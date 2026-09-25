# SPDX-License-Identifier: Apache-2.0
"""Read-only D13x SPL/ELF association audit. Never packages or loads firmware."""
import argparse
import io
import json
from pathlib import Path
import struct
import sys
import zlib

from elftools.common.exceptions import ELFError
from elftools.elf.elffile import ELFFile

from evidence import candidate_records, record
from package_candidate import inspect_elf, validate_segments


def bounded(data, offset, length):
    if offset < 0 or length <= 0 or offset + length > len(data):
        raise ValueError("truncated or out-of-range input")
    return data[offset:offset + length]


def cstring(data):
    if b"\0" not in data:
        raise ValueError("unterminated metadata string")
    return data.split(b"\0", 1)[0].decode("ascii")


def container_components(data):
    """The fixed SDK AIC.FW header and 512-byte metadata records, no extraction."""
    bounded(data, 0, 348)
    if data[:8] != b"AIC.FW\0\0" or cstring(data[8:72]) != "d13x":
        raise ValueError("unsupported product container")
    meta, size, files, file_size = struct.unpack_from("<4I", data, 332)
    if meta != 2048 or size % 512 or files != meta + size or files + file_size != len(data):
        raise ValueError("unsupported container boundaries")
    bounded(data, meta, size)
    result = {}
    spans = []
    for start in range(meta, meta + size, 512):
        item = bounded(data, start, 512)
        if item[:8] != b"META\0\0\0\0":
            raise ValueError("unsupported component metadata")
        name = cstring(item[8:72])
        if name in result:
            raise ValueError("duplicate component")
        offset, length, crc, ram = struct.unpack_from("<4I", item, 136)
        payload = bounded(data, offset, length)
        if zlib.crc32(payload) & 0xffffffff != crc:
            raise ValueError("component CRC mismatch: " + name)
        if name == "image.info":
            if offset != 0 or length != 2048:
                raise ValueError("unexpected info component")
        else:
            if offset < files or any(offset < end and begin < offset + length for begin, end in spans):
                raise ValueError("overlapping component data")
            spans.append((offset, offset + length))
        result[name] = {"offset": offset, "size": length, "ram": ram,
                        "partition": cstring(item[72:104]),
                        "filename": cstring(item[216:280]), **record(payload)}
    if not {"image.target.spl", "image.updater.spl", "image.target.os"} <= result.keys():
        raise ValueError("missing SPL or OS components")
    return result


def unique_offset(container, payload):
    offset = container.find(payload)
    if not payload or offset < 0 or container.find(payload, offset + 1) >= 0:
        raise ValueError("packaged loader is absent or ambiguous in SPL component")
    return offset


def compare_bytes(packaged, reference, base, sections, symbols):
    if len(packaged) != len(reference):
        raise ValueError("loader binary size mismatch")
    differences = []
    changed = 0
    for section in sections:
        begin = section["start"] - base
        end = section["end"] - base
        indices = [i for i in range(max(0, begin), min(len(reference), end))
                   if packaged[i] != reference[i]]
        if indices:
            changed += len(indices)
            # Preserve all ranges without an unbounded per-byte JSON dump.
            ranges = []
            for i in indices:
                if ranges and ranges[-1][1] == i:
                    ranges[-1][1] += 1
                else:
                    ranges.append([i, i + 1])
            differences.append({"section": section["name"], "executable": section["executable"],
                                "count": len(indices), "ranges": [
                                    {"offset": a, "address": base + a, "size": b - a,
                                     "packaged_hex": packaged[a:min(b, a + 32)].hex(),
                                     "reference_hex": reference[a:min(b, a + 32)].hex(),
                                     "symbols": [s["name"] for s in symbols
                                                 if s["start"] <= base + a < s["end"]]}
                                    for a, b in ranges]})
    total = sum(a != b for a, b in zip(packaged, reference))
    if changed != total:
        raise ValueError("difference outside modeled ELF sections")
    return {"exact_match": total == 0, "changed_bytes": total,
            "executable_bytes_equal": not any(d["executable"] for d in differences),
            "differences": differences}


