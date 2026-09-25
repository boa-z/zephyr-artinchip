# SPDX-License-Identifier: Apache-2.0
"""Expected-failure probes; retain failed target logs and external watchdog results."""
import argparse
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]


def guarded(command, seconds, log):
    options = {"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP} if os.name == "nt" else {
        "start_new_session": True}
    start = time.monotonic()
    with log.open("w", encoding="utf-8") as stream:
        process = subprocess.Popen(command, cwd=ROOT, stdout=stream, stderr=subprocess.STDOUT, **options)
        timed_out = False
        try:
            code = process.wait(timeout=seconds)
        except subprocess.TimeoutExpired:
            timed_out = True
            if os.name == "nt":
                subprocess.run(["taskkill", "/PID", str(process.pid), "/T", "/F"],
                               check=True, stdout=subprocess.DEVNULL)
            else:
                os.killpg(process.pid, signal.SIGKILL)
            process.wait(timeout=10)
            code = 124
    return {"exit_code": code, "timed_out": timed_out, "wall_seconds": time.monotonic() - start}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    parser.add_argument("--sdk", type=Path, required=True)
    args = parser.parse_args()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    target = output / "missing-signal"
    missing = guarded([sys.executable, "-m", "west", "twister", "-p", "qemu_riscv32",
                       "-T", str(ROOT / "samples/bringup"), "-s", "artinchip.bringup.no_assert",
                       "--board-root", str(ROOT / "boards"), "--outdir", str(target),
                       "--inline-logs", "-x=CONFIG_ARTINCHIP_BRINGUP_DROP_SIGNAL=y"],
                      240, output / "missing-signal.log")
    handlers = list(target.rglob("handler.log"))
    text = "\n".join(p.read_text(errors="replace") for p in handlers)
    configs = list(target.rglob(".config"))
    if (missing["exit_code"] == 0 or missing["timed_out"] or
            "BRINGUP: FAIL: worker did not complete" not in text or
            "BRINGUP: thread/semaphore/timeout PASS" in text or
            len(configs) != 1 or "# CONFIG_ASSERT is not set" not in configs[0].read_text()):
        raise ValueError("missing-signal probe did not produce the expected assertions-off failure")
    images = list(target.rglob("zephyr.elf"))
    if len(images) != 1:
        raise ValueError("cannot identify negative-test QEMU image")
    qemu = args.sdk / ("hosttools/qemu/qemu-system-riscv32.exe" if os.name == "nt" else
                       "hosttools/qemu/bin/qemu-system-riscv32")
    # -S deliberately prevents guest execution: only the external wall clock can end this run.
    frozen = guarded([str(qemu), "-machine", "virt", "-nographic", "-bios", "none",
                      "-kernel", str(images[0]), "-S"], 3, output / "frozen-cpu.log")
    if frozen["exit_code"] != 124 or not frozen["timed_out"]:
        raise ValueError("frozen QEMU did not reach the external watchdog")
    report = {"status": "PASS", "scope": "negative harness tests, not target runtime passes",
              "missing_signal": missing, "frozen_cpu": frozen, "hardware_validation": "pending"}
    (output / "probes.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError, subprocess.SubprocessError) as error:
        print(json.dumps({"status": "FAIL", "error": str(error)}))
        sys.exit(1)
