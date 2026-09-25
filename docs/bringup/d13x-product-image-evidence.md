# D50T product image and reported boot evidence

Recorded 2026-09-25 from the owner's supplied image path and pasted boot log.
This is a user-reported physical observation, not an agent-operated board session.
The pasted banner contains Markdown/HTML transformations; it is not a raw serial
capture suitable for byte-level transcript verification.

## Reported observation

The owner reports using aiburn to program:

    C:/Users/JCSH/Documents/Project/D50T-2-Lite/luban-lite-jc-d50t-rev/output/d13x_d50t-2-lite_rt-thread_D50T-2-Lite/images/d13x_D50T-2-Lite_page_2k_block_128k_v1.0.0.img

Relevant verbatim lines from the supplied log:

~~~text
Pre-Boot Program ... (26-09-09 13:35 16 03 e789a89)
SPINAND
Psram_init done.
goto run SPL
tinySPL [Built on Sep 21 2026 10:40:26]
Reset flag: 0x501
Reset action: Watchdog-Reset, reason: Command-Reboot
Start-up from os
Selecting default config 'Luban-lite firmware'
spl read: 1397692 byte, 85590 us -> 15947 KB/s
CRC32 verify OK.
No config partition
359897 : Run APP
Welcome to ArtInChip Luban-Lite 1.3.2 [D13x Inside]
Image version: 1.0.0
Built on Sep 23 2026 14:19:37
Boot device = 5(BD_SPINAND)
[   0.697] I/d50t.boot: D50T-2-Lite platform bootstrap; D133ECS / PSRAM 16 MiB
aic />
~~~

The observation establishes a reported working product boot/console path and
reported PSRAM initialization. This particular log identifies a command-triggered
watchdog reset; it is not evidence of an independent power-on cold-boot trial.
Printed part/capacity strings are not PCB marking or memory measurements.

## Read-only local findings

Machine-readable byte-level results are in d13x-product-artifacts.json, including
SHA-256 identities, parsed container offsets, FIT properties and reference source
hashes. The product image is 2,771,456 bytes with SHA-256:

    5cdef86d5561f2d928d3408c6a669f4fff521a1739502983d16673344dc8f01c

The actual AIC.FW archive has nine metadata entries. All component CRC32 checks
pass; eight file-backed components match the named companion files exactly.
The ninth entry is the archive's own information header, not a missing firmware.
The embedded OS FIT is identical to d13x_os.itb. Its external seg0 data matches
seg0.bin and d13x.bin; both its CRC32 and MD5 checks pass. Its tree has no signature
node. These facts establish this local container's content, not all installed
security policy or acceptance of a different payload.

The named image and its generated companion files exist. The generated
d13x_os.its describes FIT firmware seg0, RISC-V, ArtInChip OS, load/entry
0x40000000, with CRC32 and MD5 nodes. Its seg0.bin is 1,397,692 bytes, matching
the reported SPL read length. This correspondence supports the source/artifact
association but is not an installed-loader hash readback.

Generated image_cfg.json lists USB RAM updater components and separate target
components: SPL, env/env_r, OS, rodata and data. It describes loader.aic at
0x40c00000 with entry 0x40c00100. These are reference artifact parameters, not
addresses selected for a Zephyr download.

### Important loader mismatch

The packaged bootloader.bin contains Sep 21 2026 and 10:40:26, matching the
owner's tinySPL banner. Its complete bytes occur exactly at offset 256 within
loader.aic and offset 23,808 within bootloader.aic; that bootloader.aic matches
both the updater and SPL target components in the supplied .img.

The separate output/d13x_d50t-2-lite_baremetal_bootloader/images/d13x.elf and
d13x.bin belong to a newer local build (Sep 24 2026 16:30:14). That bin differs
from the packaged September 21 bin. Its ELF shows entry 0x40c00100, load span
starting 0x40c00000, stack symbols in that PSRAM region and heap
[0x40c80000, 0x41000000). These are NOT established addresses for the installed
September 21 SPL. Matching the packaged September 21 binary to an ELF/map or
equivalent memory ownership evidence is the next specific handoff requirement.

The raw loader binaries have equal lengths and differ in ten bytes: nine belong
to build date/time text, but one differs in initialized data at raw offset
0x3cca8 (packaged 0x01, separate build 0x00). The newer ELF maps this byte to
0x40c3cda8 within its rgb data symbol. Do not dismiss the mismatch as timestamps
alone; no display configuration changes are made as part of this Z0 audit.

The Zephyr candidates use a different entry/allocation in SRAM. Their current
raw .bin files do not carry the FIT or whole-device AIC.FW container metadata.
Do not substitute a raw bin for this product .img or modify the product output
directory. An adapter must preserve the confirmed loader/product partitions and
must validate RAM ownership, copied/decompressed spans and CPU/cache handoff.

## Remaining gates

The follow-up reproducible loader comparison and actual CI transport result are
recorded in loader-audit.md. The new tool confirms identical executable bytes
and no overlap with the reference ELF's known static spans; it continues to
reject the ten-byte identity mismatch and does not close runtime RAM ownership.

This evidence advances H0 but does not close it. Still required: exact board and
installed loader association; loader/staging/stack/heap/boot-argument/DMA memory
ownership; accepted download/verification path; CSR/cache/IRQ/power handoff;
actual UART pins/levels/clock; and a confirmed recovery procedure before an
authorized hardware session. No Zephyr hardware validation or flash action was
performed. loadable_image remains false.

The intended next implementation is a separate Zephyr FIT/loading adapter for
the confirmed loader, preserving the existing SPL and product data. The exact
non-destructive RAM download path or partition-selective aiburn workflow must
be verified before generating a loadable test delivery. No whole-product image
replacement, loader rebuild or automatic programming follows from this log.
