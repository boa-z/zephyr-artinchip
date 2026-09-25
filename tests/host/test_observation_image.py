# SPDX-License-Identifier: Apache-2.0
import hashlib
from pathlib import Path
import struct
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
from observation_image import wrap_loader, verify_wrapped, check_aic, checksum


def block(raw, prefix=False):
    private = 256 + ((len(raw) + 255) & ~255)
    sign = private + 256
    data = bytearray(sign)
    data[:4] = b"AIC "
    for offset, value in ((8, 0x10001), (12, sign + 16), (20, len(raw)),
                          (24, 0x40c00000), (28, 0x40c00100), (40, sign),
                          (44, 16), (64, private), (68, 128), (80, 23552 if prefix else 0)):
        struct.pack_into("<I", data, offset, value)
    data[256:256 + len(raw)] = raw
    data += hashlib.md5(data[8:]).digest()
    struct.pack_into("<I", data, 4, checksum(data))
    return bytes(data)


class ObservationTests(unittest.TestCase):
    def setUp(self):
        self.raw = b"old!" * 80
        prefix = block(b"", True)
        self.original = prefix + bytes(23552 - len(prefix)) + block(self.raw)

    def test_exact_baseline_roundtrip(self):
        self.assertEqual(wrap_loader(self.original, self.raw, self.raw), self.original)

    def test_changed_size_preserves_pbp_and_resources(self):
        for raw in (b"new!" * 30, b"new!" * 140):
            result = wrap_loader(self.original, self.raw, raw)
            verify_wrapped(self.original, result, raw)
            self.assertEqual(result[:23552], self.original[:23552])
            check_aic(result[23552:])

    def test_changed_pbp_and_payload_rejected(self):
        raw = b"new!" * 60
        good = wrap_loader(self.original, self.raw, raw)
        for offset in (100, 23552 + 260, len(good) - 1):
            bad = bytearray(good)
            bad[offset] ^= 1
            with self.assertRaises(ValueError):
                verify_wrapped(self.original, bad, raw)

    def test_unknown_signature_and_wrong_loader_rejected(self):
        bad = bytearray(self.original)
        struct.pack_into("<I", bad, 23552 + 32, 1)
        with self.assertRaises(ValueError):
            wrap_loader(bad, self.raw, b"new!")
        with self.assertRaises(ValueError):
            wrap_loader(self.original, b"wrong", b"new!")
