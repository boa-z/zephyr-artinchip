# Z0.H0 closure investigation — 2026-09-25

Z0.H0 remains **BLOCKED**. Z0.H1 is **NOT_RUN**; hardware_validation=pending,
loadable_image=false, recovery_verified=false, upstream_ready=no.
P0 and Z0.R1 remain historical software PASS; this work is four fresh target
builds plus host analysis, not another QEMU run or physical validation.

## Evidence and reproducible artifacts

Current runtime source: `53351bb86cec3094c179f0a151336daa2ae95870`, clean at build.
All four applications were freshly built with scripts/build_candidate.py and
packaged with scripts/package_candidate.py. Receipts record tools, generated
config/DTS, link inputs and source inventory. Later collector/documentation
changes do not change that immutable source_at_build; no runtime changes follow
this build. Historical f2ce05e candidates were not used for these results.

| Candidate | ELF SHA-256 prefix | Entry | Raw bytes | FIT roundtrip |
|---|---|---|---|---|
| bringup | 10d7fc73b902051a | 0x30080000 | 26744 | PASS |
| kernel | 405d27cbf67d3528 | 0x30080000 | 32972 | PASS |
| fpu | 41fdfe7741e5a44d | 0x30080000 | 33464 | PASS |
| handoff_probe | 5fa7f4e72d74e3e8 | 0x30080dd8 | 18852 | PASS |

Artifacts (repository-relative, local and not published):

- `artifacts/h0-current/53351bb/candidates/<app>/`: candidate.json, ELF/bin/map,
  generated config/DTS and build receipt.
- `artifacts/h0-current/53351bb/loader-audit.json`: current loader/candidate byte
  binding, PT_LOAD file/memory spans, static ranges and overlap result.
- `artifacts/h0-memory/loader-memory-map.json`: linked stacks/heaps/objects,
  source trace with hashes/lines, map-to-ELF key-symbol checks, disassembly,
  dynamic allocation envelopes, lifetimes and explicit unresolved ranges.
- `artifacts/h0-fit/53351bb/<app>/`: candidate.itb, roundtrip.json, verify.json.
- `artifacts/h0-current/53351bb/probe-static/`: entry disassembly and noinit/config
  checks; `negative-fit-checks.json` retains rejection tests on copied inputs.
- `docs/bringup/d13x-h0-closure.json`: compact tracked evidence index and hashes.

The initial 6806d29 candidates used the historical incorrect core addresses and
are superseded, never a loading candidate. The initial FIT checker rejected real
objcopy 0xFF section-gap padding. It was corrected to the receipt's exact profile,
with a regression test; payload bytes were not changed. The initial memory report
is preserved as loader-memory-map-initial.json; the canonical report additionally
checks map symbol values against ELF. Memory audit exits **2**, deliberately.

## Current loader and memory result

Known-good product SHA-256:
`b0062dacbd68e8ef6f6de0c99c7cdc6620e602c5e00e913b454af6e93037aaf1`.
Sep24 16:30:14 packaged/updater/target SPL and local ELF/bin have zero changed
bytes. ELF/map exist and selected map symbols match. Sep21 ten-byte mismatch is
retained as historical/superseded. Owner-reported USB programming is not readback.
Sep25 14:16:45 product application and 115200 console are owner observations.
0x101 includes SYS_POR and EXT_RST; the decoder chooses EXT_RST. This does not
contradict the owner's main-power restart.

ELF-derived ranges, exclusive ends:

| Region | Start | End | Meaning |
|---|---|---|---|
| Loader PT_LOAD | 0x40c00000 | 0x40c442b8 | text/data/BSS/stacks/boot arguments |
| IRQ stack | 0x40c3df80 | 0x40c3ff80 | 8192-byte extent, peak unknown |
| Normal stack | 0x40c3ff88 | 0x40c41f88 | 8192-byte extent, peak/alignment at jump needs observation |
| Default heap | 0x40c80000 | 0x41000000 | linked heap_def[0] |
| Reserved heap | 0x40000000 | 0x40c00000 | linked heap_def[1], type 3 |

