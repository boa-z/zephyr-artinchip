# SPDX-License-Identifier: Apache-2.0
"""Install the pinned Zephyr SDK plus only GNU RISC-V, verifying release hashes."""
import argparse
import hashlib
import json
from pathlib import Path
import platform
import subprocess
import urllib.request

VERSION = "1.0.1"
BASE = f"https://github.com/zephyrproject-rtos/sdk-ng/releases/download/v{VERSION}/"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("destination", type=Path)
    args = parser.parse_args()
    system = platform.system().lower()
    if system not in ("windows", "linux") or platform.machine().lower() not in ("amd64", "x86_64"):
        parser.error("this installer supports Windows/Linux x86_64 only")
    dest = args.destination.resolve()
    dest.mkdir(parents=True, exist_ok=True)
    sdk = dest / f"zephyr-sdk-{VERSION}"
    if sdk.exists():
        parser.error(f"refusing to overwrite an existing SDK: {sdk}")
    cache = dest / "downloads"
    cache.mkdir(exist_ok=True)
    checksums = urllib.request.urlopen(BASE + "sha256.sum", timeout=60).read()
    (cache / "sha256.sum").write_bytes(checksums)
    checks = {line.split()[-1].lstrip("./*"): line.split()[0]
              for line in checksums.decode().splitlines()}
    extension = "7z" if system == "windows" else "tar.xz"
    host = f"{system}-x86_64"
    names = [f"zephyr-sdk-{VERSION}_{host}_minimal.{extension}",
             f"toolchain_gnu_{host}_riscv64-zephyr-elf.{extension}"]
    verified = []
    for name in names:
        archive = cache / name
        if not archive.exists():
            urllib.request.urlretrieve(BASE + name, archive)
        with archive.open("rb") as stream:
            digest = hashlib.file_digest(stream, "sha256").hexdigest()
        if digest != checks[name]:
            raise ValueError(f"checksum mismatch: {name}")
        verified.append({"file": name, "sha256": digest, "url": BASE + name})
        target = dest if name == names[0] else sdk / "gnu"
        target.mkdir(parents=True, exist_ok=True)
        # System tar on both hosts: it is what the SDK's own setup script uses, so
        # toolchain permission bits and symlinks land exactly as upstream intends.
        subprocess.run(["tar", "-xf", str(archive), "-C", str(target)], check=True)
    (dest / "sdk-downloads.json").write_text(json.dumps(verified, indent=2) + "\n")
    print(sdk)


if __name__ == "__main__":
    main()
