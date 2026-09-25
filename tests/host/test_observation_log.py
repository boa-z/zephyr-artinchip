# SPDX-License-Identifier: Apache-2.0
from pathlib import Path
import sys
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
from check_observation_log import check


def fixture():
    records = []
    for stage in (1, 3):
        records += [(10, stage, 8, 0), (11, stage, 0, 0), (12, 0x18000160, stage, 0)]
        records += [(13, 0x2ffff000 + i * 4, stage, 0) for i in range(16)]
        records += [(14, 0x10000100 + i * 0x40, stage, int(i == 0)) for i in range(8)]
    lines = ["H0-SPL begin schema=1 instrumentation=active acceptance=pending",
             "H0-SPL entry=00000000 count=54 dropped=0"]
    lines += [f"H0-E {i} {k} {a:08x} {s:08x} {r:08x}" for i, (k, a, s, r) in enumerate(records)]
    lines += ["H0-SPL end evidence=CAPTURED hardware=pending",
              "H0-OBSERVE-ONLY: OS not read; no payload jump; return to console"]
    return "\r\n".join(lines).encode()


class ObservationLogTests(unittest.TestCase):
    def test_capture_does_not_promote_hardware_gate(self):
        result = check(fixture())
        self.assertEqual(len(result["nonzero_dma_enable_reads"]), 2)
        self.assertFalse(result["loadable_image"])

    def test_missing_duplicate_and_overflow(self):
        for data in (fixture()[:-5], fixture() + b"\r\n" + fixture(),
                     fixture().replace(b"dropped=0", b"dropped=1")):
            with self.assertRaises(ValueError):
                check(data)

    def test_wrong_register_or_sequence(self):
        for data in (fixture().replace(b"18000160", b"18000164"),
                     fixture().replace(b"H0-E 1 ", b"H0-E 0 ")):
            with self.assertRaises(ValueError):
                check(data)
