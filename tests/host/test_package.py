# SPDX-License-Identifier: Apache-2.0
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
from package_candidate import RAM_START, RAM_END, validate_segments


class PackageTests(unittest.TestCase):
    def segment(self, address=RAM_START, memory_size=1024, file_size=512, flags=5):
        return dict(address=address, memory_size=memory_size, file_size=file_size, flags=flags)

    def test_valid(self):
        self.assertEqual(validate_segments([self.segment()], RAM_START), [])

    def test_reserved_memory(self):
        self.assertTrue(validate_segments([self.segment(RAM_START - 4)], RAM_START))

    def test_overflow(self):
        self.assertTrue(validate_segments([self.segment(RAM_END - 4)], RAM_END - 4))

    def test_bad_entry(self):
        self.assertTrue(validate_segments([self.segment()], RAM_END))

    def test_non_executable_entry(self):
        self.assertTrue(validate_segments([self.segment(flags=6)], RAM_START))

    def test_overlap(self):
        self.assertTrue(validate_segments([self.segment(), self.segment()], RAM_START))

    def test_file_larger_than_memory(self):
        self.assertTrue(validate_segments([self.segment(file_size=2048)], RAM_START))

    def test_empty(self):
        self.assertTrue(validate_segments([], RAM_START))


if __name__ == "__main__":
    unittest.main()
