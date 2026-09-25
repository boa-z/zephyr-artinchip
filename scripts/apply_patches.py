# SPDX-License-Identifier: Apache-2.0
"""Apply or verify the recorded prerequisite on an isolated west dependency."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]


def git(tree, *args):
    return subprocess.check_output(["git", "-C", str(tree), *args], text=True).strip()


def verify(tree):
    series = json.loads((ROOT / "patches/zephyr/series.json").read_text())
    if git(tree, "rev-parse", "HEAD") != series["base"]:
        raise ValueError("Zephyr HEAD differs from the required patch base")
    for patch in series["patches"]:
        if hashlib.sha256((ROOT / patch["path"]).read_bytes()).hexdigest() != patch["sha256"]:
            raise ValueError("recorded patch checksum differs")
    changes = git(tree, "diff", "--name-only", "HEAD").splitlines()
    if set(changes) != set(series["files"]):
        raise ValueError("dependency changes differ from the recorded patch file set")
    if git(tree, "ls-files", "--others", "--exclude-standard"):
        raise ValueError("unexpected untracked dependency files")
    if git(tree, "diff", "--cached", "--name-only"):
        raise ValueError("unexpected staged dependency changes")
    for path, expected in series["files"].items():
        if git(tree, "hash-object", f"--path={path}", path) != expected:
            raise ValueError(f"patched content differs: {path}")
    return series


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    tree = Path(subprocess.check_output([sys.executable, "-m", "west", "list", "zephyr",
                                        "-f", "{abspath}"], cwd=ROOT, text=True).strip())
    if not args.check and not git(tree, "status", "--porcelain"):
        series = json.loads((ROOT / "patches/zephyr/series.json").read_text())
        if git(tree, "rev-parse", "HEAD") != series["base"]:
            raise ValueError("refusing to patch another base")
        patches = []
        for patch in series["patches"]:
            path = ROOT / patch["path"]
            if hashlib.sha256(path.read_bytes()).hexdigest() != patch["sha256"]:
                raise ValueError("patch checksum differs")
            patches.append(str(path))
        subprocess.run(["git", "-C", str(tree), "apply", "--check", *patches], check=True)
        subprocess.run(["git", "-C", str(tree), "apply", *patches], check=True)
    series = verify(tree)
    print(json.dumps({"status": "PASS", "base": series["base"],
                      "patches": series["patches"], "hardware_validation": "pending"}, indent=2))


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError, subprocess.CalledProcessError) as error:
        print(json.dumps({"status": "FAIL", "error": str(error)}))
        sys.exit(1)
