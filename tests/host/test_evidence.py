# SPDX-License-Identifier: Apache-2.0
import json
from pathlib import Path
import sys
import tempfile
import unittest
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
import evidence
from build_provenance import verify_binary


class EvidenceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.candidates = self.root / "candidates"
        self.qemu = self.root / "qemu"
        self.d13x = self.root / "d13x"
        self.logs = self.root / "logs"
        self.negative = self.root / "negative"
        self.negative.mkdir()
        (self.negative / "probes.json").write_text(json.dumps({"status":"PASS", "missing_signal":{"exit_code":1}, "frozen_cpu":{"exit_code":124,"timed_out":True}}))
        for p in (self.qemu, self.d13x, self.logs):
            p.mkdir()
        (self.logs / "build.log").write_text("retained failure or success log")
        (self.logs / ".env").write_text("must never be collected")
        self.environment = self.root / "environment.json"
        self.environment.write_text('{"status":"PASS"}')
        names = {"artinchip.bringup", "artinchip.kernel", "artinchip.fpu"}
        for directory, runtime in ((self.d13x, False), (self.qemu, True)):
            current = names | ({"artinchip.bringup.no_assert", "artinchip.clic.legacy",
                               "artinchip.clic.generic", "artinchip.clic.nuclei"} if runtime else set())
            status = "passed" if runtime else "not run"
            (directory / "twister.json").write_text(json.dumps({"testsuites": [
                {"name": name, "status": status, "testcases": [{"status": status}]} for name in current]}))
        for application in evidence.APPLICATIONS:
            p = self.candidates / application
            payload = {}
            for name in evidence.PAYLOAD | {"patches/test.patch"}:
                target = p / name
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(b"fixture")
                payload[name] = evidence.record(b"fixture")
            manifest = {"schema_version": 2, "application": application, "files": payload,
                        "patches": {"patches": [{"path": "patches/zephyr/test.patch"}]},
                        "source_at_build": {"head": "a" * 40}, "loadable_image": False,
                        "hardware_validation": "pending"}
            (p / "candidate.json").write_text(json.dumps(manifest))
        self.archive = self.root / "evidence.zip"

    def stage(self, status="success"):
        evidence.stage(self.archive, status, self.qemu, self.d13x,
                       self.candidates, self.logs, self.environment, self.negative)

    def rewrite(self, omit=None, alter=None):
        with zipfile.ZipFile(self.archive) as z:
            contents = {name: z.read(name) for name in z.namelist() if name != omit}
        if alter:
            contents[alter] = b"corrupt"
        with zipfile.ZipFile(self.archive, "w") as z:
            for name, value in contents.items():
                z.writestr(name, value)

    def test_zip_roundtrip_includes_hidden_config(self):
        self.stage()
        with zipfile.ZipFile(self.archive) as z:
            for app in evidence.APPLICATIONS:
                self.assertEqual(z.read(f"candidates/{app}/.config"), b"fixture")
            self.assertFalse(any(name.endswith(".env") for name in z.namelist()))
        self.assertEqual(evidence.verify_archive(self.archive)["software_audit"], "pass")

    def test_missing_downloaded_config(self):
        self.stage()
        self.rewrite(omit="candidates/bringup/.config")
        with self.assertRaises(ValueError):
            evidence.verify_archive(self.archive)

    def test_changed_downloaded_payload(self):
        self.stage()
        self.rewrite(alter="candidates/fpu/zephyr.bin")
        with self.assertRaises(ValueError):
            evidence.verify_archive(self.archive)

    def test_missing_candidate_is_not_success(self):
        (self.candidates / "kernel/zephyr.elf").unlink()
        with self.assertRaises(FileNotFoundError):
            self.stage()
        self.assertFalse(self.archive.exists())

    def test_failure_archive_logs_only(self):
        self.stage("failure")
        with zipfile.ZipFile(self.archive) as z:
            self.assertFalse(any(name.startswith("candidates/") for name in z.namelist()))
        self.assertEqual(evidence.verify_archive(self.archive)["software_audit"], "failed")

    def test_secret_not_on_candidate_allowlist(self):
        p = self.candidates / "bringup/candidate.json"
        manifest = json.loads(p.read_text())
        manifest["files"][".env"] = evidence.record(b"secret")
        p.write_text(json.dumps(manifest))
        with self.assertRaises(ValueError):
            self.stage()

    def test_path_traversal(self):
        for name in ("../escape", "/absolute", "C:/secret", "a\\b"):
            with self.subTest(name=name), self.assertRaises(ValueError):
                evidence.safe_name(name)


class BinaryTests(unittest.TestCase):
    def test_bin_mismatch_and_truncation(self):
        with tempfile.TemporaryDirectory() as directory:
            build = Path(directory)
            (build / "zephyr").mkdir()
            (build / "zephyr/zephyr.elf").write_bytes(b"ELF placeholder")
            command = {"cwd": str(build / "zephyr"), "tool": sys.executable,
                       "arguments": ["-c", "import pathlib,sys;pathlib.Path(sys.argv[-1]).write_bytes(b'expected')"]}
            for value in (b"changed!", b"exp"):
                (build / "zephyr/zephyr.bin").write_bytes(value)
                with self.assertRaisesRegex(ValueError, "ELF/bin"):
                    verify_binary(build, command)
            (build / "zephyr/zephyr.bin").write_bytes(b"expected")
            verify_binary(build, command)


if __name__ == "__main__":
    unittest.main()