The linked heap_def table has four 16-byte entries; the final two are zero.
heap_init initializes valid entries then returns an error on an empty entry;
current board_init source ignores this return. This is evidence about the
existing loader, not a proposed loader modification or a claim of corruption.

Path: main selects nand_boot -> MTD os -> spl_load_simple_fit -> header/tree
allocations in MEM_DEFAULT -> FIT firmware seg0 external offset/length ->
spl_read -> mtd_spinand_read -> spinand_read/page/QSPI -> CRC32 -> optional
cipher branch -> optional config DTB -> boot_app -> entry.
The generated FIT contains no cipher/compression operation. No decompressor or
relocation beyond the explicit destination copy is requested by this profile.

The header allocation is rounded to the media block size. The FIT tree allocation
is ALIGN_UP(totalsize,4) for NAND, and both are freed before return. NAND creates a
page+OOB per-read bounce buffer (freed at exit) and a persistent cache-line-aligned
page/OOB buffer. Full aligned pages can read into the destination, while partial
pages copy only the requested bytes. QSPI may use DMA, with descriptors in the
linked aich_dma object, destination derived from the read buffer, synchronous
completion/stop and cache invalidation. Thus candidate payload writes intentionally
overlap candidate SRAM; the known heap envelopes do not.

boot_arg is a linked object returned by aic_get_boot_args. Optional config DTB
uses a fixed PSRAM tail destination with a DTB-derived size; the supplied product
log says No config partition. Absence in that log is not a universal guarantee.
Default/reserved allocator envelopes alone do not prove all bus-master targets,
PBP/TCM aliases, pointer lifetime or maximum IRQ/normal-stack use. Current source
and DWARF function associations are not a reproduced compiled-config receipt.
**We cannot yet exclude every live overwrite/alias of [0x30080000,0x30100000).**
static_memory_overlap=pass therefore does not imply ram_ownership=verified.

## CPU handoff and corrected core addresses

SDK Kconfig.chip defines CPU_BASE=0x20000000 when !QEMU_RUN and 0xe0000000
only under QEMU_RUN. Matching ELF SystemInit accesses CLIC at 0x20800000;
aic_get_time_us accesses mtime at 0x2000bff8. The old d133ecs.dtsi had selected
QEMU addresses. This turn corrected CLIC, mtime and mtimecmp to 0x20800000,
0x2000bff8 and 0x20004000 and rebuilt all applications. This is source/binary
validation, not a physical MMIO test. QEMU virt's own board was not changed.

Matching boot_app cleans data cache, invalidates instruction cache, clears
mstatus.MIE and tail-jumps to the entry with a0=boot device and a1=boot_arg.
It does not establish all pending IRQs cleared, DMA quiescence, cache disabled,
FPU reset, TCM/map state or an ABI-aligned incoming stack. Vendor cache instruction
encodings are retained in disassembly; GNU standard objdump leaves them as raw
instructions, so source names are not presented as independent instruction decode.
Protocol EXEC is a different handoff and must not bypass these requirements.

Probe aic_handoff_entry is ELF entry 0x30080dd8. It is a 200-byte stackless wrapper;
its 132-byte, 16-byte-aligned SHT_NOBITS snapshot at 0x30084f40 is within its owned
candidate PT_LOAD memory span. Disassembly confirms no CSR writes, no loader-stack
access, no gp modification, and a tail jump to Zephyr __start after capture.
It preserves incoming sp/gp/a0/a1 in the snapshot, reads mstatus/mie/mip/mtvec/mtvt,
mexstatus/mxstatus/mhcr, guarded fcsr, CLICINFO, coherent mtime and eight SDK-defined
SYSMAP address/config pairs. It skips unknown TCM controls. Privilege is an M-mode
expectation, not something inferred from mstatus.MPP. The snapshot is sequential,
not an atomic freeze of changing pending interrupts or timer state.

