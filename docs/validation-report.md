# P0 and D13x Z0 software validation

Date: 2026-09-25. Status: **Z0 software candidate / HARDWARE_PENDING**.
`hardware_validation: pending`. No physical hardware execution or loadable vendor
container is claimed. All paths below are local evidence, not published artifacts.

## 1. Repository and source identity

Repository: `zephyr-artinchip`, branch `codex/bootstrap-d13x-z0`.

| Commit | Scope |
|---|---|
| `c77eda9` | Pinned west workspace, out-of-tree module and policy |
| `e8059d2` | Module, kernel and QEMU runtime tests |
| `a81da02` | FPU register lifetime and scheduling tests |
| `e267213` | D133ECS SRAM-only board/SoC candidate and CLIC prerequisite |
| `fce69d9` | Downstream CI, source and candidate audit gates |
| `5ca65c6` | Candidate collector accepts actual CMake STRING compiler entries |

The final candidate was built and collected from clean commit
`5ca65c684b10b84314c4dd562c7da4fe6f51d520`. This report is a later documentation
change. Fresh QEMU and D13x Twister runs started from `fce69d9`; the only subsequent
code change is the host collector/parser regression fix, not firmware or runtime
test code. The runs finished successfully and their logs are retained.

Reference Zephyr fork remains clean at
`839728050444f90d06870b5fc9bbbda106d91459`. The product SDK remains at
`0ac5adf01f6c5e7f60f3e5b37c56076cbd09c29b`, with existing settings, D50T application,
LVGL submodule and untracked certificate changes preserved. Fixed SoC reference
`c5807f9e7d18292f920dafaa018b8174635085c4` is read from Git objects. Neither reference
tree was edited. Exact final statuses are in the evidence directory.

## 2. Implemented scope

P0 supplies pinned dependencies, module discovery, native Windows setup, source
provenance, fail-closed checks, host tests, downstream CI and actual QEMU execution.
README commands reproduce the locally validated workspace. A second complete
network/bootstrap installation was not repeated in this continuation; Linux setup
and remote GitHub Actions execution remain NOT_RUN. No bit-for-bit reproducibility
claim is made.

Z0 supplies D133ECS metadata, a bounded-SRAM board DTS, explicit boot-contract
opt-in (from Z1 onwards that acknowledgement gates image collection rather than
compilation), E907 reset hook and legacy CLIC layout patch. Console and machine
timer reuse pinned Zephyr drivers. Zephyr drives no PSRAM: the SRAM candidate
links into SRAM, while the three Z0 gate images linked into loader-initialised
PSRAM at 0x40000000. The candidate uses Zephyr scheduling
and FPU management; it does not import an SDK or RT-Thread runtime.

## 3. Dependencies and tools

Zephyr base: `839728050444f90d06870b5fc9bbbda106d91459` (4.4.99), in the isolated
`zephyr-upstream` tree. The dependency is explicitly patched, not pristine.

- Patch: `patches/zephyr/0001-clic-legacy-mmio-layout.patch`.
- Patch SHA-256: `d493c9797d801138ef5017f7bbfe418073bcd902e7cb08698dafe78fb9454339`.
- SDK 1.0.1; GCC 14.3.0; QEMU 10.0.2; Python 3.13.15.
- west 1.5.0; CMake 4.4.3; Ninja 1.13.2; Git 2.55.0.windows.3.

`environment.json`, candidate `west-frozen.yml` and the copied patch series record
the complete local identity. Patch verification confirms only the declared three
CLIC files differ from the pinned base.

## 4. Tests and commands

Run from the repository with `.venv/Scripts` on PATH and the recorded
`ZEPHYR_SDK_INSTALL_DIR`. Each command must return zero before proceeding.

```powershell
python scripts/lint.py
python scripts/check_provenance.py
python -m unittest discover -s tests/host -v
python scripts/apply_patches.py --check
west manifest --validate
west twister -p qemu_riscv32 -T samples/bringup -T tests/kernel -T tests/fpu --board-root boards --outdir C:/tmp/aic-qemu-resume --inline-logs -j3
west twister -p d50t_2_lite/d133ecs -T samples/bringup -T tests/kernel -T tests/fpu --board-root boards --build-only --outdir C:/tmp/aic-d13x-resume --inline-logs -j3
west build -b d50t_2_lite/d133ecs samples/bringup -d C:/tmp/aic-candidate-5ca65c6
python scripts/package_candidate.py C:/tmp/aic-candidate-5ca65c6 artifacts/d13x-candidate-5ca65c6
```

These are the actual output directories used. Choose new directories for a rerun
to preserve prior results; candidate collection rejects an existing output path.

| Gate | Result | Counts and boundary |
|---|---|---|
| Lint, provenance, manifest, patch verification, environment | PASS | Local checks only |
| Host regression tests | PASS | 26 tests; zero failures/errors/skips |
| QEMU engineering/kernel runtime | PASS | 3 configurations, 7 cases executed and passed; zero filtered/skipped/failed/errors |
| D13x target compilation | PASS | 3 configurations built; 7 cases NOT_RUN; zero filtered/failed/errors |
| Fresh bringup candidate and audit | PASS | 119 input objects, 119 compile commands, 14 external runtime members |
| Remote CI, Linux setup, physical hardware | NOT_RUN | No corresponding runtime evidence |

