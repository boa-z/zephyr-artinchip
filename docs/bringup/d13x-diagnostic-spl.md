# Isolated diagnostic tinySPL: offline build evidence

The owner accepted the proposed isolated tinySPL instrumentation scope by asking
to continue after the explicit scope question. Reference SDK/PBP modification,
board operation and flashing remain outside this step. The original prohibition
on modifying tinySPL is superseded only for this isolated diagnostic work.

## Baseline reproduction

Reference SDK:
`C:/Users/JCSH/Documents/Project/D50T-2-Lite/luban-lite-jc-d50t-rev`.
Disposable copy: `C:/aic-h0-sdk-baseline`. Source was copied from the working SDK
including its product changes, excluding `.git`, output, logs, bundled tools/env
and toolchain. The toolchain directory in the copy is a junction to the reference
toolchain and was used only to execute compiler/binutils. Compiler output and
generated configuration/linker files remain in the copy.

Build environment: project venv Python 3.13, SCons 4.11.1, kconfiglib 14.1.0,
SDK's existing riscv64-unknown-elf toolchain; Git usr/bin supplies shell tools.
A venv-local `python3.exe` copy resolves the SDK's python3 commands. The initial
configuration invocation hit Windows Store's python3 placeholder and returned
an erroneous success status; that attempt is not build evidence. Configuration
was rerun successfully with the interpreter fixed. Commands, in the SDK copy:

```text
python -m SCons --apply-def=d13x_d50t-2-lite_baremetal_bootloader_defconfig
python -m SCons -j8
```

Baseline files/logs are archived in `artifacts/h0-spl-baseline/`. Compared with
the matching Sep24 loader:

- BIN length is 253552 bytes in both builds.
- `.text`, `.eh_frame` and `.data` bytes, section addresses/sizes and BSS layout
  match. This is stronger evidence than source-symbol presence alone.
- Exactly 13 BIN bytes differ, all in two compilation-time strings and the
  compilation-date string in `.rodata`; byte ranges/contexts are retained in
  `byte-differences.json`. No timestamp was patched to fabricate exact identity.
- Rebuilt BIN SHA-256:
  `7727c0ec57f7824cf9c26d2a2c273e8a2889dd60131342ddd8e403126022d00d`.

This reproduces the loader's executable bytes from the current working SDK;
it is not a readback of installed flash or proof of inherited PBP state. Earlier
memory reports' missing-reproduction blocker should be read with this follow-up
evidence; their historical reports have not been rewritten.

## Instrumentation

Original code is in `diagnostics/tinyspl/h0_diag.c` and `.h`. The documented
derivative is `diagnostics/tinyspl/patches/0001-h0-observation.patch`.
`scripts/instrument_tinyspl.py` applies guarded edits to a separately configured
copy and records source/output hashes. It rejects reference/nested destinations,
changed contexts, repeated application and unexpected QSPI stop-call counts.
It does not build, package or operate hardware itself.

The recorder has 256 fixed 16-byte records, no dynamic allocations and no prints
in event/IRQ paths. Short local IRQ masking serializes recording; this is itself
an instrumentation effect. Records saturate rather than wrap; dropped records
are counted. Boot refuses the payload jump if records were dropped.

| Kind | Address | Size field | Result field |
| --- | --- | --- | --- |
| 1 | FIT read destination | requested length | source offset |
| 2 | FIT read destination | requested length | signed read result encoded u32 |
| 3 | payload load address | payload length | source offset |
| 4 | NAND page+OOB buffer | allocation size | zero |
| 5 | freed NAND page+OOB buffer | zero | zero |
| 6 | QSPI DMA channel object pointer | zero | existing stop return code encoded u32 |
| 10 | stage | entry mstatus before recorder IRQ masking | mie |
| 11 | stage | mtvec | mhcr |
| 12 | SYSCFG address | stage | raw register value |
| 13 | SYSMAP address/config register address | stage | raw register value |
| 14 | DMA channel enable-register address | stage | raw register value |

Stages: 1 before FIT header reads, 2 before an external payload read, 3 in
boot_app before its existing final cache maintenance/IRQ-disable sequence.
UART output begins after stage 1 capture and the event list is printed after
stage 3 capture. Stage 3 is **not** the final state at the payload instruction:
the original cache operations and MIE clear still occur afterward. The existing
OS entry probe complements this with a later snapshot.

Source-defined register reads cover SYSCFG+0x160, 16 SYSMAP words and eight DMA
channel-enable registers. No undocumented TCM CSR is probed. No extra DMA stop
or peripheral reset is issued: the QSPI hook records results of existing calls.
This first version does not capture every DMA descriptor, persistent NAND buffer,
allocator consumer, FPU CSR, stack high-water mark or display/USB bus master.
MMIO faults/stalls and serial failures are not caught. Raw register values are
not interpreted as proof that all aliases or bus masters are safe.

## Diagnostic build and checks

Final files: `artifacts/h0-spl-diagnostic-v2/`; the receipt binds ELF/BIN/MAP,
configuration, compiler identity, patch inputs/outputs and the build log.
PT_LOAD is [0x40c00000, 0x40c457c8); default heap remains
[0x40c80000, 0x41000000). Static overlap with the current probe: none.
The final build reports text 243756, data 11056, BSS 29512 bytes.
Disassembly confirms h0_dump precedes the original cache/MIE/jump sequence.

Initial diagnostic compilation found a format-type warning and a missing brace
around the buffer-free hook. Both were corrected and rebuilt. The final log has
no diagnostic C warnings; a pre-existing SDK preprocessing warning,
`cc1.exe: warning: is shorter than expected`, also occurs in the unmodified
baseline and remains recorded. It was not suppressed.

120 host tests, lint and provenance checks pass. Host tests cover patch drift,
preserving conditional free semantics and protecting the reference tree; they
do not execute the diagnostic recorder on a target. Seven copied `.pbp` files
remain byte-identical to the reference, and the original known-good whole-image
SHA-256 remains `b0062dacbd68e8ef6f6de0c99c7cdc6620e602c5e00e913b454af6e93037aaf1`.

No image containing the new SPL was generated. The previous offline probe
container still contains the original SPL and cannot produce H0-SPL logs.
Next packaging must separately bind the new SPL to its AIC header/updater/target
containers and verify preserved PBP bytes and revised loader ranges. Memory
ownership, recovery and physical execution remain unverified:
`loadable_image=false`, `hardware_validation=pending`.

Follow-up: the owner requested progression to a burnable manual experiment.
[H0 observation trial](d13x-observe-flash-guide.md) delivers a separate
observe-only SPL image that returns before all OS FIT reads. It retains the
original product OS and updater, and does not run the transfer-capable diagnostic
revision described above. Its explicit H0 trial readiness is not H1 acceptance.
