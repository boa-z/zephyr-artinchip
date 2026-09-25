# SPDX-License-Identifier: Apache-2.0
import copy
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
        def cases(name):
            if name == "artinchip.kernel":
                return [name + ".artinchip_kernel." + case for case in
                        ("owned_memory", "timer_preemption", "timeout", "thread_semaphore", "module")]
            if name == "artinchip.fpu":
                return [name + ".artinchip_fpu.context_registers"]
            if name.startswith("artinchip.clic."):
                return [name + ".clic_mmio." + case for case in
                        ("irq_edges_enable_pending_shv", "invalid_width", "level_clamp",
                         "priority_widths", "layout_and_threshold")]
            return [name]
        for directory, runtime in ((self.d13x, False), (self.qemu, True)):
            current = names | ({"artinchip.bringup.no_assert", "artinchip.clic.legacy",
                               "artinchip.clic.generic", "artinchip.clic.nuclei"} if runtime else set())
            status = "passed" if runtime else "not run"
            (directory / "twister.json").write_text(json.dumps({"testsuites": [
                {"name": name, "status": status,
                 "platform": "qemu_riscv32/qemu_virt_riscv32" if runtime else "d50t_2_lite/d133ecs",
                 "testcases": [{"identifier": case, "status": status} for case in cases(name)]}
                for name in current]}))
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
                        "source_at_build": {"head": "a" * 40, "dirty": False},
                        "board": "d50t_2_lite/d133ecs",
                        "dependency_at_build": {"identity": {"head": "c" * 40}},
                        "binary_command": {"arguments": ["-O", "binary"]},
                        "loadable_image": False,
                        "hardware_validation": "pending"}
            receipt = {"schema_version": 1, "status": "PASS",
                       **{key: manifest[key] for key in
                          ("application", "board", "source_at_build",
                           "dependency_at_build", "binary_command")},
                       "files": {"zephyr/" + name: payload[name] for name in
                                 ("zephyr.elf", "zephyr.bin", "zephyr.map", ".config", "zephyr.dts")}}
            receipt["files"]["compile_commands.json"] = payload["compile_commands.json"]
            data = json.dumps(receipt).encode()
            (p / "build-provenance.json").write_bytes(data)
            payload["build-provenance.json"] = evidence.record(data)
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

    def test_twister_identity_and_coverage(self):
        for directory, runtime in ((self.qemu, True), (self.d13x, False)):
            original = json.loads((directory / "twister.json").read_text())
            evidence.check_suite(original, runtime)
            for mutation in ("platform", "duplicate_suite", "missing_case", "duplicate_case",
                             "wrong_case", "failed_case", "wrong_execution_scope", "filtered_required"):
                changed = copy.deepcopy(original)
                suites = changed["testsuites"]
                kernel = next(s for s in suites if s["name"] == "artinchip.kernel")
                if mutation == "platform":
                    kernel["platform"] = "other_board"
                elif mutation == "duplicate_suite":
                    suites.append(copy.deepcopy(kernel))
                elif mutation == "missing_case":
                    kernel["testcases"].pop()
                elif mutation == "duplicate_case":
                    kernel["testcases"][-1] = kernel["testcases"][0]
                elif mutation == "wrong_case":
                    kernel["testcases"][0]["identifier"] = "unrelated"
                elif mutation == "failed_case":
                    kernel["testcases"][0]["status"] = "failed"
                elif mutation == "filtered_required":
                    kernel["status"] = "filtered"
                else:
                    kernel["status"] = "not run" if runtime else "passed"
                with self.subTest(runtime=runtime, mutation=mutation), self.assertRaises(ValueError):
                    evidence.check_suite(changed, runtime)

    def test_expected_d13x_filter_is_not_execution(self):
        data = json.loads((self.d13x / "twister.json").read_text())
        data["testsuites"].append({"name": "artinchip.bringup.no_assert",
                                   "platform": "d50t_2_lite/d133ecs",
                                   "status": "filtered", "testcases": []})
        evidence.check_suite(data, False)
        data["testsuites"][-1]["name"] = "unknown.filtered"
        with self.assertRaises(ValueError):
            evidence.check_suite(data, False)

    def rehash_json(self, name, mutate):
        with zipfile.ZipFile(self.archive) as z:
            contents = {n: z.read(n) for n in z.namelist()}
        data = json.loads(contents[name])
        mutate(data)
        contents[name] = json.dumps(data).encode()
        if name != "evidence.json":
            index = json.loads(contents["evidence.json"])
            index["files"][name] = evidence.record(contents[name])
            contents["evidence.json"] = json.dumps(index).encode()
        with zipfile.ZipFile(self.archive, "w") as z:
            for n, value in contents.items():
                z.writestr(n, value)

    def test_download_rechecks_rehashed_gate_reports(self):
        self.stage()
        original = self.archive.read_bytes()
        changes = [
            ("qemu/twister.json", lambda d: d["testsuites"][0].update(platform="wrong")),
            ("d13x/twister.json", lambda d: d["testsuites"][0].update(status="passed")),
            ("environment.json", lambda d: d.update(status="FAIL")),
            ("negative/probes.json", lambda d: d["missing_signal"].update(exit_code=0)),
            ("negative/probes.json", lambda d: d["frozen_cpu"].update(timed_out=False))]
        for name, mutate in changes:
            self.archive.write_bytes(original)
            self.rehash_json(name, mutate)
            with self.subTest(name=name), self.assertRaises(ValueError):
                evidence.verify_archive(self.archive)

    def test_download_rejects_index_misbinding(self):
        self.stage()
        original = self.archive.read_bytes()
        for field, value in (("source_at_build", "b" * 40), ("elf", {}),
                             ("manifest", "candidates/fpu/candidate.json"),
                             ("runtime_scope", "PASS on D13x"),
                             ("hardware_validation", "verified"), ("expected_output", "PASS")):
            self.archive.write_bytes(original)
            self.rehash_json("evidence.json",
                             lambda d: d["candidates"]["kernel"].update({field: value}))
            with self.subTest(field=field), self.assertRaises(ValueError):
                evidence.verify_archive(self.archive)

    def test_download_rejects_rehashed_wrong_application(self):
        self.stage()
        self.rehash_json("candidates/kernel/candidate.json", lambda d: d.update(application="fpu"))
        with self.assertRaises(ValueError):
            evidence.verify_archive(self.archive)

    def test_download_rejects_mixed_sources_even_with_matching_index(self):
        self.stage()
        receipt_name = "candidates/kernel/build-provenance.json"
        self.rehash_json(receipt_name, lambda d: d["source_at_build"].update(head="b" * 40))
        with zipfile.ZipFile(self.archive) as archive:
            receipt_record = evidence.record(archive.read(receipt_name))
        self.rehash_json("candidates/kernel/candidate.json",
                         lambda d: d["source_at_build"].update(head="b" * 40))
        self.rehash_json("candidates/kernel/candidate.json",
                         lambda d: d["files"].update({"build-provenance.json": receipt_record}))
        self.rehash_json("evidence.json",
                         lambda d: d["candidates"]["kernel"].update(source_at_build="b" * 40))
        with self.assertRaisesRegex(ValueError, "different source"):
            evidence.verify_archive(self.archive)

    def test_stage_rejects_receipt_mismatch(self):
        path = self.candidates / "kernel/candidate.json"
        original = json.loads(path.read_text())
        for field, value in (("source_at_build", {"head": "b" * 40, "dirty": False}),
                             ("board", "other_board"),
                             ("dependency_at_build", {}), ("binary_command", {})):
            changed = copy.deepcopy(original)
            changed[field] = value
            path.write_text(json.dumps(changed))
            with self.subTest(field=field), self.assertRaisesRegex(ValueError, "receipt"):
                self.stage()
            self.assertFalse(self.archive.exists())

    def test_download_rejects_relabelled_source_with_matching_index(self):
        self.stage()
        for app in sorted(evidence.APPLICATIONS):
            self.rehash_json(f"candidates/{app}/candidate.json",
                             lambda d: d["source_at_build"].update(head="b" * 40))
        self.rehash_json("evidence.json", lambda d: [
            item.update(source_at_build="b" * 40) for item in d["candidates"].values()])
        with self.assertRaisesRegex(ValueError, "receipt"):
            evidence.verify_archive(self.archive)

    def test_download_rejects_payload_rehashed_only_at_package_time(self):
        self.stage()
        original = self.archive.read_bytes()
        for filename in ("zephyr.elf", "zephyr.bin", "zephyr.map", ".config",
                         "zephyr.dts", "compile_commands.json"):
            self.archive.write_bytes(original)
            name = f"candidates/kernel/{filename}"
            self.rewrite(alter=name)
            digest = evidence.record(b"corrupt")
            self.rehash_json("candidates/kernel/candidate.json",
                             lambda d: d["files"].update({filename: digest}))
            def update_index(data):
                data["files"][name] = digest
                if filename == "zephyr.elf":
                    data["candidates"]["kernel"]["elf"] = digest
            self.rehash_json("evidence.json", update_index)
            with self.subTest(filename=filename), self.assertRaisesRegex(ValueError, "receipt"):
                evidence.verify_archive(self.archive)

    def test_receipt_requires_success_and_clean_target_build(self):
        path = self.candidates / "kernel"
        manifest = json.loads((path / "candidate.json").read_text())
        original = json.loads((path / "build-provenance.json").read_text())
        mutations = (lambda d: d.update(status="FAIL"),
                     lambda d: d.update(schema_version=0),
                     lambda d: d.update(board="other_board"),
                     lambda d: d["source_at_build"].update(dirty=True))
        for number, mutate in enumerate(mutations):
            receipt = copy.deepcopy(original)
            mutate(receipt)
            with self.subTest(mutation=number), self.assertRaisesRegex(ValueError, "receipt"):
                evidence.check_candidate_receipt(manifest, receipt)

    def test_receipt_binds_full_source_snapshot_not_only_commit(self):
        path = self.candidates / "kernel"
        manifest = json.loads((path / "candidate.json").read_text())
        receipt = json.loads((path / "build-provenance.json").read_text())
        manifest["source_at_build"]["runtime_files"] = {"src/module.c": "changed"}
        with self.assertRaisesRegex(ValueError, "receipt: source_at_build"):
            evidence.check_candidate_receipt(manifest, receipt)

    def test_download_rejects_inconsistent_status_claims(self):
        self.stage()
        original = self.archive.read_bytes()
        for field, value in (("job_status", "failure"), ("hardware_validation", "verified"),
                             ("upstream_ready", "yes"), ("software_audit", "unknown")):
            self.archive.write_bytes(original)
            self.rehash_json("evidence.json", lambda d: d.update({field: value}))
            with self.subTest(field=field), self.assertRaises(ValueError):
                evidence.verify_archive(self.archive)


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
