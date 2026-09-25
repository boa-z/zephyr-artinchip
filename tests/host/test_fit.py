# SPDX-License-Identifier: Apache-2.0
import sys
from pathlib import Path
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
from zephyr_fit import encode, verify, decode, u32, reconstruct_binary
from unittest.mock import Mock


class Section(dict):
    def data(self):
        return b"x" * self["sh_size"]


class BinaryReconstructionTests(unittest.TestCase):
    args = ["--gap-fill", "0xFF", "--output-target=binary",
            "--remove-section=.comment", "--remove-section=COMMON"]

    def elf(self, start=4):
        return Mock(iter_sections=lambda: iter([
            Section(sh_flags=2, sh_type="SHT_PROGBITS", sh_size=2, sh_addr=0),
            Section(sh_flags=2, sh_type="SHT_PROGBITS", sh_size=2, sh_addr=start),
            Section(sh_flags=2, sh_type="SHT_NOBITS", sh_size=10, sh_addr=6)]))

    def test_objcopy_ff_padding_not_elf_segment_zero_padding(self):
        self.assertEqual(reconstruct_binary(self.elf(), 0, 6, self.args), b"xx\xff\xffxx")

    def test_unknown_objcopy_profile(self):
        with self.assertRaisesRegex(ValueError, "objcopy profile"):
            reconstruct_binary(self.elf(), 0, 6, [])

    def test_overflow_and_overlap(self):
        for start in (1, 5):
            with self.assertRaises(ValueError):
                reconstruct_binary(self.elf(start), 0, 6, self.args)


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
