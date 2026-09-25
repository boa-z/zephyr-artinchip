# SPDX-License-Identifier: Apache-2.0
"""Build-time identity and payload validation; receipts are not signatures."""
import hashlib
import json
import os
from pathlib import Path
import re
import shlex
import subprocess
import tempfile

from apply_patches import verify
from environment import git_identity

ROOT = Path(__file__).resolve().parents[1]
APPLICATIONS = {"bringup": "samples/bringup", "kernel": "tests/kernel", "fpu": "tests/fpu",
                "handoff_probe": "samples/handoff_probe"}
BOARD = "d50t_2_lite/d133ecs"
PAYLOADS = ["zephyr/zephyr.elf", "zephyr/zephyr.bin", "zephyr/zephyr.map",
            "zephyr/.config", "zephyr/zephyr.dts", "compile_commands.json",
            "CMakeCache.txt", "build.ninja"]


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def file_record(path):
    return {"size": Path(path).stat().st_size, "sha256": digest(path)}


def cache_value(cache, key):
    matches = re.findall(r"^" + re.escape(key) + r":[A-Z_]+=([^\r\n]*)$",
                         cache.replace("\r\n", "\n"), re.M)
    if len(matches) != 1 or not matches[0].strip():
        raise ValueError(f"missing or ambiguous cache value: {key}")
    return matches[0].strip()


def runtime_path(name):
    return not (name.startswith(("docs/", "scripts/", "tests/host/", ".github/"))
                or name.endswith(".md") or name in {
                    ".gitignore", ".gitattributes", "LICENSE", "NOTICE", "requirements-windows.lock"})


def source_snapshot(root=ROOT, clean=True):
    identity = git_identity(root)
    if clean and identity["dirty"]:
        raise ValueError("delivery builds require a clean committed module")
    names = subprocess.check_output(
        ["git", "-C", str(root), "ls-files", "-z", "--cached", "--others", "--exclude-standard"]
    ).decode("utf-8").split("\0")
    files = {name: digest(root / name) for name in sorted(set(names)) if name}
    return {**identity, "files": files,
            "runtime_files": {name: value for name, value in files.items() if runtime_path(name)}}


def dependency_snapshot(base):
    return {"identity": git_identity(base), "patches": verify(base)}


def tool_record(path):
    path = Path(path).resolve(strict=True)
    version = subprocess.check_output([str(path), "--version"], text=True).splitlines()[0]
    return {"path": str(path), "sha256": digest(path), "version": version}


def build_tools(cache):
    return {name: tool_record(cache_value(cache, key)) for name, key in {
        "compiler": "CMAKE_C_COMPILER", "ar": "CMAKE_AR", "objcopy": "CMAKE_OBJCOPY"}.items()}


def binary_command(build, objcopy):
    # Read the actual generated command, including all conversion options.
    commands = subprocess.check_output(
        ["ninja", "-C", str(build), "-t", "commands", "zephyr/zephyr.elf"], text=True)
    found = []
    for line in commands.splitlines():
        if "zephyr.bin" not in line:
            continue
        for fragment in line.split(" && "):
            if Path(objcopy).name not in fragment:
                continue
            tokens = shlex.split(fragment, posix=os.name != "nt")
            tokens = [token.strip('"') for token in tokens]
            if tokens and Path(tokens[0]).resolve() == Path(objcopy).resolve():
                if tokens[-2:] != ["zephyr.elf", "zephyr.bin"]:
                    raise ValueError("unsupported generated binary output command")
                found.append({"cwd": str((build / "zephyr").resolve()),
                              "tool": objcopy, "arguments": tokens[1:-2]})
    if len(found) != 1:
        raise ValueError("cannot uniquely resolve generated ELF-to-bin command")
    return found[0]


def verify_binary(build, command):
    if Path(command["cwd"]).resolve() != (build / "zephyr").resolve():
        raise ValueError("binary command belongs to another build")
    with tempfile.TemporaryDirectory() as directory:
        output = Path(directory) / "reconstructed.bin"
        subprocess.run([command["tool"], *command["arguments"],
                        str(build / "zephyr/zephyr.elf"), str(output)],
                       cwd=command["cwd"], check=True)
        if output.read_bytes() != (build / "zephyr/zephyr.bin").read_bytes():
            raise ValueError("ELF/bin conversion mismatch")


