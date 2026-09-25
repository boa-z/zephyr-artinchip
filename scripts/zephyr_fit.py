# SPDX-License-Identifier: Apache-2.0
"""Restricted external-data FIT codec and audited candidate binding. No device IO."""
import hashlib
import json
from pathlib import Path
import struct
import zlib

from evidence import candidate_records, record
from package_candidate import inspect_elf, validate_segments


def u32(value):
    return struct.pack(">I", value)


def align(value):
    return (value + 3) & ~3


def string(value):
    return value.encode("ascii") + b"\0"


def candidate(path, audit_path):
    path = Path(path).resolve()
    manifest = json.loads(path.read_text(encoding="utf-8"))
    audit = json.loads(Path(audit_path).read_text(encoding="utf-8"))
    if audit.get("audit_status") != "PASS" or not audit["loader_comparison"]["exact_match"]:
        raise ValueError("passing matching-loader static audit required")
    if manifest.get("loadable_image") is not False or manifest.get("hardware_validation") != "pending":
        raise ValueError("only pending, non-loadable candidates accepted")
    for name, expected in candidate_records(manifest).items():
        if record((path.parent / name).read_bytes()) != expected:
            raise ValueError("candidate file changed: " + name)
    elf = inspect_elf(path.parent / "zephyr.elf")
    if elf != manifest["elf"] or elf["type"] != "ET_EXEC" or validate_segments(elf["segments"], elf["entry"]):
        raise ValueError("candidate ELF metadata mismatch")
    if any(s["address"] != s["virtual_address"] for s in elf["segments"]):
        raise ValueError("non-identity mapped ELF")
    binding = audit["candidates"][manifest["application"]]
    if (binding["source_at_build"] != manifest["source_at_build"]["head"] or
            binding["elf"] != manifest["files"]["zephyr.elf"] or binding["overlaps"] or
            binding["entry"] != elf["entry"]):
        raise ValueError("candidate does not match loader audit")
    segments = sorted(elf["segments"], key=lambda s: s["address"])
    load = segments[0]["address"]
    payload = (path.parent / "zephyr.bin").read_bytes()
    end = max(s["address"] + s["file_size"] for s in segments if s["file_size"])
    if len(payload) != end - load:
        raise ValueError("raw binary span does not match ELF file spans")
    # Independently reconstruct allocated bytes, including zero-filled segment gaps.
    from elftools.elf.elffile import ELFFile
    with (path.parent / "zephyr.elf").open("rb") as stream:
        reconstructed = bytearray(len(payload))
        for seg in ELFFile(stream).iter_segments():
            if seg["p_type"] == "PT_LOAD" and seg["p_filesz"]:
                offset = seg["p_paddr"] - load
                reconstructed[offset:offset + seg["p_filesz"]] = seg.data()
    if bytes(reconstructed) != payload:
        raise ValueError("binary differs from ELF PT_LOAD bytes")
    if any(load < r["end"] and r["start"] < end for r in audit["reference_loader_ranges"]):
        raise ValueError("raw binary span overlaps loader")
    return manifest, payload, load, elf["entry"]


def encode(payload, load, entry):
    """FDT v17, single firmware, external data-offset relative to totalsize."""
    strings, structure = bytearray(), bytearray()
    offsets = {}

    def begin(name):
        data = string(name)
        structure.extend(u32(1) + data + bytes(align(len(data)) - len(data)))

    def end():
        structure.extend(u32(2))

    def prop(name, value):
        if name not in offsets:
            offsets[name] = len(strings)
            strings.extend(string(name))
        structure.extend(u32(3) + u32(len(value)) + u32(offsets[name]) + value)
        structure.extend(bytes(align(len(value)) - len(value)))

    begin("")
    prop("description", string("Artinchip Zephyr diagnostic candidate; NOT AUTHORIZED TO LOAD"))
    prop("#address-cells", u32(1))
    begin("images")
    prop("version", string("1.0.0"))
    begin("seg0")
    for name, value in {"description": "Zephyr SRAM candidate", "type": "firmware",
                        "arch": "riscv", "os": "artinchip", "compression": "none"}.items():
        prop(name, string(value))
    for name, value in {"load": load, "entry": entry, "data-offset": 0,
                        "data-size": len(payload)}.items():
        prop(name, u32(value))
    for name, algo, value in (("hash-1", "crc32", u32(zlib.crc32(payload) & 0xffffffff)),
                              ("hash-2", "md5", hashlib.md5(payload).digest())):
        begin(name)
        prop("algo", string(algo))
        prop("value", value)
        end()
    end()
    end()
    begin("configurations")
    prop("default", string("conf-1"))
    begin("conf-1")
    prop("description", string("Zephyr diagnostic firmware"))
    prop("firmware", string("seg0"))
    end()
    end()
    end()
    structure.extend(u32(9))
    off_struct = 56  # header plus terminating empty reserve map
    off_strings = off_struct + len(structure)
    total = align(off_strings + len(strings))
    header = struct.pack(">10I", 0xd00dfeed, total, off_struct, off_strings, 40,
                         17, 16, 0, len(strings), len(structure))
    return header + bytes(16) + structure + strings + bytes(total - off_strings - len(strings)) + payload


