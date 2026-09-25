# D13x software candidate boot contract

**HARDWARE_PENDING. This contract is required input to a future loader adapter,
not evidence that the installed bootloader already satisfies it.**

The candidate is linked into the bounded SRAM interval
`[0x30080000, 0x30100000)`. This is a compile-time diagnostic allocation inside
the SDK SRAM S0 region; it has NOT been established as free on the installed
loader. No download/staging address is assigned. PSRAM is not used by Zephyr.
The precise ELF entry and PT_LOAD spans are taken from `candidate.json`, never
inferred from the filename. Raw bin starts at the ELF's first load address.

Required handoff:

1. Single E907 hart in M-mode, no address translation, writable/executable SRAM
   with the selected region free of loader stack/heap/boot arguments/DMA.
2. Interrupt delivery masked before calling Zephyr entry. Bootloader must not
   expect Zephyr to return. Its a0/a1 boot arguments are not a Zephyr boot ABI.
3. Loader completes writes, cleans dirty data for the loaded range and ensures
   instruction visibility. Do not simply invalidate dirty cache lines.
4. The inherited memory map, cacheability, TCM split and SRAM access match the
   allocation. This candidate neither repeats PSRAM training nor resets caches.
5. UART0 remains clocked at 48 MHz with PA0/PA1 function 5 routed to the confirmed
   console; 115200 8N1. PE16 power hold remains asserted if the board requires it.
6. Machine timer's actual frequency is 4 MHz and CLIC legacy layout agrees with
   preflight. Standard Zephyr initialization owns timer/interrupt configuration.
7. Zephyr establishes its own stack (16-byte ABI alignment), gp, BSS, traps and
   FPU ownership. The early hook clears mexstatus SPUSHEN/SPSWAPEN bits 16/17.

Fixed SDK `boot_app.c` cleans data cache, invalidates instruction cache, masks
interrupts and invokes its selected entry; it does not establish every condition
above for a Zephyr payload. `ram_boot.c` parses ArtInChip headers or supported FIT
images depending on configuration. Renaming zephyr.bin is not packaging.
Existing local bootloader output is not confirmed to be installed on the board.

## Collection and eventual packaging

`python scripts/package_candidate.py BUILD NEW_OUTPUT` verifies SRAM spans,
entry, ELF32 little-endian ILP32D flags, allowed ISA attributes, stack alignment
attributes, locally compiled objects and externally linked archive members. It
collects raw ELF/bin/map/config/DTS/compile commands, pinned manifest and explicit
patches with hashes. It refuses an existing output directory.

A successful collection is a software audit PASS with hardware_validation pending,
loadable_image false. Build provenance records the main repository's actual
commit/dirty state; use a clean checkout and rebuild before issuing a candidate.

Container generation is BLOCKED until the installed loader's accepted format,
header/signing requirements, RAM staging address, relocation overlap rules and
entry contract are confirmed. Preserve bootloader, partitions and production data.
Recovery/RAM loading instructions must be supplied from that verified loader;
there is no guessed flash command, bypassed signature or destructive fallback.

Current machine-readable handoff facts and unresolved fields are maintained in
d13x-handoff.yml. Source-derived formats and link ranges are not observed loader
capabilities or free-memory proof; this contract remains blocked until resolved.
