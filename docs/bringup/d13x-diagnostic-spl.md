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

## Transfer-stop follow-up (offline only)

The observation transcript passed its strict checker and the owner confirmed
normal operation after restoring the original product; see the current
[trial record](d13x-observe-image-evidence.md). Recovery no longer blocks offline
development of the next diagnostic stage.

`scripts/instrument_tinyspl.py --transfer-only` now attempts the existing FIT
load and returns -1 after cleanup, dumping evidence with entry zero. A separate
boot_app guard removes the payload call even if that function is called through
another path. Modes are mutually exclusive. Zero-length reads and failed NAND
logical-to-physical translations now emit matching read-end events. Header
allocation failure reaches the diagnostic cleanup path too.

Kind 7 records the FIT attempt's terminal return value (address/size zero).
It is not a success certificate: inherited FIT error paths can retain a
nonnegative return, so a future checker must also check reads and CRC evidence.
The terminal marker is:

```text
H0-TRANSFER-ONLY: FIT attempt ended; no payload jump; return to console
```

The applied, source-bound patch is
`diagnostics/tinyspl/patches/0002-h0-transfer-stop.patch`; apply it to the baseline,
not on top of 0001. Original SDK files were hash checked against the previous
receipt before replacing only the known diagnostic files in the isolated copy.
The reference tree and delivered observation/restoration images were not changed.

Build succeeds in `C:/aic-h0-sdk-baseline`; archived ELF/BIN/MAP, configuration,
build log, disassembly and hashes are in `artifacts/h0-transfer-stop-build/`.
BIN: 254896 bytes, SHA-256
`5262510dfe7a2cb77b4cb4feaf8e21867969184b2ef181cd8d739b70b81d1b0d`.
PT_LOAD: [0x40c00000, 0x40c45808). boot_app disassembly has only diagnostic
output/return paths, with no indirect payload call. The known preprocessing
warning remains; no new C diagnostic warnings appeared. 129 host tests pass.

This is not a new flash delivery. Outstanding work before proposing a trial:

- Bound or summarize per-transfer DMA records: the 256-record buffer may
  overflow across the full product load. Overflow still reports INCOMPLETE;
  the stop mode never jumps even when the trace is complete.
- Add strict transfer-log validation for read pairing/results, allocation
  lifetimes, stop errors and snapshot completeness; the 54-record observation
  checker is intentionally inapplicable.
- Review destination/loader/heap intervals and unresolved aliases before any
  payload writes on hardware, then bind the reviewed binary to a separate
  fixed-profile package. The observe-only packager rejects this binary.

`loadable_image=false`, `hardware_validation=pending`. A successful target build
and removal of the jump do not prove that the preceding payload writes are safe.

### Schema-2 follow-up: bounded DMA summaries and transfer checker

The current transfer-stop patch supersedes the preceding offline binary.
Transfer mode emits schema 2. Kind 16 is a DMA stop summary: channel object
pointer, occurrence count, and exact return code. Only consecutive stop records
are grouped by channel/return code; grouping never crosses another event type.
The first occurrence determines record order, but interleaving within a group
is no longer represented. Errors have distinct records. Counter saturation or
record exhaustion increments dropped and prevents a CAPTURED result. Schema-1
observation mode keeps individual kind-6 records.

Kind 8 records a successful payload CRC check: load address, length and computed
CRC32. `scripts/check_transfer_log.py LOG` requires one schema-2 block, exact
snapshot register sequences, zero sampled DMA enables, paired full reads,
paired temporary NAND allocations/frees, successful stop summaries, payload/CRC
pairing, FIT completion and the stop marker. It rejects dropped records and
returns nonzero on failure. PASS is text consistency only: the printed payload
interval/CRC still needs comparison against the selected image receipt. It does
not cover uninstrumented persistent buffers or all allocator consumers.

