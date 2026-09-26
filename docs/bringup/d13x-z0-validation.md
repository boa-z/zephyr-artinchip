# Z0 validation procedure

hardware_validation: pending **for the whole Z0 scope**. Partial physical
evidence now exists and is recorded in `d13x-z0-stability-gate.md`: the
heartbeat-instrumented kernel suite reached 9/9 on board and the FPU context
matrix reached 1/1 with 5003+5004 peer preemptions, both with thread-state
MINTSTATUS.MIL held at 0 (3 on-board boots total: FPU candidate 2, kernel
candidate 1). Serial logs for those boots are kept in the local, gitignored
`artifacts/z0-gate-*-board-result/` directories, so they travel with the
delivery folder rather than the Git tree. Still NOT_RUN: the 600 s sustained
stress candidate, the ≥10 independent cold boots, and the ≥5-round kernel
repeat — no logs for those have been returned yet. QEMU results remain generic
RISC-V results, not D13x results.

## Build and collect

From an activated workspace with the pinned SDK and recorded patches applied:

```sh
python scripts/build_candidate.py bringup C:/tmp/aic-candidate-bringup
python scripts/package_candidate.py C:/tmp/aic-candidate-bringup artifacts/candidates/bringup
west twister -p d50t_2_lite/d133ecs -T samples/bringup -T tests/kernel -T tests/fpu \
  -T tests/z0_stress --board-root boards --build-only --outdir C:/tmp/aic-d13x
```

Use a new short output path on Windows (GNU ar can hit MAX_PATH in long Twister
paths). On Linux substitute a short local `/tmp` directory. **Linux is now the
required CI host** (`ubuntu-26.04`, `requirements-linux.lock`; the runner was
moved off `ubuntu-24.04` because that release's QEMU 8.2.2 has no `rv32i` CPU
model for the devicetree-composed `-cpu`). Run 36234634318 is the first green
run on that host, so that lock is now executed rather than merely declared.
Board-specific test configs opt into the
candidate boot contract; the SoC rejects builds that do not explicitly accept
that contract. Build-only scenarios must never be counted as executed test
passes.

Build and collect kernel, fpu and stress separately using the same controlled
entry point. Each candidate has its own receipt and ELF hash; the bringup ELF is
not the kernel, FPU or stress test image. To confirm a stress build still fits
the experimental window without a product reference image (what CI does):

```sh
python scripts/window_fit.py C:/tmp/aic-stress-window/zephyr \
  --expect CONFIG_AIC_Z0_STRESS_DURATION_SEC=600
```

It asserts one executable PT_LOAD at 0x40000000 with
`0 < p_filesz <= p_memsz <= 65536` and the stated 600 s profile, and reports
`loadable_image: false` / `hardware_validation: pending` — packaging a flashable
`.img` still requires the pinned known-good product reference and stays a local
operation (see `d13x-z0-stability-gate.md`).

## Physical acceptance

Load through the confirmed recoverable RAM path. Record raw UART logs for every
test, including failures. Suggested project thresholds, not vendor
certification. Per-item status as of 2026-09-26 (see
`d13x-z0-stability-gate.md` for the logs and hashes behind each line):

- Ten independent cold boots of the bringup sample. Expect module identity and
  `BRINGUP: thread/semaphore/timeout PASS`; also measure actual elapsed wall
  time. **NOT_RUN** — the gate candidates have 3 logged on-board boots between
  them (FPU 2, kernel 1); the bringup sample itself has not been cold-boot
  repeated.
- Sustained combined stress of at least ten minutes. **NOT_RUN, image
  delivered.** The dedicated `tests/z0_stress` 600 s candidate
  (`D50T_Z0_stress_gate.img`) is built, pinned and packaged; it observes
  timer-driven preemption, peer FPU preemption, voluntary switches and blocking
  wakeups continuously, prints a heartbeat every 5 s, and fails immediately when
  any watched counter stalls. Repeating kernel (0.529 s) and FPU (12.3 s) suites
  in a loop does **not** substitute for it, because neither runs long enough to
  cover a stall that appears after the first seconds.
- Kernel suite: thread handoff, semaphore timeout, timer-driven preemption and
  an owned aligned memory buffer, with complete ztest summaries. **PARTIAL** —
  9/9 PASS observed once on board with thread-state MIL held at 0
  (2,101,657 samples); the requested ≥5-round repeat has no returned log.
- FPU test loads distinct NaN-boxed f32 / finite f64 patterns into all 32 registers,
  checks fcsr and requires at least 5,000 verified peer preemptions per thread.
  Voluntary switches check ABI-preserved registers/fcsr 200 times. A phase barrier
  ensures preemption probes cannot start while the peer is still yielding.
  **PASS (2 consecutive boots)** — 5003 + 5004 peer checks, 200 voluntary
  checks, 33-slot pattern comparison clean, `FPU-MILHB violations=0`.
- Capture a controlled diagnostic exception in an isolated test session with a
  recoverable debugger/loader. Record cause, pc and trap output; **NOT_RUN** here.
- Validate inherited cache/map state, then establish safe owned-buffer clean /
  invalidate boundaries aligned to 32 bytes with no unrelated shared cache lines.
  Current owned-memory test validates CPU-visible persistence ONLY. Cache
  maintenance, uncached alias comparison, PSRAM, DMA and display coherency are
  NOT_RUN; no unverified whole-cache invalidation is performed.

The negative paths are exercised on QEMU rather than left assumed: four
fault-injection builds of `tests/z0_stress` each fail with the expected reason
(`mil_violation`, `voluntary_context_mismatch`, `timer_isr`,
`peer_preemption_missed`, non-zero exit, no timeout), and seven hermetic host
tests assert the packager rejects a missing/ambiguous/shortened duration profile,
any enabled injection, a tampered BIN or ELF, a cross-application mix and a
non-BASELINE reference. An injection build is never packaged as a hardware
image. Injection proves the verdict logic fires; it does not reproduce a defect.

## Evidence record

For each item retain test ID, board revision, operator, time, source commit and
dirty state, Zephyr base and patch SHA, SDK/compiler, exact ELF SHA-256, installed
bootloader identity, method and original serial log. Use PASS/FAIL/BLOCKED/NOT_RUN;
only change hardware_validation to verified after the applicable physical tests.
Retain failures and explain subsequent fixes, rather than replacing failed logs.

## Fault isolation

No UART: verify power hold, wiring/levels and loader clock/pin handoff before driver
changes. Early trap: capture pc/mcause and compare entry, SRAM overlap, mexstatus,
mtvec/mtvt, ABI and legacy CLIC layout. Frozen timeout: observe timer delta and
CLIC pending/enable/threshold plus compare rearming. FPU error: preserve printed
register index/expected/actual, peer epochs and ELF attributes before changing
context code. Never disable assertions to turn any of these into a PASS.
