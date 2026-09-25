# SPDX-License-Identifier: Apache-2.0
import json
from pathlib import Path
import struct
import sys
import tempfile
import unittest
from unittest.mock import patch
import zlib

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
import audit_loader as audit


def container_fixture():
    data = bytearray(4096)
    data[:8] = b"AIC.FW\0\0"
    data[8:12] = b"d13x"
    struct.pack_into("<4I", data, 332, 2048, 1536, 3584, 512)
    for index, name in enumerate(("image.target.spl", "image.updater.spl", "image.target.os")):
        offset = 2048 + index * 512
        data[offset:offset + 8] = b"META\0\0\0\0"
        encoded = name.encode()
        data[offset + 8:offset + 8 + len(encoded)] = encoded
        payload = bytes([index + 1]) * 8
        position = 3584 + 16 * index
        data[position:position + 8] = payload
        struct.pack_into("<4I", data, offset + 136, position, 8, zlib.crc32(payload), 0xffffffff)
    return data


class ContainerTests(unittest.TestCase):
    def test_complete_container(self):
        result = audit.container_components(container_fixture())
        self.assertEqual(set(result), {"image.target.spl", "image.updater.spl", "image.target.os"})
        self.assertEqual(result["image.target.os"]["size"], 8)

    def test_corrupt_payload(self):
        data = container_fixture()
        data[3584] ^= 1
        with self.assertRaisesRegex(ValueError, "CRC mismatch"):
            audit.container_components(data)

    def test_truncated(self):
        with self.assertRaisesRegex(ValueError, "boundaries"):
            audit.container_components(container_fixture()[:-1])

    def test_wrong_platform(self):
        data = container_fixture()
        data[8:12] = b"d21x"
        with self.assertRaisesRegex(ValueError, "unsupported product"):
            audit.container_components(data)

    def test_out_of_bounds_metadata(self):
        data = container_fixture()
        struct.pack_into("<I", data, 332, 0xfffffff0)
        with self.assertRaises(ValueError):
            audit.container_components(data)

    def test_duplicate_names(self):
        data = container_fixture()
        data[2568:2632] = data[2056:2120]
        with self.assertRaisesRegex(ValueError, "duplicate"):
            audit.container_components(data)

    def test_overlapping_payloads(self):
        data = container_fixture()
        data[2560 + 136:2560 + 148] = data[2048 + 136:2048 + 148]
        with self.assertRaisesRegex(ValueError, "overlapping"):
            audit.container_components(data)

    def test_missing_spl(self):
        data = container_fixture()
        data[2056:2120] = b"other" + bytes(59)
        with self.assertRaisesRegex(ValueError, "missing SPL"):
            audit.container_components(data)

    def test_nonterminated_string(self):
        with self.assertRaisesRegex(ValueError, "unterminated"):
            audit.cstring(b"not terminated")

    def test_component_truncation(self):
        data = container_fixture()
        struct.pack_into("<I", data, 2048 + 140, 100000)
        with self.assertRaisesRegex(ValueError, "out-of-range"):
            audit.container_components(data)


class ComparisonTests(unittest.TestCase):
    sections = [{"name": ".text", "start": 0x100, "end": 0x104, "executable": True},
                {"name": ".data", "start": 0x104, "end": 0x108, "executable": False}]

    def test_same_loader(self):
        result = audit.compare_bytes(b"12345678", b"12345678", 0x100, self.sections, [])
        self.assertTrue(result["exact_match"])

    def test_data_difference_is_not_identity(self):
        result = audit.compare_bytes(b"1234X678", b"12345678", 0x100, self.sections,
                                     [{"name": "setting", "start": 0x104, "end": 0x108}])
        self.assertFalse(result["exact_match"])
        self.assertTrue(result["executable_bytes_equal"])
        self.assertEqual(result["differences"][0]["ranges"][0]["symbols"], ["setting"])

    def test_changed_instruction(self):
        result = audit.compare_bytes(b"X2345678", b"12345678", 0x100, self.sections, [])
        self.assertFalse(result["executable_bytes_equal"])

    def test_truncated_loader(self):
        with self.assertRaisesRegex(ValueError, "size mismatch"):
            audit.compare_bytes(b"123", b"1234", 0x100, self.sections, [])

    def test_unmodeled_changed_byte(self):
        with self.assertRaisesRegex(ValueError, "outside modeled"):
            audit.compare_bytes(b"1234567X", b"12345678", 0x100, self.sections[:1], [])

    def test_ambiguous_embedded_loader(self):
        with self.assertRaisesRegex(ValueError, "absent or ambiguous"):
            audit.unique_offset(b"xxABCyyABC", b"ABC")

    def test_missing_embedded_loader(self):
        with self.assertRaises(ValueError):
            audit.unique_offset(b"old loader", b"new loader")

    def test_bss_and_adjacency(self):
        loader = [{"start": 0x100, "end": 0x200, "name": "PT_LOAD including BSS"}]
        self.assertEqual(len(audit.overlaps([{"start": 0x1f0, "end": 0x210}], loader)), 1)
        self.assertEqual(audit.overlaps([{"start": 0x200, "end": 0x210}], loader), [])


class OutputTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.args = ["--product", str(self.root / "product"), "--loader", str(self.root / "loader"),
                     "--candidates", str(self.root / "candidates")]

    def test_output_cannot_change_source(self):
        with self.assertRaisesRegex(ValueError, "outside every input"):
            audit.main(self.args + ["--output", str(self.root / "product/report.json")])

    def test_output_cannot_overwrite_evidence(self):
        output = self.root / "report.json"
        output.write_text("preserve")
        with self.assertRaisesRegex(ValueError, "new audit output"):
            audit.main(self.args + ["--output", str(output)])
        self.assertEqual(output.read_text(), "preserve")

    def test_blocked_audit_has_nonzero_exit_and_preserves_report(self):
        output = self.root / "report.json"
        result = {"audit_status": "BLOCKED", "blockers": ["identity mismatch"], "loadable_image": False}
        with patch.object(audit, "audit", return_value=result):
            self.assertEqual(audit.main(self.args + ["--output", str(output)]), 2)
        self.assertFalse(json.loads(output.read_text())["loadable_image"])


if __name__ == "__main__":
    unittest.main()
