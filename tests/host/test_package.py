# SPDX-License-Identifier: Apache-2.0
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
from package_candidate import RAM_START, RAM_END, compiler_from_cache, validate_segments


class PackageTests(unittest.TestCase):
    def test_compiler_cache_string(self):
        cache = "CMAKE_C_COMPILER:STRING=C:/SDK path/bin/riscv64-zephyr-elf-gcc.exe\r\n"
        self.assertEqual(compiler_from_cache(cache),
                         Path("C:/SDK path/bin/riscv64-zephyr-elf-gcc.exe"))

    def test_compiler_cache_filepath(self):
        self.assertEqual(compiler_from_cache("CMAKE_C_COMPILER:FILEPATH=/sdk/bin/gcc\n"),
                         Path("/sdk/bin/gcc"))

    def test_compiler_cache_missing_or_empty(self):
        for cache in ("", "CMAKE_C_COMPILER_AR:FILEPATH=/sdk/bin/ar\n",
                      "CMAKE_C_COMPILER:STRING=\n", "CMAKE_C_COMPILER:STRING=  \n"):
            with self.subTest(cache=cache), self.assertRaises(ValueError):
                compiler_from_cache(cache)

    def test_compiler_cache_ambiguous(self):
        cache = "CMAKE_C_COMPILER:STRING=/sdk/bin/gcc\nCMAKE_C_COMPILER:FILEPATH=/other/gcc\n"
        with self.assertRaises(ValueError):
            compiler_from_cache(cache)

    def segment(self, address=RAM_START, memory_size=1024, file_size=512, flags=5):
        return dict(address=address, memory_size=memory_size, file_size=file_size, flags=flags)

    def test_valid(self):
        self.assertEqual(validate_segments([self.segment()], RAM_START), [])

    def test_entry_in_zero_filled_tail(self):
        self.assertTrue(validate_segments([self.segment()], RAM_START + 768))

    def test_entry_misaligned(self):
        self.assertTrue(validate_segments([self.segment()], RAM_START + 1))

    def test_compressed_entry_two_byte_alignment(self):
        self.assertEqual(validate_segments([self.segment()], RAM_START + 2), [])

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
