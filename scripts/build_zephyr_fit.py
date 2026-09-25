# SPDX-License-Identifier: Apache-2.0
"""Generate a non-loadable FIT study artifact; never an AIC.FW product image."""
import argparse
import json
from pathlib import Path
import sys

from zephyr_fit import candidate, encode, verify
from evidence import record


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--audit", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists() or args.output.resolve().is_relative_to(args.manifest.parent.resolve()):
        raise ValueError("fresh output outside candidate required")
    manifest, payload, load, entry = candidate(args.manifest, args.audit)
    data = encode(payload, load, entry)
    report = verify(data, payload, load, entry)
    report.update(source_head=manifest["source_at_build"]["head"],
                  candidate_manifest=record(args.manifest.read_bytes()),
                  static_audit=record(args.audit.read_bytes()))
    args.output.mkdir(parents=True)
    (args.output / "candidate.itb").write_bytes(data)
    (args.output / "roundtrip.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report))


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError, KeyError) as error:
        print(json.dumps({"status": "FAIL", "error": str(error)}))
        sys.exit(1)
