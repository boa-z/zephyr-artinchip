# SPDX-License-Identifier: Apache-2.0
import copy
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
from check_provenance import validate


class ProvenanceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / "test.c").write_text("/* SPDX-License-Identifier: Apache-2.0 */\n")
        self.data = {"schema_version": 1, "files": [{"path": "test.c", "kind": "new",
                     "license": "Apache-2.0", "license_basis": "original work",
                     "rights_holders": [], "changes": "new", "dependencies": [],
                     "review_status": "reviewed"}]}

    def check(self, data=None, files=None):
        return validate(self.root, self.data if data is None else data,
                        {"test.c"} if files is None else files)

    def test_original(self):
        self.assertEqual(self.check(), [])

    def test_missing_coverage(self):
        self.assertIn("uncovered: other.c", self.check(files={"test.c", "other.c"}))

    def test_unknown_license(self):
        self.data["files"][0]["license"] = "NOASSERTION"
        self.assertTrue(self.check())

    def test_missing_origin(self):
        self.data["files"][0]["kind"] = "derived"
        self.assertTrue(self.check())

    def test_unreviewed_source(self):
        self.data["files"][0]["review_status"] = "review_required"
        self.assertTrue(self.check())

    def test_duplicate(self):
        self.data["files"].append(copy.deepcopy(self.data["files"][0]))
        self.assertTrue(self.check())

    def test_path_escape(self):
        self.data["files"][0]["path"] = "../escape.c"
        self.assertTrue(self.check())

    def test_bad_schema(self):
        self.assertTrue(self.check(data=[]))


if __name__ == "__main__":
    unittest.main()
