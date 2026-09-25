# SPDX-License-Identifier: Apache-2.0
"""Lossless AIC.FW extraction/refill rehearsal. No replacement OS or device IO."""
import argparse
import json
from pathlib import Path
import sys

from audit_loader import container_components
from evidence import record


BASELINE = "b0062dacbd68e8ef6f6de0c99c7cdc6620e602c5e00e913b454af6e93037aaf1"


def split_image(data):
    components = container_components(data)
    # image.info aliases the header, so it must not become a second write span.
    payloads = sorted((value["offset"], value["offset"] + value["size"], name)
                      for name, value in components.items() if name != "image.info")
    spans = []
    cursor = 0
    for start, end, name in payloads:
        if cursor < start:
            spans.append((cursor, start, "opaque-header-metadata-or-padding"))
        spans.append((start, end, name))
        cursor = end
    if cursor < len(data):
        spans.append((cursor, len(data), "opaque-trailing-padding"))
    parts = [{"file": f"part-{index:03d}.bin", "offset": start,
              "name": name, **record(data[start:end])}
             for index, (start, end, name) in enumerate(spans)]
    return components, parts


def reconstruct(reference, parts, chunks):
    # Derive trusted offsets and filenames again, rather than trusting a manifest.
    _, expected = split_image(reference)
    if parts != expected or set(chunks) != {part["file"] for part in expected}:
        raise ValueError("part layout or inventory changed")
    result = bytearray()
    for part in expected:
        chunk = chunks[part["file"]]
        if record(chunk) != {key: part[key] for key in ("size", "sha256")}:
            raise ValueError("part content changed: " + part["file"])
        if len(result) != part["offset"]:
            raise ValueError("non-contiguous reconstruction")
        result.extend(chunk)
    if result != reference:
        raise ValueError("reconstructed image differs")
    return bytes(result)


def compare_images(reference, candidate):
    original = container_components(reference)
    rebuilt = container_components(candidate)
    if original.keys() != rebuilt.keys():
        raise ValueError("component inventory changed")
    changes = {name: {"before": original[name], "after": rebuilt[name]}
               for name in original if original[name] != rebuilt[name]}
    return {"byte_identical": reference == candidate,
            "changed_bytes": sum(a != b for a, b in zip(reference, candidate))
            + abs(len(reference) - len(candidate)),
            "component_changes": changes,
            "opaque_or_metadata_changed": reference != candidate and not changes}


def rehearse(source, destination):
    data = source.read_bytes()
    if record(data)["sha256"] != BASELINE:
        raise ValueError("source does not match pinned known-good image")
    components, parts = split_image(data)
    # Refuse existing output, including the source directory. Never overwrite SDK output.
    destination.mkdir(parents=True, exist_ok=False)
    for part in parts:
        begin = part["offset"]
        (destination / part["file"]).write_bytes(data[begin:begin + part["size"]])
    rebuilt = reconstruct(data, parts, {
        part["file"]: (destination / part["file"]).read_bytes() for part in parts})
    difference = compare_images(data, rebuilt)
    if not difference["byte_identical"]:
        raise ValueError("roundtrip failed")
    # Distinct extension: this is a codec rehearsal, not a diagnostic burn artifact.
    output = destination / "original-os-refilled.aicfw.bin"
    output.write_bytes(rebuilt)
    if output.read_bytes() != data:
        raise ValueError("written output verification failed")
    report = {"schema_version": 1, "status": "PASS", "scope": "original-OS lossless roundtrip only",
              "input": record(data), "output": record(rebuilt), "components": components,
              "parts": parts, "difference": difference, "loadable_image": False,
              "hardware_validation": "pending", "replacement_os_supported": False}
    (destination / "report.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("destination", type=Path, help="Fresh output directory")
    args = parser.parse_args()
    try:
        result = rehearse(args.source, args.destination)
    except (ValueError, OSError, UnicodeError) as error:
        print(json.dumps({"status": "FAIL", "error": str(error)}))
        return 1
    print(json.dumps({"status": result["status"], "difference": result["difference"],
                      "loadable_image": False}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
