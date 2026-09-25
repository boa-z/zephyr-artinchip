# SPDX-License-Identifier: Apache-2.0
"""Report tools and source identity as JSON; fail when prerequisites are absent."""
import argparse
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys

from apply_patches import verify

ZEPHYR_REVISION = "839728050444f90d06870b5fc9bbbda106d91459"


def run(command, cwd=None):
    try:
        result = subprocess.run(command, cwd=cwd, capture_output=True, text=True,
                                encoding="utf-8", errors="replace", timeout=30)
        return {"code": result.returncode, "stdout": result.stdout.strip(),
                "stderr": result.stderr.strip()}
    except (OSError, subprocess.TimeoutExpired) as error:
        return {"code": 1, "stdout": "", "stderr": str(error)}


def git_identity(path):
    head = run(["git", "rev-parse", "HEAD"], path)
    state = run(["git", "status", "--porcelain"], path)
    return {"path": str(path), "head": head["stdout"] if head["code"] == 0 else None,
            "dirty": bool(state["stdout"]), "status": state["stdout"],
            "head_error": head["stderr"] if head["code"] else None}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sdk", type=Path, default=os.environ.get("ZEPHYR_SDK_INSTALL_DIR"))
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    report = {"host": platform.platform(), "python": sys.version,
              "source": git_identity(root), "tools": {}, "errors": []}
    for name in ("git", "west", "cmake", "ninja"):
        path = shutil.which(name)
        report["tools"][name] = run([path, "--version"]) if path else {"code": 1}
        if report["tools"][name]["code"]:
            report["errors"].append(f"missing or unusable tool: {name}")
    sdk = args.sdk
    suffix = ".exe" if os.name == "nt" else ""
    if sdk:
        for name, path in {
            "gcc": sdk / f"gnu/riscv64-zephyr-elf/bin/riscv64-zephyr-elf-gcc{suffix}",
            "qemu": sdk / (f"hosttools/qemu/qemu-system-riscv32{suffix}" if os.name == "nt"
                           else "hosttools/qemu/bin/qemu-system-riscv32"),
        }.items():
            report["tools"][name] = run([str(path), "--version"])
            if report["tools"][name]["code"]:
                report["errors"].append(f"missing or unusable tool: {path}")
        report["sdk"] = str(sdk)
    else:
        report["errors"].append("specify --sdk or ZEPHYR_SDK_INSTALL_DIR")
    zephyr = run([sys.executable, "-m", "west", "list", "zephyr", "-f", "{abspath}"], root)
    if zephyr["code"]:
        report["errors"].append("west cannot resolve Zephyr")
    else:
        report["zephyr"] = git_identity(Path(zephyr["stdout"]))
        try:
            report["patch_series"] = verify(Path(zephyr["stdout"]))
        except (ValueError, OSError, subprocess.CalledProcessError) as error:
            report["errors"].append(str(error))
    report["status"] = "FAIL" if report["errors"] else "PASS"
    text = json.dumps(report, indent=2, ensure_ascii=False)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text + "\n", encoding="utf-8")
    print(text)
    return bool(report["errors"])


if __name__ == "__main__":
    sys.exit(main())