Both Twister runs began at `2026-09-25T03:39:42+00:00` (11:39:42 Singapore). QEMU
completed in 69.07 seconds and D13x build-only in 58.02 seconds. The FPU handler
log records `5003 + 5004` verified preemptions and 200 voluntary checks. Kernel
tests cover module linkage, owned memory, thread/semaphore handoff, timeout and
timer-driven preemption. Owned-memory success is CPU-visible persistence only.

Original JSON, xUnit, handler and build logs were copied into
`artifacts/validation-20260925/`; `sha256.json` records 29 evidence file hashes.
Original Twister trees remain at the paths above. Prior failure logs are retained.

The previous `candidate-release.log` records a real collection failure:
`cannot resolve compiler from build cache`. The build uses
`CMAKE_C_COMPILER:STRING`, while the collector accepted only `FILEPATH`. Commit
`5ca65c6` handles both and rejects absent, empty or ambiguous entries. Four new
host tests pass; collection of the previously failing release build and a fresh
candidate both pass. No failed test or log was suppressed.

## 5. Physical hardware

NOT_RUN: no board operator, serial capture, physical loading or cold-boot run.
QEMU virt does not validate E907 CLIC, actual timer input, UART wiring, reset CSR
behavior or loader handoff. Cache maintenance, PSRAM, DMA/display coherency and
controlled hardware exception diagnostics remain NOT_RUN.

## 6. License and provenance

The provenance checker covers 51 declarations: 44 new, 4 derived, 1 copied and
2 reference-only. Its reviewed status denotes a file/source transformation audit,
not human legal approval or DCO. The derived files are board DTS, SoC DTS, reset
assembly and the CLIC patch; their source revisions, hashes and retained notices
are in `provenance.yml`. This continuation adds no imported third-party code.
Original code remains Apache-2.0. Human ownership/license review and DCO remain
pending. No Signed-off-by was generated; no push or publication was performed.

## 7. Candidate files and identity

Directory: `artifacts/d13x-candidate-5ca65c6/`. Contents include ELF, raw bin, map,
`.config`, final DTS, compile database, frozen manifest, patch series, boot contract,
validation procedure and `candidate.json`. All 12 listed payload files were
independently rehashed against the manifest after collection.

| File | Bytes | SHA-256 |
|---|---:|---|
| `zephyr.elf` | 374948 | `f9fb571e13c85e859776d343c857f2005e7b3aa09210f480d68c6be421b0239f` |
| `zephyr.bin` | 29204 | `3cf151d5d0cbc3e038f24060a751c7cd1ef331a34fcd85d45115f77f8b13a86c` |
| `zephyr.map` | 305838 | `13f6a77c9bc98f4bf318aa496008cc5ea926fe38a95cd321f49d49e5606769e1` |
| `.config` | 28532 | `723e9acfbd11ffd3d0e8150955627601b2591ddce5ac4866f6864eecca89e46d` |
| `zephyr.dts` | 5565 | `2384e9b0108f186557e53ac0b6755e3c291c4b7b61bcce79845c2a57396f12ec` |

`candidate.json` SHA-256:
`ff3e608d0dedfad0bd44dbd9937ea00ab2a88a3847d66416c6f442e08606bfa4`.
Remaining payload hashes and external runtime member hashes are in that manifest.

Entry/load origin: `0x30080000`; allocation: 36,832 bytes of the candidate 512 KiB
link region, 7.03%. ELF32 little-endian RISC-V, double-float ABI, 16-byte stack
alignment; compile flags are `rv32imafdc_zicsr_zifencei` / `ilp32d`. Nominal SRAM
is 1 MiB and PSRAM 16 MiB; this does not prove installed-loader RAM availability.
`loadable_image` is false: raw ELF/bin are not a confirmed vendor container.

## 8. Remaining blockers

- Installed bootloader identity, accepted container/signature format and a
  confirmed recoverable RAM loading method.
- Actual SRAM reservations/staging/stack/heap/DMA and entry privilege/CSR state.
- Board revision, UART wiring/electrical levels, clock and power-hold handoff.
- Measured timer behavior, interrupt return, FPU switching and cache/map state
  on a physical D133ECS board.

Software checks can be rerun without hardware; they cannot close these blockers.
No guessed flashing command, bootloader replacement or partition operation exists
in this delivery.

## 9. Next bounded action

Obtain the installed-loader boot log and verified RAM/UART handoff evidence, then
resolve `bringup/d13x-boot-contract.md` before authorizing a recoverable board test.
Use `bringup/d13x-z0-validation.md` for acceptance: ten cold boots, sustained
combined kernel/FPU execution and retained failure diagnostics. Keep Z1 and later
peripheral work outside this delivery.