def loader_layout(elf_data, raw):
    elf = ELFFile(io.BytesIO(elf_data))
    if (elf.elfclass != 32 or not elf.little_endian or elf["e_machine"] != "EM_RISCV"
            or elf["e_type"] != "ET_EXEC"):
        raise ValueError("unsupported loader ELF")
    segments = [s for s in elf.iter_segments() if s["p_type"] == "PT_LOAD"]
    if len(segments) != 1:
        raise ValueError("expected one fixed-profile loader PT_LOAD")
    segment = segments[0]
    start = segment["p_paddr"]
    base = elf["e_entry"]
    if (segment["p_vaddr"] != start or segment["p_filesz"] > segment["p_memsz"]
            or segment["p_offset"] + segment["p_filesz"] > len(elf_data)
            or not start <= base < start + segment["p_filesz"]
            or start + segment["p_memsz"] > 2**32):
        raise ValueError("invalid loader load segment")
    # This profile's raw SDK bin omits the leading boot header. Verify the
    # entire suffix, including gaps, rather than guessing objcopy options.
    if segment.data()[base - start:] != raw:
        raise ValueError("reference loader ELF/bin mismatch")
    sections = []
    for section in elf.iter_sections():
        if section["sh_flags"] & 2 and section["sh_type"] != "SHT_NOBITS" and section["sh_size"]:
            begin, size = section["sh_addr"], section["sh_size"]
            if not base <= begin < begin + size <= base + len(raw):
                raise ValueError("unmodeled allocated loader section")
            if bounded(raw, begin - base, size) != section.data():
                raise ValueError("allocated section differs from raw loader")
            sections.append({"name": section.name, "start": begin, "end": begin + size,
                             "executable": bool(section["sh_flags"] & 4)})
    for a, b in zip(sorted(sections, key=lambda s: s["start"]),
                    sorted(sections, key=lambda s: s["start"])[1:]):
        if a["end"] > b["start"]:
            raise ValueError("overlapping allocated sections")
    if not any(s["executable"] and s["start"] == base for s in sections):
        raise ValueError("loader entry is not an executable section start")
    table = elf.get_section_by_name(".symtab")
    if table is None:
        raise ValueError("loader symbol table missing")
    symbols = [{"name": s.name, "start": s["st_value"], "end": s["st_value"] + s["st_size"]}
               for s in table.iter_symbols() if s["st_size"] and s["st_value"]]

    def symbol(name):
        found = table.get_symbol_by_name(name)
        if not found or len(found) != 1:
            raise ValueError("missing/ambiguous loader symbol: " + name)
        return found[0]["st_value"]

    heap_start, heap_end = symbol("__heap_start"), symbol("__heap_end")
    if not start + segment["p_memsz"] <= heap_start < heap_end <= 2**32:
        raise ValueError("invalid static loader heap span")
    spans = [{"name": "loader PT_LOAD (includes BSS, stacks and boot arguments)",
              "start": start, "end": start + segment["p_memsz"]},
             {"name": "loader default heap", "start": heap_start, "end": heap_end}]
    for bottom, top in (("g_base_irqstack", "g_top_irqstack"),
                        ("g_base_normalstack", "g_top_normalstack")):
        if not start <= symbol(bottom) < symbol(top) <= spans[0]["end"]:
            raise ValueError("stack outside modeled PT_LOAD")
    return base, sections, symbols, spans


def overlaps(candidate, loader):
    return [{"candidate": c, "loader": s} for c in candidate for s in loader
            if c["start"] < s["end"] and s["start"] < c["end"]]


