# SPDX-License-Identifier: Apache-2.0
"""Reparse external FIT and compare against the audited candidate and ELF."""
import argparse
import json
from pathlib import Path
import sys

from zephyr_fit import candidate, verify


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("fit", type=Path)
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--audit", type=Path, required=True)
    args = parser.parse_args()
    _, payload, load, entry = candidate(args.manifest, args.audit)
    print(json.dumps(verify(args.fit.read_bytes(), payload, load, entry), indent=2))


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError, KeyError) as error:
        print(json.dumps({"status": "FAIL", "error": str(error)}))
        sys.exit(1)
