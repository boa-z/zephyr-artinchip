# SPDX-License-Identifier: Apache-2.0
"""Fresh controlled D13x build; only successful builds receive a provenance receipt."""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess
import sys

from build_provenance import (APPLICATIONS, BOARD, PAYLOADS, ROOT, binary_command,
                              build_tools, dependency_snapshot, file_record, linked_files,
                              source_snapshot, validate_build_identity, verify_binary)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("application", choices=APPLICATIONS)
    parser.add_argument("build", type=Path)
    args = parser.parse_args()
    build = args.build.resolve()
    if build.exists():
        raise ValueError("fresh build directory required; do not overwrite old evidence")
    source = source_snapshot()
    base = Path(subprocess.check_output(
        [sys.executable, "-m", "west", "list", "zephyr", "-f", "{abspath}"],
        cwd=ROOT, text=True).strip())
    dependency = dependency_snapshot(base)
    command = [sys.executable, "-m", "west", "build", "-b", BOARD,
               str(ROOT / APPLICATIONS[args.application]), "-d", str(build)]
    subprocess.run(command, cwd=ROOT, check=True)
    if source_snapshot() != source or dependency_snapshot(base) != dependency:
        raise ValueError("source or dependency changed during build")
    cache = validate_build_identity(build, args.application, base)
    tools = build_tools(cache)
    conversion = binary_command(build, tools["objcopy"]["path"])
    verify_binary(build, conversion)
    receipt = {"schema_version": 1, "status": "PASS", "board": BOARD,
               "application": args.application, "build": str(build), "command": command,
               "completed_utc": datetime.now(timezone.utc).isoformat(),
               "source_at_build": source, "dependency_at_build": dependency,
               "tools": tools, "binary_command": conversion,
               "linked_files": linked_files(build),
               "files": {name: file_record(build / name) for name in PAYLOADS}}
    (build / "build-provenance.json").write_text(json.dumps(receipt, indent=2) + "\n",
                                                 encoding="utf-8")
    print(json.dumps({"status": "PASS", "receipt": str(build / "build-provenance.json")}))


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError, KeyError, subprocess.CalledProcessError) as error:
        print(json.dumps({"status": "FAIL", "error": str(error)}))
        sys.exit(1)
