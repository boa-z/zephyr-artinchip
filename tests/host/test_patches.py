# SPDX-License-Identifier: Apache-2.0
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
import apply_patches


class PatchTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.tree = self.root / "tree"
        self.tree.mkdir()
        self.git("init", "-q")
        (self.tree / "source.c").write_text("original\n")
        self.git("add", "source.c")
        self.git("-c", "user.name=Fixture", "-c", "user.email=fixture@example.invalid",
                 "-c", "commit.gpgsign=false", "commit", "-qm", "fixture")
        base = self.git("rev-parse", "HEAD")
        (self.tree / "source.c").write_text("patched\n")
        blob = self.git("hash-object", "--path=source.c", "source.c")
        directory = self.root / "patches/zephyr"
        directory.mkdir(parents=True)
        self.patch = directory / "fixture.patch"
        self.patch.write_bytes(b"fixture")
        self.series = {"base": base, "patches": [{"path": "patches/zephyr/fixture.patch",
                       "sha256": hashlib.sha256(b"fixture").hexdigest()}],
                       "files": {"source.c": blob}}
        (directory / "series.json").write_text(json.dumps(self.series))
        mocked = patch.object(apply_patches, "ROOT", self.root)
        mocked.start()
        self.addCleanup(mocked.stop)

    def git(self, *args):
        return subprocess.check_output(["git", "-C", str(self.tree), *args], text=True).strip()

    def test_exact_patch(self):
        self.assertEqual(apply_patches.verify(self.tree), self.series)

    def test_unpatched(self):
        self.git("restore", "source.c")
        with self.assertRaises(ValueError):
            apply_patches.verify(self.tree)

    def test_extra_change(self):
        (self.tree / "other.c").write_text("unexpected\n")
        with self.assertRaises(ValueError):
            apply_patches.verify(self.tree)

    def test_wrong_contents(self):
        (self.tree / "source.c").write_text("wrong\n")
        with self.assertRaises(ValueError):
            apply_patches.verify(self.tree)

    def test_staged_change(self):
        self.git("add", "source.c")
        with self.assertRaises(ValueError):
            apply_patches.verify(self.tree)

    def test_patch_tampering(self):
        self.patch.write_bytes(b"changed")
        with self.assertRaises(ValueError):
            apply_patches.verify(self.tree)


if __name__ == "__main__":
    unittest.main()
