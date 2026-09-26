# SPDX-License-Identifier: Apache-2.0
"""Report the experimental product-window fit of a D13x build; no packaging, no IO.

The gate packager needs the pinned product reference image, which a CI runner
does not have, so this applies the same structural window binding (one executable
segment at 0x40000000 that still fits the observed 64 KiB window, matching
144-slot interrupt tables, ELF-to-BIN round trip) straight from a build
directory, and echoes the Kconfig profile the build itself states. It never
produces a flashable image and never claims hardware validation.
"""
import argparse
import json
from pathlib import Path
import sys

from evidence import record
from package_gate_trial import WINDOW_BYTES, config_setting, window_binding


def check(build, expectations=()):
    elf_data = (build / "zephyr.elf").read_bytes()
    raw = (build / "zephyr.bin").read_bytes()
    config = (build / ".config").read_text(encoding="utf-8", errors="replace")
    # window_binding raises if the gate build overflowed the experimental window.
    segment, entry = window_binding(elf_data, raw)
    profile = {key: config_setting(config, key) for key, _ in expectations}
    for key, expected in expectations:
        if profile[key] != expected:
            raise ValueError(f"{key}={profile[key]}, expected {expected}: "
                             "the build does not state the required hardware profile")
    return {"status": "PASS", "window_start": segment["p_paddr"],
            "p_filesz": segment["p_filesz"], "p_memsz": segment["p_memsz"],
            "window_bytes": WINDOW_BYTES,
            "ram_utilization_percent": round(100 * segment["p_memsz"] / WINDOW_BYTES, 2),
            "entry": entry, "elf": record(elf_data), "binary": record(raw),
            "profile": profile, "loadable_image": False,
            "hardware_validation": "pending",
            "scope": "offline window size and profile check; no product image packaged"}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("build", type=Path, help="directory containing zephyr.elf/bin/.config")
    parser.add_argument("--expect", action="append", default=[],
                        metavar="CONFIG_SYMBOL=VALUE",
                        help='repeatable required profile, e.g. '
                             'CONFIG_AIC_Z0_STRESS_DURATION_SEC=600')
    args = parser.parse_args()
    pairs = []
    for item in args.expect:
        key, separator, value = item.partition("=")
        if not separator or not key or not value:
            parser.error(f"malformed --expect: {item}")
        pairs.append((key, value))
    try:
        print(json.dumps(check(args.build.resolve(), pairs), indent=2))
    except (OSError, ValueError, KeyError) as error:
        print(json.dumps({"status": "FAIL", "error": str(error)}))
        sys.exit(1)
