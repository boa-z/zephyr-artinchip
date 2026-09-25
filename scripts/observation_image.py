# SPDX-License-Identifier: Apache-2.0
"""Build/check the fixed-profile H0 observe-only image. No device access."""
import hashlib
import argparse
import io
import json
from pathlib import Path
import struct
import sys
import zlib

from elftools.elf.elffile import ELFFile
from audit_loader import container_components, cstring, loader_layout
from evidence import record
from image_roundtrip import BASELINE


def word(data, offset):
    return struct.unpack_from("<I", data, offset)[0]


def checksum(data):
    if len(data) % 4:
        raise ValueError("unaligned AIC checksum input")
    return (~sum(v[0] for v in struct.iter_unpack("<I", data))) & 0xffffffff


def check_aic(data):
    if len(data) < 272 or data[:4] != b"AIC " or word(data, 8) != 0x10001:
        raise ValueError("unsupported AIC header")
    length, sign = word(data, 12), word(data, 40)
    if (length != len(data) or word(data, 32) or word(data, 36)
            or word(data, 44) != 16 or sign + 16 != length):
        raise ValueError("unsupported signed/encrypted AIC profile or length")
    if checksum(data) or hashlib.md5(data[8:sign]).digest() != data[sign:]:
        raise ValueError("AIC checksum/MD5 mismatch")


def wrap_loader(original, old_bin, new_bin):
    # The first image and padding hold the unchanged PBP/private resources.
    offset = word(original, 80)
    if offset != 23552 or original[:4] != b"AIC ":
        raise ValueError("unexpected PBP extension layout")
    check_aic(original[:word(original, 12)])
    old = original[offset:]
    check_aic(old)
    if (word(old, 20) != len(old_bin) or old[256:256 + len(old_bin)] != old_bin
            or word(old, 24) != 0x40c00000 or word(old, 28) != 0x40c00100):
        raise ValueError("reference SPL binding mismatch")
    if any(word(old, n) for n in (48, 52, 56, 60, 72, 76, 80)):
        raise ValueError("unmodeled AIC resources")
    private = word(old, 64)
    if private != 256 + ((len(old_bin) + 255) & ~255):
        raise ValueError("unexpected private resource location")
    resources = old[private:word(old, 40)]
    if word(old, 68) > len(resources):
        raise ValueError("private resource exceeds extent")
    new_private = 256 + ((len(new_bin) + 255) & ~255)
    sign = new_private + len(resources)
    header = bytearray(old[:256])
    for at, value in ((4, 0), (12, sign + 16), (20, len(new_bin)), (40, sign), (64, new_private)):
        struct.pack_into("<I", header, at, value)
    block = header + new_bin + bytes(new_private - 256 - len(new_bin)) + resources
    block += hashlib.md5(block[8:]).digest()
    struct.pack_into("<I", block, 4, checksum(block))
    check_aic(block)
    return original[:offset] + block


def verify_wrapped(original, wrapped, new_bin):
    offset = word(original, 80)
    if wrapped[:offset] != original[:offset]:
        raise ValueError("PBP prefix changed")
    old, new = original[offset:], wrapped[offset:]
    check_aic(new)
    if new[256:256 + len(new_bin)] != new_bin or word(new, 20) != len(new_bin):
        raise ValueError("new loader differs")
    allowed = {4, 12, 20, 40, 64}
    for n in range(0, 256, 4):
        if n not in allowed and new[n:n + 4] != old[n:n + 4]:
            raise ValueError("unexpected header field change")
    private, sign = word(new, 64), word(new, 40)
    if private != 256 + ((len(new_bin) + 255) & ~255):
        raise ValueError("new resource offset mismatch")
    if any(new[256 + len(new_bin):private]):
        raise ValueError("loader padding changed")
    if new[private:sign] != old[word(old, 64):word(old, 40)]:
        raise ValueError("private resource changed")


