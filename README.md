# zephyr-artinchip

Community-maintained ArtInChip support as an out-of-tree Zephyr module and west
manifest repository. Scope: P0 infrastructure and a D133ECS SRAM-only Z0 software
candidate. **Z0 CLOSED — hardware validated within Z0 scope: the four physical
stability gate items PASS (kernel 9/9, the FPU context matrix, a 601.789 s
sustained stress window, and >=10 independent cold boots of one candidate as
owner-reported evidence), with thread-state MINTSTATUS.MIL held at 0 across
2,333,061 logged heartbeat samples and zero FPU context failures, and the required
Linux software gate green in Actions run 36235471896. That claim covers only E907 /
CLIC, the machine timer, the scheduler, IRQ delivery and preemption, WFI, context
switching, FPU sharing and sustained CPU/kernel stress inside the experimental
0x40000000/64 KiB product window. It says nothing about the default SRAM layout,
PSRAM/DMA/cache coherency, clock/reset/pinctrl, GPIO, CAN, display, GE/MPP or
storage, and no image here is a shippable loadable container
(`loadable_image: false`).** See
`docs/bringup/d13x-z0-stability-gate.md` for the per-item board logs and the
evidence split between archived logs and owner-reported repeats.

## Reproduce on Windows

Validated with Python 3.13.15, Zephyr SDK 1.0.1, GCC 14.3.0 and QEMU 10.0.2.
Place this repository in `zephyr-artinchip` inside a new workspace. In PowerShell:

```powershell
python -m venv .venv
. .venv/Scripts/Activate.ps1
python -m pip install -r requirements-windows.lock
west init -l .
west update
python scripts/apply_patches.py
python scripts/install_sdk.py ../toolchains
$env:ZEPHYR_SDK_INSTALL_DIR = (Resolve-Path ../toolchains/zephyr-sdk-1.0.1).Path
west manifest --validate
python scripts/environment.py --output artifacts/environment.json
```

Skip `west init` in an already initialized workspace. The SDK installer refuses
to overwrite an installation; reuse an already verified SDK through the environment
variable. If PowerShell activation is restricted, add `.venv/Scripts` to PATH only
in the current process and invoke `.venv/Scripts/python` explicitly.

`zephyr-upstream` is an isolated official dependency clone so an existing `zephyr`
fork is not changed. Its HEAD is pinned to
`839728050444f90d06870b5fc9bbbda106d91459`; the explicit CLIC layout and width-validation patches are applied
on top and verified by `scripts/apply_patches.py --check`. **The dependency is
patched**, not an unmodified upstream build. `patches/zephyr/series.json` and its
patch files are required in addition to `west manifest --freeze`.

Only Zephyr itself is fetched: successful bringup/kernel/FPU builds use in-tree
code and SDK runtime libraries, so imported module paths are explicitly blocked.
Revisit that decision when adding an actual external-module consumer. SDK/product
source is not a build dependency. No global Git or environment changes are needed.

The installer supports Windows and Linux x86_64. **Linux is now the required CI
host**: `.github/workflows/ci.yml` runs on `ubuntu-26.04` with
`requirements-linux.lock`, which mirrors the Windows lock minus the Windows-only
curses wheel. The runner is not `ubuntu-24.04`: that release's apt emulator is
QEMU 8.2.2, which has no `rv32i` CPU model, and the pinned Zephyr revision
composes `-cpu` from devicetree, so all 28 QEMU cases died as an empty
`unexpected eof`. Ubuntu 26.04 ships QEMU 10.2.1, in a separate
`qemu-system-riscv` package (24.04 kept RISC-V inside `qemu-system-misc`), the
same major version as the locally validating emulator, and the workflow now
asserts the binary and the `rv32i` model before anything is built. Run
36234634318 at `163269d` is the first green Ubuntu run: 8 of 8 scenarios,
28 of 28 cases, no warnings, D13x build-only and the evidence round trip all
passing. Windows
remains the locally exercised developer host and is kept as a manual,
non-blocking compatibility run
(`.github/workflows/ci-windows.yml`, `workflow_dispatch` only).

## Verification gates

```powershell
python scripts/lint.py
python scripts/check_provenance.py
python -m unittest discover -s tests/host -v
python scripts/apply_patches.py --check
west twister -p qemu_riscv32 -T samples/bringup -T tests/kernel -T tests/fpu -T tests/clic -T tests/z0_stress --board-root boards --outdir C:/tmp/aic-qemu --inline-logs -j4
west twister -p d50t_2_lite/d133ecs -T samples/bringup -T tests/kernel -T tests/fpu -T tests/z0_stress --board-root boards --build-only --outdir C:/tmp/aic-d13x --inline-logs -j4
python scripts/window_fit.py C:/tmp/aic-stress-window/zephyr --expect CONFIG_AIC_Z0_STRESS_DURATION_SEC=600
```