def decode(data):
    """Bounded parser; reject ambiguous/malformed input rather than guessing."""
    if len(data) < 56:
        raise ValueError("truncated FIT")
    magic, total, os, ost, om, version, last, cpu, ns, nt = struct.unpack_from(">10I", data)
    if (magic != 0xd00dfeed or version != 17 or last != 16 or cpu != 0 or om != 40 or
            data[40:56] != bytes(16) or os < 56 or os % 4 or nt % 4 or
            os + nt > ost or ost + ns > total or total > len(data) or total % 4):
        raise ValueError("unsupported FIT layout")
    strings = data[ost:ost + ns]
    stop, pos, stack, nodes, finished = os + nt, os, [], {}, False
    while pos < stop:
        token = struct.unpack_from(">I", data, pos)[0]
        pos += 4
        if token == 1:
            end = data.find(b"\0", pos, stop)
            if end < 0:
                raise ValueError("unterminated node")
            name = data[pos:end].decode("ascii")
            if "/" in name or (not stack and name):
                raise ValueError("invalid node name")
            stack.append(name)
            path = "/".join(stack)
            if path in nodes:
                raise ValueError("duplicate node")
            nodes[path] = {}
            pos = align(end + 1)
        elif token == 2:
            if not stack:
                raise ValueError("unbalanced FIT")
            stack.pop()
        elif token == 3:
            if not stack or pos + 8 > stop:
                raise ValueError("invalid property")
            size, offset = struct.unpack_from(">2I", data, pos)
            pos += 8
            end = strings.find(b"\0", offset)
            if end < 0 or offset >= len(strings) or pos + size > stop:
                raise ValueError("property outside FIT")
            name = strings[offset:end].decode("ascii")
            props = nodes["/".join(stack)]
            if name in props:
                raise ValueError("duplicate property")
            props[name] = data[pos:pos + size]
            pos += align(size)
        elif token == 9:
            if stack or pos != stop:
                raise ValueError("invalid FIT end")
            finished = True
        else:
            raise ValueError("unsupported FIT token")
    if not finished:
        raise ValueError("missing FIT end")
    return nodes, total


def verify(data, payload, load, entry):
    nodes, total = decode(data)
    expected = {"", "/images", "/images/seg0", "/images/seg0/hash-1",
                "/images/seg0/hash-2", "/configurations", "/configurations/conf-1"}
    if set(nodes) != expected:
        raise ValueError("unexpected FIT nodes")
    image = nodes["/images/seg0"]
    if set(image) != {"description", "type", "arch", "os", "compression", "load",
                      "entry", "data-offset", "data-size"}:
        raise ValueError("unexpected firmware properties")
    checks = {"type": string("firmware"), "arch": string("riscv"), "os": string("artinchip"),
              "compression": string("none"), "load": u32(load), "entry": u32(entry),
              "data-offset": u32(0), "data-size": u32(len(payload))}
    if any(image[k] != v for k, v in checks.items()):
        raise ValueError("FIT semantics do not match candidate")
    if (nodes["/configurations"].get("default") != string("conf-1") or
            nodes["/configurations/conf-1"].get("firmware") != string("seg0")):
        raise ValueError("wrong default firmware")
    if data[total:] != payload:
        raise ValueError("external payload differs or trailing bytes present")
    for name, algo, value in (("hash-1", "crc32", u32(zlib.crc32(payload) & 0xffffffff)),
                              ("hash-2", "md5", hashlib.md5(payload).digest())):
        if nodes["/images/seg0/" + name] != {"algo": string(algo), "value": value}:
            raise ValueError("FIT hash mismatch")
    return {"status": "PASS", "payload": record(payload), "load": load, "entry": entry,
            "fit": record(data), "external_data_start": total,
            "loadable_image": False, "hardware_validation": "pending"}
