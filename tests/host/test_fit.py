# SPDX-License-Identifier: Apache-2.0
import sys
from pathlib import Path
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
from zephyr_fit import encode, verify, decode, u32


class FitTests(unittest.TestCase):
    def setUp(self):
        self.payload = bytes(range(256)) * 97 + b"unaligned-tail"
        self.load, self.entry = 0x30082000, 0x30082002
        self.fit = encode(self.payload, self.load, self.entry)

    def test_roundtrip(self):
        result = verify(self.fit, self.payload, self.load, self.entry)
        self.assertEqual(result["status"], "PASS")
        self.assertFalse(result["loadable_image"])

    def test_changed_payload(self):
        data = self.fit[:-1] + bytes([self.fit[-1] ^ 1])
        with self.assertRaises(ValueError):
            verify(data, self.payload, self.load, self.entry)

    def test_wrong_address(self):
        for load, entry in ((self.load + 4, self.entry), (self.load, self.entry + 4)):
            with self.assertRaises(ValueError):
                verify(self.fit, self.payload, load, entry)

    def test_hash_corruption(self):
        import zlib
        crc = u32(zlib.crc32(self.payload) & 0xffffffff)
        data = self.fit.replace(crc, bytes(4), 1)
        with self.assertRaises(ValueError):
            verify(data, self.payload, self.load, self.entry)

    def test_truncated_and_trailing(self):
        for data in (self.fit[:20], self.fit[:-1], self.fit + b"\0"):
            with self.assertRaises(ValueError):
                verify(data, self.payload, self.load, self.entry)

    def test_invalid_structure_boundaries(self):
        data = bytearray(self.fit)
        data[12:16] = u32(0xffffffff)
        with self.assertRaises(ValueError):
            decode(data)

    def test_no_cipher_or_extra_firmware(self):
        data = self.fit.replace(b"compression\0", b"cipherxxxxx\0", 1)
        with self.assertRaises(ValueError):
            verify(data, self.payload, self.load, self.entry)


if __name__ == "__main__":
    unittest.main()
