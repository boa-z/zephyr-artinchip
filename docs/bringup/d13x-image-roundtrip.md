# Original OS refill and early probe output

This is offline development evidence, not a diagnostic image delivery.
H0 remains BLOCKED; hardware_validation=pending; loadable_image=false.

## Lossless container rehearsal

Run `scripts/image_roundtrip.py SOURCE FRESH_DIRECTORY` with the known-good
product image. Its SHA-256 must equal
`b0062dacbd68e8ef6f6de0c99c7cdc6620e602c5e00e913b454af6e93037aaf1`.
The script validates component CRCs/bounds with the existing container reader,
extracts components and all intervening opaque bytes to numbered files, rereads
those files, and reconstructs the whole container. The original OS is included
as its own extracted/refilled component. Header, metadata and padding are
preserved, not regenerated. `image.info` aliases the header and is not a second
write range. Names embedded in the image are never used as filesystem paths.

The reconstruction must be byte-identical, including padding. Wrong baselines,
modified chunks, changed inventories and reused output directories fail. A
partial output directory after an I/O failure is not a passing delivery; use a
new directory on retry. No replacement-OS interface is provided yet.

Real-image run: `artifacts/h0-image-roundtrip/original-os-v1/report.json` reports
PASS, 0 changed bytes and no component changes. The reconstructed file is named
`original-os-refilled.aicfw.bin` to distinguish this rehearsal from a new
diagnostic `.img`. This proves lossless extraction/refill, not metadata rewriting
for a differently sized OS, NAND write behavior or acceptance by AiBurn.

## Probe observation changes

Owner reports COM11 at 115200 and no debugger interface. The latest pasted
Reset log shows matching Sep24 loader/Sep25 application banners, successful OS
CRC, `No config partition`, and reset flag `0x100` (External-PIN-Reset). This is
owner-supplied text, not a captured raw serial file or flash readback.

After recording its existing entry snapshot, the probe now attempts
`H0-PROBE stage=snapshot-before-zephyr` on inherited UART0. It reads the UART
address from devicetree, checks LCR.DLAB before writing THR, and bounds the
LSR.THRE poll at 65536 iterations per character. No clock, baud divisor, pinmux,
FIFO or UART interrupt settings are changed. The early path has no C calls and
uses only the existing t0..t4 scratch set. Main prints the recorded UART status:
1 attempted, 2 all bytes submitted, 3 skipped because DLAB set, 4 poll timeout.

This marker follows the entire snapshot; a fault during snapshot acquisition can
still prevent output. Poll bounds do not bound stalled bus transactions and are
not milliseconds. LSR reads may clear UART error flags. Status 2 means bytes
were submitted, not that the host received them or the transmitter drained.
The path requires the inherited UART mapping and configuration to be usable.
No physical UART result is claimed.

The changed probe requires a new ELF/bin/map/receipt and a new loader/FIT audit;
historical 53351bb probe artifacts do not include this output and must not be
relabeled. Other firmware applications have not changed.

## Remaining work before a test image

Implement and independently verify bounded OS replacement and required metadata
updates only after the container write semantics are established. Preserve all
non-OS components and report metadata changes separately. Close RAM/TCM alias
and DMA/lifetime questions before loading the probe. A probe cannot retroactively
prove the loader's earlier writes were safe. Recovery and physical operation
remain separate gates; no board access or flashing is part of this rehearsal.