def map_inputs(text, build):
    text = text.replace("\r\n", "\n")
    heading = "Archive member included to satisfy reference by file (symbol)\n"
    if not text.startswith(heading) or "\nDiscarded input sections\n" not in text:
        raise ValueError("unsupported GNU archive map format")
    included = text[len(heading):].split("\nDiscarded input sections\n", 1)[0]
    members = []
    for line in included.splitlines():
        if not line or line[0].isspace():
            continue
        match = re.fullmatch(r"(.+\.a)\(([^()]+)\)(?:\s+.*)?", line)
        if not match:
            raise ValueError(f"unparsed archive inclusion: {line}")
        archive, member = match.groups()
        if Path(member).name != member or "/" in member or "\\" in member or member in {".", ".."}:
            raise ValueError("unsafe archive member name")
        path = Path(archive.strip('"').replace("\\", "/"))
        path = path if path.is_absolute() else build / path
        members.append((path.resolve(strict=True), member))
    objects = []
    for name in re.findall(r"^LOAD (.+)$", text, re.M):
        path = Path(name.strip('"').replace("\\", "/"))
        path = path if path.is_absolute() else build / path
        if path.suffix in {".o", ".obj"}:
            objects.append(path.resolve(strict=True))
        elif path.suffix != ".a":
            raise ValueError(f"unsupported linked input: {name}")
        else:
            path.resolve(strict=True)
    if not members or not objects:
        raise ValueError("missing archive or direct object link evidence")
    return sorted(set(members)), sorted(set(objects))


def linked_files(build):
    members, objects = map_inputs((build / "zephyr/zephyr.map").read_text(encoding="utf-8"), build)
    return {str(path): file_record(path) for path in sorted({p for p, _ in members} | set(objects))}


def validate_build_identity(build, application, base):
    cache = (build / "CMakeCache.txt").read_text(encoding="utf-8")
    for key, expected in {"APPLICATION_SOURCE_DIR": ROOT / APPLICATIONS[application],
                          "ZEPHYR_BASE": base}.items():
        if Path(cache_value(cache, key)).resolve() != expected.resolve():
            raise ValueError(f"foreign build directory: {key}")
    if cache_value(cache, "BOARD") != BOARD:
        raise ValueError("unexpected build board")
    commands = json.loads((build / "compile_commands.json").read_text())
    inputs = {Path(entry["file"]).resolve() for entry in commands}
    if ROOT / "src/module.c" not in inputs or ROOT / APPLICATIONS[application] / "src/main.c" not in inputs:
        raise ValueError("build does not consume the intended module and application")
    return cache


def verify_receipt(build):
    path = build / "build-provenance.json"
    receipt = json.loads(path.read_text(encoding="utf-8"))
    if receipt.get("schema_version") != 1 or receipt.get("status") != "PASS":
        raise ValueError("missing successful build-time provenance")
    if Path(receipt["build"]).resolve() != build.resolve():
        raise ValueError("receipt belongs to another build")
    source = source_snapshot(clean=False)
    original = receipt["source_at_build"]
    if original["dirty"] or Path(original["path"]).resolve() != ROOT:
        raise ValueError("untrusted source checkout identity")
    if source["runtime_files"] != original["runtime_files"]:
        raise ValueError("firmware sources differ from build-time snapshot")
    base = Path(receipt["dependency_at_build"]["identity"]["path"])
    if dependency_snapshot(base) != receipt["dependency_at_build"]:
        raise ValueError("Zephyr or patch state differs from build-time snapshot")
    cache = validate_build_identity(build, receipt["application"], base)
    if build_tools(cache) != receipt["tools"]:
        raise ValueError("build tool identity changed")
    if set(receipt["files"]) != set(PAYLOADS):
        raise ValueError("receipt payload inventory differs")
    for name, expected in receipt["files"].items():
        if file_record(build / name) != expected:
            raise ValueError(f"build payload changed: {name}")
    if linked_files(build) != receipt["linked_files"]:
        raise ValueError("linked inputs differ from build-time snapshot")
    if binary_command(build, receipt["tools"]["objcopy"]["path"]) != receipt["binary_command"]:
        raise ValueError("binary conversion command changed")
    verify_binary(build, receipt["binary_command"])
    return receipt
