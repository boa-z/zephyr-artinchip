# Z0 validation procedure

hardware_validation: pending. No physical board session or serial log exists
for this delivery. QEMU results are generic RISC-V results, not D13x results.

## Build and collect

From an activated workspace with the pinned SDK and recorded patches applied:

```sh
python scripts/build_candidate.py bringup C:/tmp/aic-candidate-bringup
python scripts/package_candidate.py C:/tmp/aic-candidate-bringup artifacts/candidates/bringup
west twister -p d50t_2_lite/d133ecs -T samples/bringup -T tests/kernel -T tests/fpu --board-root boards --build-only --outdir C:/tmp/aic-d13x
```

Use a new short output path on Windows (GNU ar can hit MAX_PATH in long Twister
paths). On Linux substitute a short local `/tmp` directory; Linux has not been
validated locally. Board-specific test configs opt into the candidate boot
contract; the SoC rejects builds that do not explicitly accept that contract.
Build-only scenarios must never be counted as executed test passes.

Build and collect kernel and fpu separately using the same controlled entry point.
Each candidate has its own receipt and ELF hash; the bringup ELF is not the kernel
or FPU test image. Current hardware facts and blockers are recorded in
d13x-handoff.yml.

## Physical acceptance (NOT_RUN)

After the boot contract is resolved, load through the confirmed recoverable RAM
path. Record raw UART logs for every test, including failures. Suggested project
thresholds, not vendor certification:

- Ten independent cold boots of the bringup sample. Expect module identity and
  `BRINGUP: thread/semaphore/timeout PASS`; also measure actual elapsed wall time.
- Run kernel and FPU builds for at least ten minutes in repeated combined cycles.
  Kernel covers thread handoff, semaphore timeout, timer-driven preemption and
  an owned aligned memory buffer. Retain complete ztest summaries.
- FPU test loads distinct NaN-boxed f32 / finite f64 patterns into all 32 registers,
  checks fcsr and requires at least 5,000 verified peer preemptions per thread.
  Voluntary switches check ABI-preserved registers/fcsr 200 times. A phase barrier
  ensures preemption probes cannot start while the peer is still yielding.
- Capture a controlled diagnostic exception in an isolated test session with a
  recoverable debugger/loader. Record cause, pc and trap output; NOT_RUN here.
- Validate inherited cache/map state, then establish safe owned-buffer clean /
  invalidate boundaries aligned to 32 bytes with no unrelated shared cache lines.
  Current owned-memory test validates CPU-visible persistence ONLY. Cache
  maintenance, uncached alias comparison, PSRAM, DMA and display coherency are
  NOT_RUN; no unverified whole-cache invalidation is performed.

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
