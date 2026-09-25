# SPDX-License-Identifier: Apache-2.0
"""Validate and collect an SRAM-only D133ECS software candidate, never a flash image."""
import argparse
import hashlib
import json
import io
import re
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

from elftools.common.exceptions import ELFError

from elftools.elf.elffile import ELFFile

from environment import git_identity
from apply_patches import verify

RAM_START = 0x30080000
RAM_END = 0x30100000
REQUIRED = ["zephyr.elf", "zephyr.bin", "zephyr.map", ".config", "zephyr.dts"]


def validate_segments(segments, entry):
    errors = []
    spans = []
    executable = False
    for segment in segments:
        start = segment["address"]
        end = start + segment["memory_size"]
        if segment["file_size"] > segment["memory_size"]:
            errors.append("file size exceeds memory size")
        if start < RAM_START or end > RAM_END or end <= start:
            errors.append(f"segment outside candidate SRAM: {start:#x}..{end:#x}")
        if any(start < previous_end and previous_start < end
               for previous_start, previous_end in spans):
            errors.append("overlapping load segments")
        spans.append((start, end))
        executable |= bool(segment["flags"] & 1 and start <= entry < end)
    if not executable:
        errors.append("entry does not lie in an executable load segment")
    return errors


def inspect_elf(path, data=None):
    with (path.open("rb") if data is None else io.BytesIO(data)) as stream:
        elf = ELFFile(stream)
        if elf.elfclass != 32 or elf["e_machine"] != "EM_RISCV":
            raise ValueError(f"not an ELF32 RISC-V input: {path}")
        if elf["e_flags"] & 0x6 != 0x4:
            raise ValueError(f"not double-float ABI: {path}")
        if not elf.little_endian:
            raise ValueError(f"not little endian: {path}")
        arch = elf.get_section_by_name(".riscv.attributes")
        if arch is None:
            raise ValueError(f"missing RISC-V attributes: {path}")
        attributes = {}
        for subsection in arch.iter_subsections():
            for section in subsection.iter_subsubsections():
                for attribute in section.iter_attributes():
                    attributes[attribute.tag] = attribute.value
        isa = attributes.get("TAG_ARCH", "")
        if not isa.startswith("rv32i"):
            raise ValueError(f"unexpected base ISA: {path}: {isa}")
        allowed = {"m", "a", "f", "d", "c", "zicsr", "zifencei", "zmmul", "zaamo", "zalrsc"}
        extensions = {re.sub(r"[0-9].*", "", part) for part in isa.split("_")[1:]}
        if extensions - allowed:
            raise ValueError(f"unapproved ISA extensions: {path}: {isa}")
        if attributes.get("TAG_STACK_ALIGN", 16) != 16:
            raise ValueError(f"stack alignment is not 16: {path}")
        segments = [{"address": segment["p_paddr"], "virtual_address": segment["p_vaddr"],
                     "memory_size": segment["p_memsz"], "file_size": segment["p_filesz"],
                     "flags": segment["p_flags"]}
                    for segment in elf.iter_segments()
                    if segment["p_type"] == "PT_LOAD" and segment["p_memsz"]]
        return {"entry": elf["e_entry"], "elf_flags": elf["e_flags"],
                "segments": segments, "attributes": attributes}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("build", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    build = args.build.resolve()
    output = args.output.resolve()
    if output.exists():
        parser.error("output must be a new directory; retain previous evidence")
    zephyr_output = build / "zephyr"
    for name in REQUIRED:
        if not (zephyr_output / name).is_file():
            parser.error(f"missing build output: {name}")
    config = (zephyr_output / ".config").read_text(encoding="utf-8")
    for required in ("CONFIG_SOC_D133ECS=y", "CONFIG_FPU=y", "CONFIG_FPU_SHARING=y",
                     "CONFIG_ARTINCHIP_MODULE=y", "CONFIG_ARTINCHIP_D13X_BOOT_CONTRACT=y"):
        if required not in config.splitlines():
            parser.error(f"missing configuration: {required}")
    metadata = inspect_elf(zephyr_output / "zephyr.elf")
    if not all(re.search(r"(?:^|_)" + ext + r"[0-9]", metadata["attributes"]["TAG_ARCH"])
               for ext in ("m", "a", "f", "d", "c")):
        raise ValueError("final image is not RV32IMAFDC")
    errors = validate_segments(metadata["segments"], metadata["entry"])
    if any(s["virtual_address"] != s["address"] for s in metadata["segments"]):
        errors.append("candidate requires identity-mapped SRAM load segments")
    objects = sorted(set(build.rglob("*.obj")) | set(build.rglob("*.o")))
    if not objects:
        errors.append("no compiled input objects available for ABI audit")
    for path in objects:
        try:
            inspect_elf(path)
        except ValueError as error:
            errors.append(str(error))
    # Inspect every externally linked archive member named by the GNU link map.
    cache = (build / "CMakeCache.txt").read_text(encoding="utf-8")
    compiler = re.search(r"^CMAKE_C_COMPILER:FILEPATH=(.+)$", cache, re.M)
    if not compiler:
        raise ValueError("cannot resolve compiler from build cache")
    gcc = Path(compiler.group(1).strip())
    ar = gcc.with_name("riscv64-zephyr-elf-ar" + (".exe" if os.name == "nt" else ""))
    members = set(re.findall(r"([^\s()]+\.a)\(([^)]+)\)",
                            (zephyr_output / "zephyr.map").read_text(encoding="utf-8")))
    external = []
    for archive, member in sorted(members):
        path = Path(archive.replace("\\", "/"))
        path = path.resolve() if path.is_absolute() else (build / path).resolve()
        if path.is_relative_to(build):
            continue  # all locally compiled input objects were inspected above
        # Windows GNU ar can translate LF on stdout: extract to preserve bytes.
        if Path(member).name != member or member in {".", ".."}:
            raise ValueError("unsafe archive member name")
        with tempfile.TemporaryDirectory() as temporary:
            subprocess.run([str(ar), "x", str(path), member], cwd=temporary, check=True)
            content = (Path(temporary) / member).read_bytes()
        inspected = inspect_elf(Path(member), content)
        external.append({"archive": str(path), "member": member,
                         "sha256": hashlib.sha256(content).hexdigest(),
                         "attributes": inspected["attributes"]})
    if not external:
        errors.append("no external runtime members identified; inspect the link map")
    if errors:
        raise ValueError("\n".join(errors))
    base = Path(subprocess.check_output([sys.executable, "-m", "west", "list", "zephyr",
                                        "-f", "{abspath}"], cwd=root, text=True).strip())
    dependency = git_identity(base)
    series = verify(base)
    freeze = subprocess.check_output([sys.executable, "-m", "west", "manifest", "--freeze"],
                                     cwd=root, text=True)
    commands = build / "compile_commands.json"
    if not commands.is_file():
        raise ValueError("compile_commands.json is required for flag auditing")
    output.mkdir(parents=True)
    shutil.copy2(commands, output / commands.name)
    shutil.copytree(root / "patches/zephyr", output / "patches")
    for name in REQUIRED:
        shutil.copy2(zephyr_output / name, output / name)
    (output / "west-frozen.yml").write_text(freeze, encoding="utf-8")
    shutil.copy2(root / "docs/bringup/d13x-boot-contract.md", output / "boot-contract.md")
    shutil.copy2(root / "docs/bringup/d13x-z0-validation.md", output / "validation.md")
    manifest = {
        "status": "HARDWARE_PENDING", "hardware_validation": "pending",
        "loadable_image": False, "format": "raw ELF/bin software candidate; no vendor container",
        "packaging_blocker": "Confirm installed loader, RAM staging and handoff before packaging",
        "source": git_identity(root), "zephyr": dependency, "patches": series,
        "compiler": subprocess.check_output([str(gcc), "--version"], text=True).splitlines()[0],
        "runtime_members": external,
        "board": "d50t_2_lite/d133ecs", "nominal_sram": 1048576,
        "nominal_psram": 16777216, "psram_enabled": False,
        "link_region": [RAM_START, RAM_END], "elf": metadata,
        "input_objects_checked": len(objects), "files": {},
    }
    for path in sorted(output.rglob("*")):
        if not path.is_file():
            continue
        manifest["files"][path.relative_to(output).as_posix()] = {"size": path.stat().st_size,
                                        "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
    (output / "candidate.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": "PASS", "scope": "candidate ELF/ABI/collection only",
                      "hardware_validation": "pending", "output": str(output)}, indent=2))


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError, ELFError, subprocess.CalledProcessError) as error:
        print(json.dumps({"status": "FAIL", "error": str(error)}))
        sys.exit(1)