def build(reference, old_bin, elf_data, raw):
    if record(reference)["sha256"] != BASELINE:
        raise ValueError("wrong known-good image")
    if record(raw)["sha256"] != OBSERVE_BIN_SHA256:
        raise ValueError("unreviewed observation loader binary")
    _, _, _, spans = loader_layout(elf_data, raw)
    if spans[0]["end"] > 0x40c80000:
        raise ValueError("diagnostic SPL overlaps default heap")
    elf = ELFFile(io.BytesIO(elf_data))
    sym = elf.get_section_by_name(".symtab").get_symbol_by_name("spl_load_simple_fit")
    if not sym or sym[0]["st_size"] != 34:
        raise ValueError("observe-only function profile changed; review disassembly")
    # Bind to the exact reviewed observe-only function machine code separately.
    symbol = sym[0]
    section = elf.get_section(symbol["st_shndx"])
    off = symbol["st_value"] - section["sh_addr"]
    function = section.data()[off:off + symbol["st_size"]]
    if record(function)["sha256"] != OBSERVE_FUNCTION_SHA256:
        raise ValueError("unreviewed observe-only control flow")
    components = container_components(reference)
    item = components["image.target.spl"]
    start, end = item["offset"], item["offset"] + item["size"]
    original = reference[start:end]
    wrapped = wrap_loader(original, old_bin, raw)
    verify_wrapped(original, wrapped, raw)
    if len(wrapped) > item["size"]:
        raise ValueError("diagnostic SPL exceeds fixed component slot")
    meta, length = struct.unpack_from("<2I", reference, 332)
    slots = [n for n in range(meta, meta + length, 512)
             if cstring(reference[n + 8:n + 72]) == "image.target.spl"]
    if len(slots) != 1 or len(wrapped) > word(reference, slots[0] + 108):
        raise ValueError("SPL partition capacity mismatch")
    output = bytearray(reference)
    output[start:end] = wrapped + b"\xff" * (item["size"] - len(wrapped))
    struct.pack_into("<2I", output, slots[0] + 140, len(wrapped), zlib.crc32(wrapped))
    verify_image(reference, output, wrapped)
    return bytes(output), {"scope": "H0 observe-only controlled experiment", "offline_verification": "PASS",
        "hardware_validation": "pending", "loadable_image": False, "recovery_verified": False,
        "zephyr_execution": "disabled; OS FIT function returns before all reads",
        "reference": record(reference), "image": record(output), "loader": record(raw),
        "loader_elf": record(elf_data), "loader_spans": spans,
        "pbp_prefix": record(original[:word(original, 80)]), "target_spl": record(wrapped),
        "retained_updater": components["image.updater.spl"],
        "unchanged_components": sorted(set(components) - {"image.target.spl"})}


def verify_image(reference, output, expected_spl):
    before, after = container_components(reference), container_components(output)
    if len(output) != len(reference) or before.keys() != after.keys():
        raise ValueError("container inventory/length changed")
    item = before["image.target.spl"]
    start, end = item["offset"], item["offset"] + item["size"]
    if (output[start:start + len(expected_spl)] != expected_spl
            or output[start + len(expected_spl):end] != b"\xff" * (end - start - len(expected_spl))):
        raise ValueError("SPL slot differs")
    meta, length = struct.unpack_from("<2I", reference, 332)
    slot = next(n for n in range(meta, meta + length, 512)
                if cstring(reference[n + 8:n + 72]) == "image.target.spl")
    if after["image.target.spl"]["offset"] != start or after["image.target.spl"]["size"] != len(expected_spl):
        raise ValueError("SPL metadata mismatch")
    cursor = 0
    for lo, hi in sorted([(slot + 140, slot + 148), (start, end)]):
        if reference[cursor:lo] != output[cursor:lo]:
            raise ValueError("unauthorized container change")
        cursor = hi
    if reference[cursor:] != output[cursor:]:
        raise ValueError("unauthorized trailing change")
    for name in before.keys() - {"image.target.spl"}:
        if before[name] != after[name]:
            raise ValueError("non-target-SPL component changed")


OBSERVE_FUNCTION_SHA256 = '2e07b17987db588a6620e98b04833a1c7aa915a2ab0c8a3d01b9fd741b12dd86'
OBSERVE_BIN_SHA256 = "ddb228cf1e60f1a22df71cf2cded750c92724b831017c2743b2dc1d6e63f6a72"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("reference", "original-bin", "elf", "bin", "output"):
        parser.add_argument("--" + name, type=Path, required=True)
    args = parser.parse_args()
    try:
        for path in (args.reference, args.original_bin, args.elf, args.bin):
            if args.output.resolve().is_relative_to(path.parent.resolve()):
                raise ValueError("fresh output outside input directories required")
        original = args.reference.read_bytes()
        raw = args.bin.read_bytes()
        result, report = build(original, args.original_bin.read_bytes(), args.elf.read_bytes(), raw)
        args.output.mkdir(parents=True, exist_ok=False)
        image = args.output / "D50T_H0_observe_only.img"
        image.write_bytes(result)
        actual = image.read_bytes()
        components = container_components(actual)
        spl = components["image.target.spl"]
        wrapped = actual[spl["offset"]:spl["offset"] + spl["size"]]
        before = container_components(original)["image.target.spl"]
        verify_wrapped(original[before["offset"]:before["offset"] + before["size"]], wrapped, raw)
        verify_image(original, actual, wrapped)
        if actual != result:
            raise ValueError("written image mismatch")
        (args.output / "verification.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        (args.output / "SHA256SUMS.txt").write_text(record(actual)["sha256"] + "  " + image.name + "\n", encoding="utf-8")
        print(json.dumps(report, indent=2))
        return 0  # Build verification only; explicit report keeps H0/H1 pending.
    except (OSError, ValueError, KeyError, struct.error) as error:
        print(json.dumps({"offline_verification": "FAIL", "error": str(error)}))
        return 1


if __name__ == "__main__":
    sys.exit(main())
