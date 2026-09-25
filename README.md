# zephyr-artinchip

Community-maintained ArtInChip support as an out-of-tree Zephyr module and west
manifest repository. Scope: P0 infrastructure and a D133ECS SRAM-only Z0 software
candidate. **HARDWARE_PENDING: no physical board test and no loadable container.**

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

The installer also has a Linux x86_64 path, but only native Windows execution is
validated in this delivery. The Windows package lock is not a Linux lock.

## Verification gates

```powershell
python scripts/lint.py
python scripts/check_provenance.py
python -m unittest discover -s tests/host -v
python scripts/apply_patches.py --check
west twister -p qemu_riscv32 -T samples/bringup -T tests/kernel -T tests/fpu -T tests/clic --board-root boards --outdir C:/tmp/aic-qemu --inline-logs -j4
west twister -p d50t_2_lite/d133ecs -T samples/bringup -T tests/kernel -T tests/fpu --board-root boards --build-only --outdir C:/tmp/aic-d13x --inline-logs -j4
```

Use new output directories to preserve prior evidence. A short absolute Windows
path avoids GNU ar MAX_PATH failures with Twister's nested build paths. The roots
are passed explicitly; module declarations alone do not run tests. QEMU must
execute all 7 configurations / 23 cases. D13x is 3 build-only configurations and
zero runtime passes. JSON, xUnit, handler and build logs are retained by Twister.
`.github/workflows/ci.yml` enforces these downstream gates with no failure bypass;
the prior remote run 36092052502 failed during cross-drive artifact upload.
The revised R1 workflow has local archive checks; its remote rerun is pending
separate push authorization.

Interactive sample: `west build -b qemu_riscv32 samples/bringup -d build-qemu`,
then `west build -d build-qemu -t run`. Expected lines are
`MODULE: zephyr-artinchip` and `BRINGUP: thread/semaphore/timeout PASS`.
Exit QEMU with Ctrl-A, X. Module discovery is checked by a build assertion and a
real function linked from the module library.

## D13x candidate

Read `docs/bringup/d13x-preflight.md` and `d13x-boot-contract.md` first.

```powershell
python scripts/build_candidate.py bringup C:/tmp/aic-candidate-bringup
python scripts/package_candidate.py C:/tmp/aic-candidate-bringup artifacts/candidates/bringup
```

Delivery builds require a clean committed module and a new build directory. Repeat
the controlled build/collection for kernel and fpu with distinct directories.
See docs/build-receipts.md for source binding, negative probes and evidence ZIPs.

The collector validates ELF/load spans/ABI/ISA/compile flags/input objects/linked
runtime members and records hashes, source identity, toolchain and patch series.
Output is raw ELF/bin/map/config/DTS plus evidence, **not a packaged flash image**.
Link allocation is 512 KiB inside nominal 1 MiB SRAM; nominal 16 MiB PSRAM stays
disabled. Actual installed-loader overlap, RAM staging, handoff, accepted container
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