Validation: 134 host tests pass, including native execution of the actual C
recorder functions with IRQ stubs. 200000 alternating successful stop calls
use two records; tests also exercise errors, operation boundaries, counter
saturation and record overflow. No IRQ/CSR/MMIO behavior is proven by that test.
Schema-2 parser tests reject failed/short reads, missing CRC/free/snapshot,
duplicate attempts, enabled sampled channels and overflow. Target build passes
with only the already recorded preprocessing warning.

Current build and receipt: `artifacts/h0-transfer-summary-build/`.
BIN: 255152 bytes, SHA-256
`97f6781040fa1fa5ff36d0ecb00fe665bed5ce89aa5df72b1571fe3e61347c4f`.
Applied source hashes: `artifacts/h0-transfer-summary-patch/patch-inputs.json`.

The original product container hash was verified against the restored baseline.
Its FIT was inspected using the isolated SDK's existing `tools/scripts/fdt`
parser (reference-only, not copied into this project); the restricted Zephyr FIT
codec correctly rejects this different layout and was not relaxed. The actual
product seg0 interval is [0x40000000, 0x4015543c), file offset 0x800, length
1397820, CRC32 0xf183bd17; the payload CRC was recomputed successfully. There
is no numeric overlap with this build's loader PT_LOAD or default heap (exact
ranges in the receipt). This is a static virtual-address comparison, not proof
that undocumented aliases or other bus masters cannot touch those bytes.

The repeated-success DMA capacity issue and basic transfer parser are now
addressed. A pathological number of distinct events still fails closed.
Before a flash release, remaining work is runtime interval guarding/profile
binding and review of persistent NAND/DMA buffer ownership and alias assumptions.
No schema-2 physical trace exists yet. The delivered observation and restoration
images remain unchanged; no new flash image is released by this build.

### Guarded original-product trial (2026-09-26)

The subsequent build adds the fixed numeric read guard in h0_diag.h, restricts
the device to SPI NAND and requires the original payload CRC before issuing its
read. Kind 9 records a rejected profile; the log checker fails that attempt.
The CLI checker also binds reported payload and metadata fields to the original
product profile. Native tests exercise lower/upper heap bounds and wrong
payload address/size. The observation profile remains unchanged.

The initial summarized loader wrapper exceeded the original target SPL slot by
1536 bytes; this was a failed packaging check, not a delivered image. Disabling
only CONFIG_AIC_BOOTLOADER_CMD_MEM in the isolated bootloader defconfig removes
unused memory shell commands. The SDK reloads defconfig on every build, so the
defconfig change is required; changing .config alone did not change the build.
The final wrapper is exactly 279568 bytes, equal to the original slot. No
partition relocation or header-layout extension was needed.

Final BIN SHA-256:
`333266456097713f133874dae4afc0fa0b759852c6dfe249a99d4741c2488057`.
`scripts/transfer_image.py` pins this complete binary and the original product
container, validates ELF/BIN association and numeric spans, verifies AIC wrapping
and rejects changes outside target SPL bytes and their length/CRC fields.
The original USB updater and PBP remain exact. boot_app linked instructions were
reviewed again: no indirect payload call remains.

Ownership review: the linked hal_dma_def_v1x driver initializes its free list
from aich_dma.task (static loader storage); descriptors are not allocated from
the payload destination. spinand_init allocates its persistent databuf using
aicos_malloc_align before assigning oobbuf inside the same allocation. These
source facts narrow ownership; runtime pointers and physical aliases are not
fully observed by the current trace and remain outside any H1 acceptance.

Build, applied source/config patches and hashes accompany the offline-verified
manual H0 trial image in `artifacts/h0-transfer-guard-candidate/`. See the
[operator guide](d13x-transfer-flash-guide.md). No board operation was performed
by the agent. The upcoming physical trial, including its restoration, is pending.

### User-reported transfer and restoration result (2026-09-26)

