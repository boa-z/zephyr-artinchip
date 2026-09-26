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

from environment import qemu_executable

ROOT = Path(__file__).resolve().parents[1]

# Each stress fault-injection build must fail on QEMU with exactly this reason.
# The inject=<mode> field in the target's own opening line proves the override
# reached the build, so a silently ignored Kconfig cannot fake an expected FAIL.
STRESS_FAILURES = {
    "mil": "mil_violation",
    "fpu": "voluntary_context_mismatch",
    "timer": "timer_isr",
    "peer": "peer_preemption_missed",
}


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


def stress_injection_probes(output):
    results = {}
    for mode, reason in STRESS_FAILURES.items():
        target = output / f"stress-{mode}"
        run = guarded([sys.executable, "-m", "west", "twister", "-p", "qemu_riscv32",
                       "-T", str(ROOT / "tests/z0_stress"), "-s", "artinchip.z0_stress",
                       "--board-root", str(ROOT / "boards"), "--outdir", str(target),
                       "--inline-logs",
                       f"-x=CONFIG_AIC_Z0_STRESS_INJECT_{mode.upper()}=y"],
                      300, output / f"stress-{mode}.log")
        text = "\n".join(p.read_text(errors="replace")
                         for p in target.rglob("handler.log"))
        claims_pass = "Z0-STRESS PASS" in text
        if (run["exit_code"] == 0 or run["timed_out"] or claims_pass or
                f"inject={mode}" not in text or "result=FAIL" not in text or
                f"reason={reason}" not in text):
            raise ValueError(f"stress {mode} injection did not produce the expected "
                             f"FAIL reason={reason}")
        results[mode] = {**run, "reason": reason, "claims_pass": claims_pass}
    return results


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
    qemu = str(qemu_executable(args.sdk))
    # -S deliberately prevents guest execution: only the external wall clock can end this run.
    frozen = guarded([str(qemu), "-machine", "virt", "-nographic", "-bios", "none",
                      "-kernel", str(images[0]), "-S"], 3, output / "frozen-cpu.log")
    if frozen["exit_code"] != 124 or not frozen["timed_out"]:
        raise ValueError("frozen QEMU did not reach the external watchdog")
    stress = stress_injection_probes(output)
    report = {"status": "PASS", "scope": "negative harness tests, not target runtime passes",
              "missing_signal": missing, "frozen_cpu": frozen,
              "stress_injections": stress, "hardware_validation": "pending"}
    (output / "probes.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError, subprocess.SubprocessError) as error:
        print(json.dumps({"status": "FAIL", "error": str(error)}))
        sys.exit(1)
