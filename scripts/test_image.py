# SPDX-License-Identifier: Apache-2.0
"""Fixed-slot OS replacement for offline AIC.FW study; never operates hardware."""
import argparse
import json
from pathlib import Path
import struct
import sys
import zlib

from audit_loader import container_components, cstring
from evidence import record
from image_roundtrip import BASELINE
from zephyr_fit import candidate, verify as verify_fit


OS = "image.target.os"


def layout(data):
    components = container_components(data)
    meta, size = struct.unpack_from("<2I", data, 332)
    slots = [offset for offset in range(meta, meta + size, 512)
             if cstring(data[offset + 8:offset + 72]) == OS]
    if len(slots) != 1 or components[OS]["partition"] != "os":
        raise ValueError("unsupported OS metadata")
    offset = slots[0]
    partition_size = struct.unpack_from("<I", data, offset + 108)[0]
    item = components[OS]
    if not 0 < item["size"] <= partition_size:
        raise ValueError("invalid OS partition capacity")
    return components, offset, partition_size


def replace_os(reference, fit):
    components, meta, capacity = layout(reference)
    os = components[OS]
    if not 0 < len(fit) <= min(os["size"], capacity):
        raise ValueError("OS exceeds fixed slot/partition or is empty")
    output = bytearray(reference)
    start, end = os["offset"], os["offset"] + os["size"]
    output[start:end] = fit + b"\xff" * (os["size"] - len(fit))
    struct.pack_into("<2I", output, meta + 140, len(fit), zlib.crc32(fit))
    return bytes(output)


def verify_replacement(reference, output, fit):
    before, meta, capacity = layout(reference)
    after, new_meta, new_capacity = layout(output)
    if len(output) != len(reference) or before.keys() != after.keys():
        raise ValueError("container size/inventory changed")
    if meta != new_meta or capacity != new_capacity:
        raise ValueError("OS partition layout changed")
    old = before[OS]
    start, end = old["offset"], old["offset"] + old["size"]
    if not 0 < len(fit) <= min(old["size"], capacity):
        raise ValueError("invalid replacement size")
    # Independently compare every byte outside the only two allowed ranges.
    ranges = sorted([(meta + 140, meta + 148), (start, end)])
    cursor = 0
    for begin, finish in ranges:
        if reference[cursor:begin] != output[cursor:begin]:
            raise ValueError("change outside OS payload/length/CRC")
        cursor = finish
    if reference[cursor:] != output[cursor:]:
        raise ValueError("change outside OS payload/length/CRC")
    if (output[start:start + len(fit)] != fit or
            output[start + len(fit):end] != b"\xff" * (end - start - len(fit))):
        raise ValueError("OS payload or retired-slot fill differs")
    if after[OS]["offset"] != start or after[OS]["size"] != len(fit):
        raise ValueError("OS metadata differs")
    for name in before.keys() - {OS}:
        if before[name] != after[name]:
            raise ValueError("non-OS component changed: " + name)
    return {"verification": "PASS", "scope": "fixed-slot offline replacement only",
            "reference": record(reference), "output": record(output), "fit": record(fit),
            "os_before": old, "os_after": after[OS],
            "allowed_change_ranges": [{"start": a, "end": b} for a, b in ranges],
            "metadata_fields_changed": ["OS size_in_img", "OS crc"],
            "retired_slot_fill": "0xff; outside declared OS component",
            "non_os_components_unchanged": sorted(before.keys() - {OS}),
            "container_offsets_unchanged": True, "partition_layout_unchanged": True,
            "status": "BLOCKED", "loadable_image": False,
            "hardware_validation": "pending", "recovery_verified": False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=["build", "verify"])
    parser.add_argument("--reference", type=Path, required=True)
    parser.add_argument("--fit", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--audit", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True,
                        help="Fresh directory for build; existing image file for verify")
    args = parser.parse_args()
    try:
        reference = args.reference.read_bytes()
        if record(reference)["sha256"] != BASELINE:
            raise ValueError("reference does not match pinned baseline")
        manifest, payload, load, entry = candidate(args.manifest, args.audit)
        if manifest["application"] != "handoff_probe":
            raise ValueError("only handoff_probe is supported by this study profile")
        fit = args.fit.read_bytes()
        verify_fit(fit, payload, load, entry)
        output = (replace_os(reference, fit) if args.mode == "build"
                  else args.output.read_bytes())
        report = verify_replacement(reference, output, fit)
        report.update(source_head=manifest["source_at_build"]["head"],
                      manifest=record(args.manifest.read_bytes()), audit=record(args.audit.read_bytes()))
        if args.mode == "build":
            # No overwrite, input-derived filenames, external commands or device IO.
            for path in (args.reference, args.fit, args.manifest, args.audit):
                if args.output.resolve().is_relative_to(path.parent.resolve()):
                    raise ValueError("output must be outside input directories")
            args.output.mkdir(parents=True, exist_ok=False)
            image = args.output / "probe-offline-only.aicfw.bin"
            image.write_bytes(output)
            verify_replacement(reference, image.read_bytes(), fit)
            (args.output / "report.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        print(json.dumps(report, indent=2))
        return 2  # Offline verification passed; hardware/loading gate remains blocked.
    except (OSError, ValueError, KeyError, struct.error) as error:
        print(json.dumps({"status": "FAIL", "error": str(error)}))
        return 1


if __name__ == "__main__":
    sys.exit(main())