The owner supplied the schema-2 transcript and confirmed normal restoration.
Locally serialized pasted text (including chat escapes, not raw serial bytes):
`artifacts/h0-transfer-user-evidence/user-pasted.log`, SHA-256
`9b9f2229c34a656f2f4eac72d1b2f442aa7dd0002188478906d7630d2fb0773b`.
The corrected checker returns PASS; its report is `check.json` alongside it.

This trial exposed an error in our host checker and synthetic fixtures:
kind-2 SPI NAND returns were incorrectly treated as byte counts. The source
chain is spl_read -> mtdcore.c:mtd_read -> spinand_mtd.c:mtd_spinand_read ->
spinand.c:spinand_read. The wrapper forwards the driver's status (zero here),
not the requested length. The checker now requires zero for this NAND profile,
rejects byte-count-shaped/nonzero values and retains negative-error rejection.
No firmware change or repeat flash is necessary for this host-side correction.
Earlier claims that return-value checking detects short reads were incorrect:
mtd_spinand_read can clamp length to its partition boundary while returning a
status. Requested lengths are recorded, not independently measured. Payload
CRC matching the fixed original-image profile supplies separate content evidence.

Results within the trial's scope:

- 99 ordered events, dropped=0; three paired reads (40, 732, 1397820 bytes
  requested), three temporary buffer allocations/frees.
- Payload [0x40000000, 0x4015543c), offset 0x800, CRC32 0xf183bd17 matches
  the offline-verified original image.
- Stop summaries on channel object 0x40c3d690 report 1 + 1 + 683 = 685 calls,
  all returning zero. These are stop-call counts, not a generic transfer count.
- All three CPU/mapping snapshots have identical values; eight sampled DMA
  enable registers are zero at every snapshot. No payload jump was performed.
- Recovery accepted as `owner_report`; no independent recovery serial capture
  or AiBurn result file was supplied. Do not request repetition for that alone.

The bounded original-product transfer-and-restoration trial is complete.
Its reset banner is Command-Reboot (0x500), not external-pin Reset evidence.
Full alias/persistent-buffer/bus-master ownership and final handoff/Zephyr
execution remain unverified. Overall hardware validation and the H1 loadable
gate remain pending/false; the original delivery manifest is a pre-trial record.

### Next handoff probe readiness review

The existing Zephyr handoff probe remains linked in the candidate SRAM region
starting at 0x30080000. The successful original-product transfer at 0x40000000
does not validate that different region; the existing transfer-stop image also
intentionally rejects the SRAM payload profile. Do not substitute the old probe
FIT into the successful transfer image and assume its gate has passed.

The probe's MTIME high/low/high consistency loop previously retried indefinitely.
It now permits at most 65536 attempts. Exhaustion records sentinel timer values,
selects `H0-PROBE FAIL mtime-incoherent; kernel-not-started` for the bounded UART
path and enters an explicit stop without calling __start. A noinit status word
distinguishes exhaustion from a coherent sample. This bounds retries only;
MMIO bus faults/stalls and UART visibility are not guaranteed. The stop requires
reset and is not a recovery mechanism.

Development target build: `C:/aic-h0-bounded-probe-dev`, 25424 bytes RAM used.
Build log and reviewed entry disassembly are in artifacts/h0-bounded-probe-*.txt
and artifacts/h0-bounded-probe-build.log. Linked code branches to the failure
stop at 0x30080f46 or to __start at 0x30080000; no new CSR addresses were added.
137 host tests and lint/provenance checks pass. This is an uncommitted development
build, not a clean-source delivery receipt or physical execution result. Initial
configuration failed to locate the SDK; setting the existing SDK path resolved
it. The successful build uses a cache outside the reference Zephyr tree.

The next minimal experiment should isolate final handoff from Zephyr startup:
a new standalone, stackless diagnostic confined to the already exercised
original-product destination, with a reviewed entry and bounded serial output,
followed by a deliberate stop. It still needs its own source/build/hash binding,
load/entry/CRC guard profile and review of final cache/interrupt state. It must
not inherit H1 acceptance from the original-product CRC result. No new flash
image is released by this readiness review; no board action is needed yet.
