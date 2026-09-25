# SPDX-License-Identifier: Apache-2.0
"""Stage allowlisted evidence into one ZIP and verify bytes after downloading."""
import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import sys
import zipfile

APPLICATIONS = {"bringup", "kernel", "fpu"}
PAYLOAD = {".config", "zephyr.elf", "zephyr.bin", "zephyr.map", "zephyr.dts",
           "compile_commands.json", "build-provenance.json", "west-frozen.yml",
           "boot-contract.md", "validation.md", "patches/README.md", "patches/series.json"}
LOGS = {"twister.json", "testplan.json", "twister.xml", "twister_report.xml",
        "twister_suite_report.xml", "handler.log", "build.log", "twister.log", "probes.json", "missing-signal.log", "frozen-cpu.log"}


def record(data):
    return {"size": len(data), "sha256": hashlib.sha256(data).hexdigest()}


def safe_name(name):
    path = PurePosixPath(name)
    if path.is_absolute() or ".." in path.parts or "\\" in name or ":" in name:
        raise ValueError(f"unsafe evidence path: {name}")
    return name


def candidate_records(manifest):
    patches = {"patches/" + PurePosixPath(p["path"]).name for p in manifest["patches"]["patches"]}
    files = manifest["files"]
    if set(files) != PAYLOAD | patches or manifest.get("schema_version") != 2:
        raise ValueError("candidate inventory differs from explicit payload allowlist")
    if manifest["loadable_image"] or manifest["hardware_validation"] != "pending":
        raise ValueError("unexpected candidate hardware claim")
    for name in files:
        safe_name(name)
    return files


def check_suite(data, runtime):
    suites = data["testsuites"]
    selected = [s for s in suites if s["status"] != "filtered"]
    expected = {"artinchip.bringup", "artinchip.kernel", "artinchip.fpu"}
    if runtime:
        expected |= {"artinchip.bringup.no_assert", "artinchip.clic.legacy",
                     "artinchip.clic.generic", "artinchip.clic.nuclei"}
    if {s["name"] for s in selected} != expected:
        raise ValueError("unexpected selected Twister scenarios")
    status = "passed" if runtime else "not run"
    if any(s["status"] != status or not s["testcases"] or
           any(c["status"] != status for c in s["testcases"]) for s in selected):
        raise ValueError("Twister gate contains failed or unexecuted cases")


def stage(output, status, qemu, d13x, candidates, logs, environment, negative):
    if output.exists():
        raise ValueError("archive must use a new output path")
    success = status == "success"
    files = {}
    for label, source in (("qemu", qemu), ("d13x", d13x), ("negative", negative)):
        if success and label != "negative":
            check_suite(json.loads((source / "twister.json").read_text()), label == "qemu")
        if source.exists():
            for path in source.rglob("*"):
                if path.is_file() and path.name in LOGS:
                    files[f"{label}/{path.relative_to(source).as_posix()}"] = path.read_bytes()
    # Only the dedicated log directory is accepted; never traverse the workspace.
    if logs.exists():
        for path in logs.glob("*.log"):
            files["logs/" + path.name] = path.read_bytes()
    index = {}
    if success:
        probes = json.loads((negative / "probes.json").read_text())
        if (probes["status"] != "PASS" or probes["missing_signal"]["exit_code"] == 0 or
                probes["frozen_cpu"]["exit_code"] != 124 or not probes["frozen_cpu"]["timed_out"]):
            raise ValueError("negative runtime probes did not meet their failure expectations")
        env = json.loads(environment.read_text())
        if env["status"] != "PASS":
            raise ValueError("environment gate did not pass")
        files["environment.json"] = environment.read_bytes()
        for application in sorted(APPLICATIONS):
            directory = candidates / application
            manifest = json.loads((directory / "candidate.json").read_text())
            if manifest["application"] != application:
                raise ValueError("candidate application mismatch")
            for name, expected in candidate_records(manifest).items():
                data = (directory / name).read_bytes()
                if record(data) != expected:
                    raise ValueError(f"candidate integrity mismatch: {application}/{name}")
                files[f"candidates/{application}/{name}"] = data
            files[f"candidates/{application}/candidate.json"] = (directory / "candidate.json").read_bytes()
            index[application] = {"manifest": f"candidates/{application}/candidate.json",
                                  "source_at_build": manifest["source_at_build"]["head"],
                                  "elf": manifest["files"]["zephyr.elf"],
                                  "hardware_validation": "pending",
                                  "runtime_scope": "NOT_RUN on D13x",
                                  "expected_output": {
                                      "bringup": "BRINGUP: thread/semaphore/timeout PASS",
                                      "kernel": "TESTSUITE artinchip_kernel succeeded",
                                      "fpu": "TESTSUITE artinchip_fpu succeeded"}[application]}
        if len({item["source_at_build"] for item in index.values()}) != 1:
            raise ValueError("candidate set was built from different source commits")
    if not files:
        raise ValueError("no evidence to retain")
    for name in files:
        safe_name(name)
    manifest = {"schema_version": 1, "software_audit": "pass" if success else "failed",
                "job_status": status, "transport_verified": "pending",
                "hardware_validation": "pending", "upstream_ready": "no",
                "candidates": index, "files": {name: record(data) for name, data in files.items()}}
    output.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, data in files.items():
            archive.writestr(name, data)
        archive.writestr("evidence.json", json.dumps(manifest, indent=2) + "\n")
    verify_archive(output)


def verify_archive(path):
    with zipfile.ZipFile(path) as archive:
        names = archive.namelist()
        if len(names) != len(set(names)):
            raise ValueError("duplicate archive entries")
        for name in names:
            safe_name(name)
        manifest = json.loads(archive.read("evidence.json"))
        if set(names) != set(manifest["files"]) | {"evidence.json"}:
            raise ValueError("archive inventory mismatch")
        for name, expected in manifest["files"].items():
            if record(archive.read(name)) != expected:
                raise ValueError(f"archive integrity mismatch: {name}")
        if manifest["software_audit"] == "pass":
            if set(manifest["candidates"]) != APPLICATIONS:
                raise ValueError("missing application candidate")
            for application, item in manifest["candidates"].items():
                candidate = json.loads(archive.read(item["manifest"]))
                for name, expected in candidate_records(candidate).items():
                    if record(archive.read(f"candidates/{application}/{name}")) != expected:
                        raise ValueError("downloaded candidate differs from candidate manifest")
        elif manifest["candidates"] or any(n.startswith("candidates/") for n in names):
            raise ValueError("failure archive must not advertise candidate success")
    return {"status": "PASS", "scope": "archive inventory/size/SHA-256",
            "software_audit": manifest["software_audit"], "files": len(manifest["files"])}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    check = sub.add_parser("verify")
    check.add_argument("archive", type=Path)
    create = sub.add_parser("stage")
    create.add_argument("archive", type=Path)
    create.add_argument("--status", choices=["success", "failure", "cancelled", "skipped"], required=True)
    for name in ("qemu", "d13x", "candidates", "logs", "environment", "negative"):
        create.add_argument("--" + name, type=Path, required=True)
    args = parser.parse_args()
    if args.command == "stage":
        stage(args.archive, args.status, args.qemu, args.d13x, args.candidates, args.logs, args.environment, args.negative)
    print(json.dumps(verify_archive(args.archive), indent=2))


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError, KeyError, zipfile.BadZipFile) as error:
        print(json.dumps({"status": "FAIL", "error": str(error)}))
        sys.exit(1)
