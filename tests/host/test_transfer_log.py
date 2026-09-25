# SPDX-License-Identifier: Apache-2.0
from pathlib import Path
import sys
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'scripts'))
from check_transfer_log import check, check_original


def snapshot(stage):
    return ([(10, stage, 8, 0), (11, stage, 0, 0), (12, 0x18000160, stage, 2)]
            + [(13, 0x2ffff000 + 4*i, stage, 0) for i in range(16)]
            + [(14, 0x10000100 + 0x40*i, stage, 0) for i in range(8)])


def records():
    result = snapshot(1)
    for address, size in ((0x40c80040, 40), (0x40c80100, 512)):
        result += [(1, address, size, 0), (16, 0x40c10000, 2, 0), (2, address, size, 0)]
    result += snapshot(2)
    result += [(3, 0x40000000, 4096, 512), (1, 0x40000000, 4096, 512),
               (4, 0x40c81000, 2112, 0), (16, 0x40c10000, 100000, 0),
               (5, 0x40c81000, 0, 0), (2, 0x40000000, 4096, 0),
               (8, 0x40000000, 4096, 0x12345678), (7, 0, 0, 0)]
    return result + snapshot(3)


def encode(events):
    lines = ['H0-SPL begin schema=2 instrumentation=active acceptance=pending',
             f'H0-SPL entry=00000000 count={len(events)} dropped=0']
    lines += [f'H0-E {i} {k} {a:08x} {s:08x} {r:08x}' for i, (k,a,s,r) in enumerate(events)]
    lines += ['H0-SPL end evidence=CAPTURED hardware=pending',
              'H0-TRANSFER-ONLY: FIT attempt ended; no payload jump; return to console']
    return '\n'.join(lines).encode()


class TransferTests(unittest.TestCase):
    def test_original_profile_with_nand_status_returns(self):
        rows = records()
        adjusted = []
        for k, a, s, r in rows:
            if a == 0x40c80100 and k in (1, 2):
                s = 732
            if a == 0x40000000 and k in (1, 2, 3, 8):
                s = 1397820
                r = 0xf183bd17 if k == 8 else (2048 if k in (1, 3) else 0)
            adjusted.append((k, a, s, r))
        self.assertEqual(check_original(encode(adjusted))['read_count'], 3)

    def test_byte_count_is_not_a_nand_success_status(self):
        rows = records()
        index = next(i for i, e in enumerate(rows) if e[0] == 2)
        k, a, s, _ = rows[index]
        rows[index] = (k, a, s, s)
        with self.assertRaisesRegex(ValueError, 'NAND read'):
            check(encode(rows))

    def test_generic_trace_cannot_pass_original_image_binding(self):
        with self.assertRaisesRegex(ValueError, 'profile'):
            check_original(encode(records()))

    def test_large_stop_count_without_promoting_gate(self):
        result = check(encode(records()))
        self.assertEqual(result['dma_stop_count'], 100004)
        self.assertFalse(result['loadable_image'])

    def test_failures_and_lifetimes(self):
        for kind, column, value in ((2, 3, 0xffffffff), (16, 3, 1),
                                    (16, 2, 0), (5, 1, 0x1234),
                                    (4, 1, 0), (7, 3, 0xffffffff),
                                    (14, 3, 1), (3, 1, 0xfffffff0)):
            with self.subTest(kind=kind, column=column):
                rows = records()
                index = next(i for i, e in enumerate(rows) if e[0] == kind)
                changed = list(rows[index])
                changed[column] = value
                rows[index] = tuple(changed)
                with self.assertRaises(ValueError):
                    check(encode(rows))

    def test_missing_crc_free_and_snapshot(self):
        for kind in (8, 5, 12, 7):
            with self.assertRaises(ValueError):
                check(encode([e for e in records() if e[0] != kind]))

    def test_truncated_duplicate_overflow(self):
        data = encode(records())
        for invalid in (data[:-10], data+b'\n'+data, data.replace(b'dropped=0', b'dropped=1')):
            with self.assertRaises(ValueError):
                check(invalid)
