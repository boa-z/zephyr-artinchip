# SPDX-License-Identifier: Apache-2.0
from pathlib import Path
import struct
import sys
import unittest
import zlib

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
from test_image import replace_os, verify_replacement
from test_loader_audit import container_fixture


class ReplacementTests(unittest.TestCase):
    def setUp(self):
        data = container_fixture()
        data[3072 + 72:3072 + 75] = b"os\0"
        struct.pack_into("<I", data, 3072 + 108, 16)
        self.reference = bytes(data)
        self.fit = b"FIT!"

    def test_smaller_payload_fixed_slot(self):
        output = replace_os(self.reference, self.fit)
        report = verify_replacement(self.reference, output, self.fit)
        self.assertEqual(output[3616:3624], b"FIT!\xff\xff\xff\xff")
        self.assertEqual(report["status"], "BLOCKED")
        self.assertFalse(report["loadable_image"])
        self.assertTrue(report["partition_layout_unchanged"])

    def test_empty_and_oversize_rejected(self):
        for fit in (b"", b"x" * 9, b"x" * 17):
            with self.assertRaises(ValueError):
                replace_os(self.reference, fit)

    def test_same_size(self):
        fit = b"x" * 8
        verify_replacement(self.reference, replace_os(self.reference, fit), fit)

    def test_non_os_with_repaired_crc_rejected(self):
        data = bytearray(replace_os(self.reference, self.fit))
        data[3584] ^= 1
        struct.pack_into("<I", data, 2048 + 144, zlib.crc32(data[3584:3592]))
        with self.assertRaises(ValueError):
            verify_replacement(self.reference, data, self.fit)

    def test_padding_header_partition_and_tail_tampering(self):
        for offset in (400, 3072 + 104, 3622, len(self.reference) - 1):
            data = bytearray(replace_os(self.reference, self.fit))
            data[offset] ^= 1
            with self.assertRaises(ValueError):
                verify_replacement(self.reference, data, self.fit)

    def test_wrong_expected_payload_and_truncation(self):
        output = replace_os(self.reference, self.fit)
        for image, fit in ((output, b"oops"), (output[:-1], self.fit)):
            with self.assertRaises(ValueError):
                verify_replacement(self.reference, image, fit)
