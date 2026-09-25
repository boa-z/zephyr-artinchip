# SPDX-License-Identifier: Apache-2.0
"""Identify a manually reviewed host tool without executing it or opening USB.

Exit 2: recognized profile, H0 still blocked. Exit 1: unknown/unreadable input.
This is a hash-bound review lookup, not a general executable analyzer.
"""
import argparse
import hashlib
import json
from pathlib import Path
import sys


REVIEWED_SHA256 = "e58c96d7b34a1150115013519646af2d4518f8b63e9232559de959072097d48f"


def audit(data):
    digest = hashlib.sha256(data).hexdigest()
    result = {
        "schema_version": 1,
        "sha256": digest,
        "size": len(data),
        "method": "exact SHA-256 lookup of manual offline disassembly review",
        "hardware_validation": "pending",
        "loadable_image": False,
        "recovery_verified": False,
    }
    if digest != REVIEWED_SHA256:
        result.update(status="UNKNOWN", reason="Executable differs from reviewed profile; re-review required")
        return result, 1
    result.update(
        status="BLOCKED",
        profile="installed AiBurn upgcmd PE32 i386",
        reviewed_path={
            "ramboot_function_va": "0x405ed0",
            "format_string_va": "0x605007",
            "format": "ram_boot 0x%lx %s %d",
            "format_reference_va": "0x406223",
            "shell_wrapper_call_va": "0x40628c",
            "shell_wrapper_va": "0x4073b0",
            "transport_call_va": "0x4073d2",
            "transport_va": "0x4072b0",
            "protocol_header_store_va": "0x4072e5",
            "protocol_header_value": "0x00050101",
            "command": "0x05 RUN_SHELL",
        },
        conclusion="Reviewed ramboot path delegates to loader ram_boot; not an independent FIT executor",
        limitations=[
            "Loader must be audited separately; host identity cannot prove board loader identity",
            "Connection and updater preparation paths are not fully reviewed",
            "No claim of RAM-only behavior or absence of persistent writes",
            "No staging address, live RAM ownership, or recovery proof established",
        ],
    )
    return result, 2


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("executable", type=Path, help="Read as bytes only; never launched")
    args = parser.parse_args(argv)
    try:
        result, status = audit(args.executable.read_bytes())
    except OSError as error:
        result, status = {"status": "ERROR", "error": str(error), "loadable_image": False}, 1
    print(json.dumps(result, indent=2))
    return status


if __name__ == "__main__":
    sys.exit(main())
