# SPDX-License-Identifier: Apache-2.0
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
from instrument_tinyspl import once, changes, apply, SPI, QSPI, BOOT


class PatchTests(unittest.TestCase):
    def test_modes_conflict_before_writes(self):
        with self.assertRaisesRegex(ValueError, "mutually exclusive"):
            apply(Path("missing-reference"), Path("missing-copy"),
                  Path("missing-evidence"), True, True)

    def test_transfer_mode_blocks_even_direct_boot_app(self):
        patched = changes(BOOT, "void boot_app(void) {\n    aicos_dcache_clean();\n    jump();\n}\n",
                          transfer_only=True)
        self.assertLess(patched.index("    return;"), patched.index("    aicos_dcache_clean();"))
        self.assertNotIn("h0_dump", patched)

    def test_ambiguous_context_fails(self):
        for source in ("", "needle needle"):
            with self.assertRaises(ValueError):
                once(source, "needle", "replacement")

    def test_free_remains_conditional(self):
        source = "    buf = malloc(flash->info->page_size + flash->info->oob_size);\n    if (buf)\n        free(buf);\n"
        patched = changes(SPI, source)
        self.assertIn("if (buf) {\n        h0_event(5,", patched)
        self.assertIn("        free(buf);\n    }", patched)
        with self.assertRaises(ValueError):
            changes(SPI, patched)

    def test_changed_stop_inventory_fails(self):
        with self.assertRaises(ValueError):
            changes(QSPI, "    hal_dma_chan_stop(dma_rx);\n")

    def test_reference_and_nested_targets_rejected_before_writes(self):
        with tempfile.TemporaryDirectory() as directory:
            reference = Path(directory) / "sdk"
            reference.mkdir()
            evidence = Path(directory) / "evidence"
            for destination in (reference, reference / "nested", reference.parent):
                with self.assertRaisesRegex(ValueError, "disjoint"):
                    apply(reference, destination, evidence)
            self.assertFalse(evidence.exists())