def audit(product, loader, candidates):
    image_paths = list(product.glob("*.img"))
    if len(image_paths) != 1:
        raise ValueError("product directory must contain exactly one .img")
    image = image_paths[0].read_bytes()
    components = container_components(image)
    packaged = (product / "bootloader.bin").read_bytes()
    bindings = {}
    for name in ("image.target.spl", "image.updater.spl"):
        item = components[name]
        payload = bounded(image, item["offset"], item["size"])
        bindings[name] = {"raw_loader_offset": unique_offset(payload, packaged), **record(payload)}
    if bindings["image.target.spl"] != bindings["image.updater.spl"]:
        raise ValueError("updater and target SPL differ")
    reference = (loader / "d13x.bin").read_bytes()
    elf_data = (loader / "d13x.elf").read_bytes()
    base, sections, symbols, spans = loader_layout(elf_data, reference)
    comparison = compare_bytes(packaged, reference, base, sections, symbols)
    results = {}
    for app in ("bringup", "kernel", "fpu", *(["handoff_probe"] if (candidates / "handoff_probe").exists() else [])):
        directory = candidates / app
        manifest = json.loads((directory / "candidate.json").read_text())
        if manifest["application"] != app:
            raise ValueError("candidate application mismatch")
        for name, expected in candidate_records(manifest).items():
            if record((directory / name).read_bytes()) != expected:
                raise ValueError("candidate payload changed: " + app + "/" + name)
        metadata = inspect_elf(directory / "zephyr.elf")
        if metadata["type"] != "ET_EXEC":
            raise ValueError("candidate is not executable")
        entry, segments = metadata["entry"], metadata["segments"]
        errors = validate_segments(segments, entry)
        if errors:
            raise ValueError("invalid candidate: " + str(errors))
        candidate_spans = [{"start": s["address"], "end": s["address"] + s["memory_size"]}
                           for s in segments]
        results[app] = {"source_at_build": manifest["source_at_build"]["head"],
                        "elf": manifest["files"]["zephyr.elf"], "entry": entry,
                        "load_spans": candidate_spans,
                        "file_spans": [{"start": s["address"], "end": s["address"] + s["file_size"]}
                                       for s in segments if s["file_size"]],
                        "overlaps": overlaps(candidate_spans, spans)}
    blocked = []
    if not comparison["exact_match"]:
        blocked.append("Packaged SPL differs from the supplied loader ELF/bin; static layout is reference-only.")
    if any(r["overlaps"] for r in results.values()):
        blocked.append("Candidate overlaps a known static loader range.")
    return {"schema_version": 1, "audit_status": "BLOCKED" if blocked else "PASS",
            "static_memory_overlap": "fail" if any(r["overlaps"] for r in results.values()) else "pass",
            "ram_ownership": "unverified",
            "scope": "local container, loader identity and known static spans only",
            "input_files": {str(image_paths[0]): record(image), str(product / "bootloader.bin"): record(packaged),
                            str(loader / "d13x.bin"): record(reference), str(loader / "d13x.elf"): record(elf_data)},
            "container_components": components, "packaged_loader_bindings": bindings,
            "loader_comparison": comparison, "reference_loader_ranges": spans,
            "candidates": results, "blockers": blocked, "handoff_status": "BLOCKED",
            "remaining_hardware_evidence": ["installed-image association", "runtime/DMA/staging RAM ownership",
                                           "TCM/map/cache/CSR and interrupt handoff", "recovery and console confirmation"],
            "hardware_validation": "pending", "loadable_image": False}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("product", "loader", "candidates", "output"):
        parser.add_argument("--" + name, type=Path, required=True)
    args = parser.parse_args(argv)
    if args.output.exists():
        raise ValueError("use a new audit output path")
    for root in (args.product, args.loader, args.candidates):
        if args.output.resolve().is_relative_to(root.resolve()):
            raise ValueError("audit output must be outside every input tree")
    result = audit(args.product, args.loader, args.candidates)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x", encoding="utf-8") as stream:
        json.dump(result, stream, indent=2)
        stream.write("\n")
    print(json.dumps({"status": result["audit_status"], "output": str(args.output),
                      "blockers": result["blockers"], "loadable_image": False}))
    return 2 if result["audit_status"] == "BLOCKED" else 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (OSError, ValueError, KeyError, struct.error, ELFError) as error:
        print(json.dumps({"status": "FAIL", "error": str(error)}))
        sys.exit(1)