The probe prints a source identity, entry, buffer address/size and sequence marker
once the normal console is available. The exact ELF hash stays in candidate.json
and the expected-output sidecar: embedding the final ELF's own hash would create
a self-reference. Firmware honestly prints ELF_SHA256=external:candidate.json.
No CAN/display/DMA/filesystem/network/PSRAM application use is enabled. This does
not turn off or validate inherited peripherals. No probe has run on hardware.

## Remaining closure gates

| Work package | Result |
|---|---|
| A current evidence | Recorded; historical mismatch preserved |
| B fresh current runtime candidates | Four clean receipt builds and static audits PASS |
| C dynamic RAM | Bounded model and binary trace produced; ownership BLOCKED |
| D FIT adapter | Four CRC32/MD5 external-data FIT roundtrips PASS, loadable=false |
| E recovery | Source capability review and plan; manual recovery unverified |
| F probe | Built and statically inspected; physical capture NOT_RUN |
| G H1 delivery | Intentionally not generated: memory, recovery and authorization gates unmet |

See d13x-recovery-plan.md for RAM-only limitations, OS-selection risks and the
human recovery sequence. No whole-product AIC.FW, H1 directory, hardware action,
push, release or upstream PR was produced. Human DCO remains pending.

## Offline reproduction

From a clean committed checkout with the pinned, isolated patched Zephyr tree
and SDK environment selected, use a NEW short build directory for each app:

~~~powershell
.venv/Scripts/python.exe scripts/build_candidate.py handoff_probe C:/aic-new-probe
.venv/Scripts/python.exe scripts/package_candidate.py C:/aic-new-probe artifacts/new/candidates/handoff_probe
~~~

Repeat bringup/kernel/fpu with their own fresh build paths. Then invoke
scripts/audit_loader.py with --product and --loader pointing to the matching
read-only SDK image directories, --candidates to the complete new candidate root,
and --output to a new report file. Invoke scripts/audit_loader_memory.py with
--sdk, --audit, --objdump and a new --output path. Exit 2 means the bounded report
was produced but memory ownership is BLOCKED; do not treat it as a passing gate.

~~~powershell
.venv/Scripts/python.exe scripts/build_zephyr_fit.py artifacts/new/candidates/handoff_probe/candidate.json --audit artifacts/new/loader-audit.json --output artifacts/new-fit/probe
.venv/Scripts/python.exe scripts/verify_zephyr_fit.py artifacts/new-fit/probe/candidate.itb artifacts/new/candidates/handoff_probe/candidate.json --audit artifacts/new/loader-audit.json
~~~

FIT tools accept only the recorded objcopy profile and candidate receipt/files
bound to the static audit. They never execute commands embedded in input receipts.
Malformed layouts, unexpected nodes, changed payloads, addresses, hashes, receipts
or unsupported conversion options fail nonzero. Output paths must be fresh.
The FIT contains only one firmware node with external data, CRC32 and MD5 as in
the product reference; CRC32 is the current loader's checked hash, not authentication.
No script here generates a whole-product image or communicates with a board.

Final host verification: 97 tests PASS (artifacts/logs/h0-closure-final-host.log),
lint PASS, provenance PASS, diff whitespace check PASS. Five additional offline
negative checks rejected altered candidate bytes, rehashed receipt inconsistency,
truncated/trailing FIT data and a changed hash algorithm. No hardware test ran.

Follow-up offline tool review: [pre-board observations](d13x-preboard.md) records
the installed upgcmd RAM-to-shell call chain and a reproducible hash-bound audit.
It does not close the RAM ownership/recovery gates or change firmware candidates.
Follow-up validation: 101 host tests PASS; lint and provenance PASS. The installed
tool audit matched its reviewed hash and returned exit 2 (BLOCKED), as designed.
No board connection, firmware execution, flashing or recovery rehearsal occurred.
