# SPDX-License-Identifier: Apache-2.0
"""Check repository text, Python syntax and YAML without modifying source."""
import ast
import json
from pathlib import Path
import subprocess
import sys

import yaml


def main():
    root = Path(__file__).resolve().parents[1]
    names = subprocess.check_output(
        ["git", "ls-files", "--cached", "--others", "--exclude-standard"],
        cwd=root, text=True).splitlines()
    errors = []
    for name in sorted(set(names)):
        path = root / name
        if not path.is_file():
            errors.append(f"missing: {name}")
            continue
        try:
            text = path.read_text(encoding="utf-8")
            if path.suffix != ".patch":
                for number, line in enumerate(text.splitlines(), 1):
                    if line.rstrip() != line:
                        errors.append(f"trailing whitespace: {name}:{number}")
            if text and not text.endswith("\n"):
                errors.append(f"no final newline: {name}")
            if path.suffix == ".py":
                ast.parse(text, filename=name)
            if path.suffix in {".yaml", ".yml"}:
                yaml.safe_load(text)
        except (UnicodeError, OSError, SyntaxError, yaml.YAMLError) as error:
            errors.append(f"{name}: {error}")
    print(json.dumps({"status": "FAIL" if errors else "PASS", "errors": errors}, indent=2))
    return bool(errors)


if __name__ == "__main__":
    sys.exit(main())
