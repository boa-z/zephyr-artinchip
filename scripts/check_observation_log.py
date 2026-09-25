# SPDX-License-Identifier: Apache-2.0
"""Check one raw serial observation block; never declares hardware acceptance."""
import argparse
import json
from pathlib import Path
import re
import sys
from evidence import record


def check(data):
    lines = data.decode("utf-8", errors="replace").splitlines()
    begins = [i for i, line in enumerate(lines) if line == "H0-SPL begin schema=1 instrumentation=active acceptance=pending"]
    if len(begins) != 1:
        raise ValueError("expected exactly one H0 observation boot block")
    block = lines[begins[0] + 1:]
    if len(block) < 57:
        raise ValueError("truncated observation block")
    if block[0] != "H0-SPL entry=00000000 count=54 dropped=0":
        raise ValueError("unexpected entry/count/dropped records")
    expected = []
    for stage in (1, 3):
        expected += [(10, stage, None), (11, stage, None), (12, 0x18000160, stage)]
        expected += [(13, 0x2ffff000 + i * 4, stage) for i in range(16)]
        expected += [(14, 0x10000100 + i * 0x40, stage) for i in range(8)]
    events = []
    for index, (kind, address, size) in enumerate(expected):
        match = re.fullmatch(r"H0-E (\d+) (\d+) ([0-9a-fA-F]{8}) ([0-9a-fA-F]{8}) ([0-9a-fA-F]{8})", block[index + 1])
        if not match:
            raise ValueError("malformed event at index " + str(index))
        seq, typ = map(int, match.group(1, 2))
        addr, value, result = (int(match.group(n), 16) for n in (3, 4, 5))
        if (seq, typ, addr) != (index, kind, address) or (size is not None and size != value):
            raise ValueError("event order/register/stage mismatch")
        events.append({"index": seq, "kind": typ, "address": addr, "size": value, "result": result})
    if block[55] != "H0-SPL end evidence=CAPTURED hardware=pending":
        raise ValueError("missing complete-trace marker")
    if block[56] != "H0-OBSERVE-ONLY: OS not read; no payload jump; return to console":
        raise ValueError("missing observe-only stop marker")
    return {"log_validation": "PASS", "raw_log": record(data), "events": events,
            "nonzero_dma_enable_reads": [e for e in events if e["kind"] == 14 and e["result"]],
            "loadable_image": False, "hardware_validation": "pending",
            "limits": "Text consistency only; no flash identity, recovery or full memory safety proof"}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("log", type=Path)
    args = parser.parse_args()
    try:
        print(json.dumps(check(args.log.read_bytes()), indent=2))
    except (ValueError, OSError) as error:
        print(json.dumps({"log_validation": "FAIL", "error": str(error)}))
        sys.exit(1)
