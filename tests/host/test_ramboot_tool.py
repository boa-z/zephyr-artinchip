# SPDX-License-Identifier: Apache-2.0
import contextlib
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
from audit_ramboot_tool import audit, main


class RambootToolTests(unittest.TestCase):
    def test_help_strings_do_not_establish_capability(self):
        for data in (b"", b"MZramboot ram_boot 0x%lx %s %d", b"\0" * 4096):
            report, code = audit(data)
            self.assertEqual(code, 1)
            self.assertEqual(report["status"], "UNKNOWN")
            self.assertFalse(report["loadable_image"])
            self.assertNotIn("reviewed_path", report)

    def test_recognized_identity_never_opens_hardware_gate(self):
        # Simulate only profile identity; this is not a test of vendor code.
        import hashlib
        data = b"test-only profile"
        with patch("audit_ramboot_tool.REVIEWED_SHA256", hashlib.sha256(data).hexdigest()):
            report, code = audit(data)
            self.assertEqual(code, 2)
            self.assertEqual(report["status"], "BLOCKED")
            self.assertFalse(report["loadable_image"])
            self.assertFalse(report["recovery_verified"])
            changed, changed_code = audit(data + b"changed")
            self.assertEqual(changed_code, 1)
            self.assertNotIn("reviewed_path", changed)

    def test_missing_input_returns_nonzero_json(self):
        with tempfile.TemporaryDirectory() as directory, contextlib.redirect_stdout(io.StringIO()) as output:
            self.assertEqual(main([str(Path(directory) / "missing.exe")]), 1)
            self.assertEqual(json.loads(output.getvalue())["status"], "ERROR")

    def test_input_is_read_only_and_not_executed(self):
        with tempfile.TemporaryDirectory() as directory, contextlib.redirect_stdout(io.StringIO()):
            source = Path(directory) / "tool.py"
            data = b'raise RuntimeError("must never execute")\n'
            source.write_bytes(data)
            self.assertEqual(main([str(source)]), 1)
            self.assertEqual(source.read_bytes(), data)
