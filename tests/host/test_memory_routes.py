# SPDX-License-Identifier: Apache-2.0
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
from audit_loader_memory import route_requirements


class MemoryRouteTests(unittest.TestCase):
    def test_nand_excludes_only_ram_staging(self):
        all_routes = route_requirements("all")
        nand = route_requirements("nand-fit")
        self.assertEqual([s for s in all_routes if s not in nand],
                         ["RAM-only staging and compatible RAM FIT executor are not verified."])
        self.assertTrue(any("DMA" in s for s in nand))
        self.assertTrue(any("Recovery" in s for s in nand))

    def test_unknown_route_cannot_skip_gates(self):
        for route in ("", "nand", "safe", None):
            with self.assertRaises(ValueError):
                route_requirements(route)
