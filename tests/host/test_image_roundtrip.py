# SPDX-License-Identifier: Apache-2.0
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
import zlib
import struct

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
from image_roundtrip import split_image, reconstruct, compare_images, rehearse
from evidence import record
from test_loader_audit import container_fixture


class RoundtripTests(unittest.TestCase):
    def setUp(self):
        self.data = bytes(container_fixture())
        _, self.parts = split_image(self.data)
        self.chunks = {p["file"]: self.data[p["offset"]:p["offset"] + p["size"]]
                       for p in self.parts}

    def test_lossless_with_nonzero_padding(self):
        data = bytearray(self.data)
        data[-9:] = b"padding!?"
        _, parts = split_image(data)
        chunks = {p["file"]: bytes(data[p["offset"]:p["offset"] + p["size"]]) for p in parts}
        self.assertEqual(reconstruct(bytes(data), parts, chunks), data)

    def test_os_and_opaque_tampering_rejected(self):
        for part in self.parts:
            chunks = self.chunks.copy()
            chunks[part["file"]] = b"X" + chunks[part["file"]][1:]
            with self.assertRaisesRegex(ValueError, "content changed"):
                reconstruct(self.data, self.parts, chunks)

    def test_untrusted_inventory_rejected(self):
        for parts in (self.parts[::-1], self.parts[:-1], [dict(self.parts[0], file="../escape")]):
            with self.assertRaisesRegex(ValueError, "inventory changed"):
                reconstruct(self.data, parts, self.chunks)
        with self.assertRaises(ValueError):
            reconstruct(self.data, self.parts, dict(self.chunks, extra=b""))

    def test_valid_crc_changed_os_is_still_a_difference(self):
        data = bytearray(self.data)
        position = 3584 + 32
        data[position] ^= 1
        struct.pack_into("<I", data, 3072 + 144, zlib.crc32(data[position:position + 8]))
        result = compare_images(self.data, data)
        self.assertFalse(result["byte_identical"])
        self.assertEqual(set(result["component_changes"]), {"image.target.os"})

    def test_padding_change_not_hidden_by_component_hashes(self):
        data = self.data[:-1] + b"X"
        result = compare_images(self.data, data)
        self.assertTrue(result["opaque_or_metadata_changed"])
        self.assertEqual(result["changed_bytes"], 1)

    def test_output_refuses_reuse_and_source_unchanged(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "source.img"
            source.write_bytes(self.data)
            output = Path(directory) / "out"
            with patch("image_roundtrip.BASELINE", record(self.data)["sha256"]):
                report = rehearse(source, output)
                self.assertTrue(report["difference"]["byte_identical"])
                self.assertFalse(report["loadable_image"])
                with self.assertRaises(FileExistsError):
                    rehearse(source, output)
            self.assertEqual(source.read_bytes(), self.data)

    def test_wrong_baseline_writes_nothing(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "source.img"
            source.write_bytes(self.data)
            output = Path(directory) / "out"
            with self.assertRaisesRegex(ValueError, "pinned"):
                rehearse(source, output)
            self.assertFalse(output.exists())