Use new output directories to preserve prior evidence. A short absolute Windows
path avoids GNU ar MAX_PATH failures with Twister's nested build paths. The roots
are passed explicitly; module declarations alone do not run tests. QEMU must
execute all 8 scenarios / 28 cases (bringup x2, kernel 9, fpu, clic x3, the
`tests/z0_stress` 3 s coverage profile). D13x is 4 build-only configurations and
zero runtime passes. JSON, xUnit, handler and build logs are retained by Twister.
`.github/workflows/ci.yml` enforces these downstream gates with no failure bypass;
the prior run 36092052502 failed during cross-drive artifact upload. Follow-up
run 36096131063 passed failure-evidence upload/download verification but failed
a host-test path comparison. Run 36099116552 at a607310 then passed the complete
workflow; run 36099414248 at 480e95e also completed successfully. Both downloaded
archives passed independent verification including all three candidate .config
files and candidate-to-build-receipt consistency. Those were Windows-host runs;
the required gate has since moved to `ubuntu-26.04`, where run 36234634318 at
`163269d` is the first green run; docs/bringup/d13x-z0-stability-gate.md records
its environment data. See docs/validation-r1-report.md for follow-up
acceptance evidence and docs/bringup/loader-audit.md for the remaining hardware gates.

Interactive sample: `west build -b qemu_riscv32 samples/bringup -d build-qemu`,
then `west build -d build-qemu -t run`. Expected lines are
`MODULE: zephyr-artinchip` and `BRINGUP: thread/semaphore/timeout PASS`.
Exit QEMU with Ctrl-A, X. Module discovery is checked by a build assertion and a
real function linked from the module library.

## D13x candidate

Read `docs/bringup/d13x-preflight.md` and `d13x-boot-contract.md` first.
`docs/bringup/d13x-z1-platform-baseline.md` records the Z1 platform baseline and
the three CLIC upstream candidate dossiers; no pull request has been opened.

```powershell
python scripts/build_candidate.py bringup C:/tmp/aic-candidate-bringup
python scripts/package_candidate.py C:/tmp/aic-candidate-bringup artifacts/candidates/bringup
```

Delivery builds require a clean committed module and a new build directory. Repeat
the controlled build/collection for kernel, fpu and stress with distinct
directories. `tests/z0_stress` is the standalone 600 s sustained-stress verifier
for the Z0 stability gate (timer preemption, peer FPU preemption, voluntary
switches, blocking wakeup, thread-context-only MIL sampling); it does not link the
kernel or FPU ztest suites. See docs/bringup/d13x-z0-stability-gate.md for the
gate, its packaged candidates and its failure-path probes.
See docs/build-receipts.md for source binding, negative probes and evidence ZIPs.
Use scripts/audit_loader.py for read-only product-SPL identity/static-range checks;
see docs/bringup/loader-audit.md for its nonzero BLOCKED result and scope limits.

The collector validates ELF/load spans/ABI/ISA/compile flags/input objects/linked
runtime members and records hashes, source identity, toolchain and patch series.
Output is raw ELF/bin/map/config/DTS plus evidence, **not a packaged flash image**.
Link allocation is 512 KiB inside the SoC's 1 MiB SRAM; the Z0 gate images
instead linked at `0x40000000`, the SDK's PSRAM_CMA origin, so they relied on
loader-initialised PSRAM and no Zephyr PSRAM driver is enabled. Actual
installed-loader overlap, RAM staging, handoff, accepted container
and console wiring must be confirmed before loading. No speculative flash command
or automatic programming is provided.

`docs/bringup/d13x-z0-validation.md` defines recoverable hardware acceptance and
failure diagnosis. CPU-visible aligned memory persistence is tested; cache
maintenance, DMA/display coherency and PSRAM remain NOT_RUN.
See `docs/validation-r1-report.md` for the R1 results and candidate index.
`docs/validation-report.md` preserves the earlier delivery's historical evidence.

## Policy

See `CONTRIBUTING.md`, `NOTICE` and `docs/provenance.yml`. Derived hardware facts
retain their sources and original hashes. No SDK runtime is imported. Human
license/ownership review and DCO sign-off remain pending. Development uses local
commits with the supplied repository identity and an accurate Assisted-by trailer;
no Signed-off-by is generated. No push, release or automatic hardware operation.

H0 closure follow-up (2026-09-25): see [closure investigation](docs/bringup/d13x-h0-closure.md). Four clean target builds and FIT roundtrips pass; corrected non-QEMU core MMIO addresses. Dynamic RAM and manual recovery remain BLOCKED, H1 NOT_RUN, loadable_image=false.
