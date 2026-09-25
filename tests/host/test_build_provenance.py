# SPDX-License-Identifier: Apache-2.0
import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
import build_provenance as bp
from environment import git_identity


class ReceiptTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.build = Path(self.temp.name).resolve()
        for name in bp.PAYLOADS:
            p = self.build / name
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_bytes(b"original")
        self.source = {"path": str(bp.ROOT), "head": "a" * 40, "dirty": False,
                       "runtime_files": {"src/module.c": "original"}}
        self.dependency = {"identity": {"path": str(self.build / "dependency")}, "patches": "original"}
        self.receipt = {"schema_version": 1, "status": "PASS", "build": str(self.build),
                        "application": "bringup", "source_at_build": self.source,
                        "dependency_at_build": self.dependency, "tools": {"objcopy": {"path": "objcopy"}},
                        "binary_command": {}, "linked_files": {},
                        "files": {name: bp.file_record(self.build / name) for name in bp.PAYLOADS}}
        self.write_receipt()
        self.mocks = {}
        for name, result in {"source_snapshot": self.source, "dependency_snapshot": self.dependency,
                             "validate_build_identity": "cache", "build_tools": self.receipt["tools"],
                             "linked_files": {}, "binary_command": {}, "verify_binary": None}.items():
            mock = patch.object(bp, name, return_value=copy.deepcopy(result))
            self.mocks[name] = mock.start()
            self.addCleanup(mock.stop)

    def write_receipt(self):
        (self.build / "build-provenance.json").write_text(json.dumps(self.receipt))

    def test_valid_receipt(self):
        self.assertEqual(bp.verify_receipt(self.build), self.receipt)

    def test_collection_identity_does_not_replace_build(self):
        self.mocks["source_snapshot"].return_value["head"] = "b" * 40
        self.assertEqual(bp.verify_receipt(self.build)["source_at_build"]["head"], "a" * 40)

    def test_old_build_new_firmware_source(self):
        self.mocks["source_snapshot"].return_value["runtime_files"]["src/module.c"] = "changed"
        with self.assertRaisesRegex(ValueError, "firmware sources"):
            bp.verify_receipt(self.build)

    def test_old_build_new_patch(self):
        self.mocks["dependency_snapshot"].return_value["patches"] = "changed"
        with self.assertRaisesRegex(ValueError, "patch state"):
            bp.verify_receipt(self.build)

    def test_foreign_module(self):
        self.receipt["source_at_build"]["path"] = str(self.build)
        self.write_receipt()
        with self.assertRaisesRegex(ValueError, "checkout identity"):
            bp.verify_receipt(self.build)

    def test_missing_receipt(self):
        (self.build / "build-provenance.json").unlink()
        with self.assertRaises(FileNotFoundError):
            bp.verify_receipt(self.build)

    def test_changed_payloads(self):
        for name in ("zephyr/.config", "zephyr/zephyr.elf", "zephyr/zephyr.map", "zephyr/zephyr.bin"):
            with self.subTest(name=name):
                p = self.build / name
                original = p.read_bytes()
                try:
                    p.write_bytes(b"truncated")
                    with self.assertRaisesRegex(ValueError, "payload changed"):
                        bp.verify_receipt(self.build)
                finally:
                    p.write_bytes(original)

    def test_changed_linked_input(self):
        self.mocks["linked_files"].return_value = {"inside/build/precompiled.a": "changed"}
        with self.assertRaisesRegex(ValueError, "linked inputs"):
            bp.verify_receipt(self.build)

    def test_failed_source_read(self):
        self.mocks["source_snapshot"].side_effect = ValueError("cannot read Git source identity")
        with self.assertRaises(ValueError):
            bp.verify_receipt(self.build)


class MapTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / "SDK path/lib").mkdir(parents=True)
        (self.root / "SDK path/lib/libgcc.a").touch()
        (self.root / "direct.obj").touch()
        self.text = ("Archive member included to satisfy reference by file (symbol)\n\n"
                     "SDK path/lib/libgcc.a(_muldi3.o)\n  reference (symbol)\n\n"
                     "Discarded input sections\n\nLOAD direct.obj\nLOAD SDK path/lib/libgcc.a\n")

    def test_spaces_and_crlf(self):
        members, objects = bp.map_inputs(self.text.replace("\n", "\r\n"), self.root)
        self.assertEqual(members, [((self.root / "SDK path/lib/libgcc.a").resolve(), "_muldi3.o")])
        self.assertEqual(objects, [(self.root / "direct.obj").resolve()])

    def test_missing_archive(self):
        (self.root / "SDK path/lib/libgcc.a").unlink()
        with self.assertRaises(FileNotFoundError):
            bp.map_inputs(self.text, self.root)

    def test_unparsed_member(self):
        with self.assertRaises(ValueError):
            bp.map_inputs(self.text.replace("libgcc.a(_muldi3.o)", "unparsed.lib(member)"), self.root)

    def test_unrelated_object_not_audited_as_linked(self):
        (self.root / "unlinked.obj").touch()
        _, objects = bp.map_inputs(self.text, self.root)
        self.assertNotIn(self.root / "unlinked.obj", objects)

    def test_local_archive_is_included(self):
        members, _ = bp.map_inputs(self.text, self.root)
        # Windows runner TEMP can use an alias/junction while map_inputs returns
        # resolved paths. Compare both sides in the same canonical namespace.
        self.assertTrue(members[0][0].is_relative_to(self.root.resolve()))

    def test_build_path_alias_keeps_local_archive(self):
        alias = self.root / "SDK path" / ".."
        members, objects = bp.map_inputs(self.text, alias)
        self.assertEqual(members, [((self.root / "SDK path/lib/libgcc.a").resolve(), "_muldi3.o")])
        self.assertEqual(objects, [(self.root / "direct.obj").resolve()])

    def test_unsafe_member(self):
        with self.assertRaises(ValueError):
            bp.map_inputs(self.text.replace("_muldi3.o", "../escape.o"), self.root)


class GitIdentityTests(unittest.TestCase):
    def test_git_status_error_is_not_clean(self):
        with patch("environment.run", side_effect=[
            {"code": 0, "stdout": "a" * 40, "stderr": ""},
            {"code": 128, "stdout": "", "stderr": "failed"},
        ]):
            with self.assertRaises(ValueError):
                git_identity(Path("."))


if __name__ == "__main__":
    unittest.main()
