# SPDX-License-Identifier: Apache-2.0
"""Check source declarations, not legal ownership or license compatibility."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys

import yaml

KINDS = {"new", "copied", "derived", "reference-only"}
STATES = {"reviewed", "review_required", "blocked"}
SUFFIXES = {".c", ".h", ".S", ".dts", ".dtsi", ".py", ".yml", ".yaml",
            ".conf", ".txt", ".cmake", ".json", ".ps1", ".sh", ".patch"}


def source_files(root):
    result = subprocess.run(["git", "ls-files", "--cached", "--others", "--exclude-standard"],
                            cwd=root, check=True, text=True, capture_output=True)
    return {p for p in result.stdout.splitlines()
            if (Path(p).suffix in SUFFIXES or Path(p).name.startswith("Kconfig")
                or Path(p).name.endswith("_defconfig"))
            and p != "docs/provenance.yml"}


def validate(root, manifest, files=None):
    errors = []
    covered = set()
    if not isinstance(manifest, dict) or manifest.get("schema_version") != 1:
        return ["unsupported provenance schema"]
    entries = manifest.get("files", [])
    if not isinstance(entries, list):
        return ["files must be a list"]
    for entry in entries:
        if not isinstance(entry, dict):
            errors.append("entry must be a mapping")
            continue
        path = entry.get("path", "")
        kind = entry.get("kind")
        state = entry.get("review_status")
        if not path or Path(path).is_absolute() or ".." in Path(path).parts:
            errors.append(f"unsafe path: {path}")
            continue
        if path in covered:
            errors.append(f"duplicate: {path}")
        covered.add(path)
        if kind not in KINDS or state not in STATES:
            errors.append(f"invalid kind/status: {path}")
        if not (root / path).is_file():
            errors.append(f"missing file: {path}")
        for field in ("license", "license_basis", "rights_holders", "changes", "dependencies"):
            if field not in entry or entry[field] is None:
                errors.append(f"missing {field}: {path}")
        if entry.get("license") in (None, "", "unknown", "NOASSERTION"):
            errors.append(f"unknown license: {path}")
        if kind != "reference-only" and state != "reviewed":
            errors.append(f"unreviewed repository source: {path}")
        if kind in {"copied", "derived", "reference-only"}:
            sources = entry.get("sources", [])
            if not sources:
                errors.append(f"missing sources: {path}")
            for source in sources:
                if not all(source.get(f) for f in ("project", "revision", "path", "sha256")):
                    errors.append(f"incomplete source: {path}")
                if not re.fullmatch(r"[0-9a-f]{64}", str(source.get("sha256", ""))):
                    errors.append(f"invalid source hash: {path}")
                if not re.fullmatch(r"[0-9a-f]{40}", str(source.get("revision", ""))):
                    errors.append(f"unpinned source: {path}")
        if kind == "copied" and (root / path).is_file() and entry.get("sources"):
            actual = hashlib.sha256((root / path).read_bytes()).hexdigest()
            if actual != entry["sources"][0].get("sha256"):
                errors.append(f"copied file changed; classify as derived: {path}")
    for path in sorted((source_files(root) if files is None else files) - covered):
        errors.append(f"uncovered: {path}")
    return errors


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args()
    try:
        data = yaml.safe_load((args.root / "docs/provenance.yml").read_text(encoding="utf-8"))
        errors = validate(args.root, data)
    except (OSError, ValueError, yaml.YAMLError, subprocess.CalledProcessError) as error:
        errors = [str(error)]
    print(json.dumps({"status": "FAIL" if errors else "PASS", "errors": errors}, indent=2))
    return bool(errors)


if __name__ == "__main__":
    sys.exit(main())
