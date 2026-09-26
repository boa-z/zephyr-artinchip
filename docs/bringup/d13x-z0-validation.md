# Z0 validation procedure

hardware_validation: **verified within Z0 scope** (closed 2026-09-26). That scope is
exactly: D133ECS boot inside the current experimental 0x40000000/64 KiB product
window, E907/CLIC, machine timer, scheduler, IRQ delivery and preemption, WFI,
context switch, FPU sharing, and sustained CPU/kernel stress. It is recorded in
`d13x-z0-stability-gate.md`: the heartbeat-instrumented kernel suite reached 9/9 on
board (1 archived round, and >=5 consecutive rounds as owner-reported evidence), the
FPU context matrix reached 1/1 with 5003+5004 peer preemptions on 2 logged boots, and
the dedicated 600 s stress candidate completed a 601.789 s window with
`timer_isr=120360`, `fpu_a=fpu_b=90300`, `voluntary=180602`, `timeout_wakeups=28560`,
`mil_samples=209162`, `mil_violations=0`, `mil_worst=00`, `fpu_failures=0`. The >=10
independent cold boots are likewise **owner-observed hardware evidence**: the
operator reports them, the repository archives 4 boots with serial logs (FPU 2,
kernel 1, stress 1 excerpt), and no per-boot Reset flag was returned for the rest.
Logs live in the local, gitignored `artifacts/z0-gate-*-board-result/` directories, so
they travel with the delivery folder rather than the Git tree. QEMU results remain
generic RISC-V results, not D13x results.

Still **not** validated by this, and Z0 closure must not be read as covering them:
default SRAM layout and product partition ownership, timer accuracy against an
external timebase, PSRAM/DMA/cache coherency, clock/reset/pinctrl, GPIO, CAN,
display, GE/MPP, storage, controlled diagnostic-exception capture, installed-loader
RAM ownership and manual failure recovery (H0/H1 items stay BLOCKED/NOT_RUN), and
upstream readiness. `loadable_image` stays false for every candidate here.

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
run on that host and run 36235471896 is green on the delivered Z0 baseline head
`fee21ae`, so that lock is now executed rather than merely declared. CI carries
no board: it contributes nothing to the four physical gate items.
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
  time. **PASS for the gate candidate (owner-reported)** — the operator reports
  >=10 independent cold boots of one gate candidate, all completing normally; 4
  boots have archived serial logs in this delivery (FPU 2, kernel 1, stress 1
  excerpt) and no per-boot Reset flag was returned for the rest. The bringup
  sample itself has still not been cold-boot repeated, so this line is satisfied
  for the gate images only.
- Sustained combined stress of at least ten minutes. **PASS (one 601.789 s
  window)**. The dedicated `tests/z0_stress` 600 s candidate
  (`D50T_Z0_stress_gate.img`) is built, pinned and packaged; on board it observed
  timer-driven preemption, peer FPU preemption, voluntary switches and blocking
  wakeups continuously, printed a heartbeat every 5 s, and would have ended with
  the stalled counter's name as the FAIL reason. Repeating kernel (0.529 s) and
  FPU (12.3 s) suites in a loop does **not** substitute for it, because neither
  runs long enough to cover a stall that appears after the first seconds. One
  window is a single-sample result, not a repeatability claim.
- Kernel suite: thread handoff, semaphore timeout, timer-driven preemption and
  an owned aligned memory buffer, with complete ztest summaries. **PASS** —
  9/9 PASS observed on board with thread-state MIL held at 0 (2,101,657 samples,
  log archived for that round) plus >=5 consecutive 9/9 rounds reported by the
  operator, whose per-round logs were not returned.
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
