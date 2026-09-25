# Fixed-slot diagnostic container: offline review

Status: H0 BLOCKED; loadable_image=false; hardware_validation=pending;
recovery_verified=false. No flash, USB, serial or AiBurn operation occurred.

`scripts/test_image.py` now builds and separately verifies an offline AIC.FW
container containing the 32397e5 handoff probe FIT. The original SDK image is
read-only and pinned to SHA-256
`b0062dacbd68e8ef6f6de0c99c7cdc6620e602c5e00e913b454af6e93037aaf1`.
Candidate manifest/receipt, matching-loader audit and FIT payload/load/entry are
validated before substitution. Output must be a fresh directory outside input
directories. The script does not execute commands from inputs.

## Deliberately restricted layout

The replacement must fit both the original OS component span and declared OS
partition capacity. No relocation, partition growth, media change, component
rename or version change is supported. The total container length and all
component offsets remain unchanged. Only OS metadata size_in_img and crc change;
the old OS span contains the exact new FIT followed by 0xff. The unused tail is
outside the new declared OS component. This is file padding, not an instruction
to erase the remaining NAND partition. Header/image.info stay byte-identical.

SDK mk_image.py stores actual payload length and CRC in metadata and separately
aligns the next file offset. The local artinchip-flash parser extracts components
by explicit metadata offset/size, and device.rs reads the same pair when sending
a component. This supports the fixed-offset study layout, but does not attest
the installed AiBurn binary's acceptance, erase/write set or recovery behavior.

Verification re-parses both containers, checks all CRCs, checks inventory and
capacity, compares every byte outside the two allowed ranges, compares the exact
FIT and retired-slot fill, and compares every non-OS component. It does not call
the constructor to derive expected output. A repaired component CRC cannot hide
an unauthorized change elsewhere.

## Reproduction

Use `.venv/Scripts/python.exe scripts/test_image.py build` with:

- `--reference`: the pinned product `.img` in the read-only SDK output.
- `--fit artifacts/h0-early-uart/fit/candidate.itb`
- `--manifest artifacts/h0-early-uart/candidates/handoff_probe/candidate.json`
- `--audit artifacts/h0-early-uart/loader-audit.json`
- `--output`: a fresh directory such as `artifacts/h0-test-image-v2`.

Use mode `verify` with the same inputs and `--output` pointing to the generated
file. Both modes return 2 when offline verification passes but loading remains
BLOCKED; invalid inputs return 1. Neither reports a passing hardware gate.

## Recorded result

Artifact: `artifacts/h0-test-image-v1/probe-offline-only.aicfw.bin`

Size: 2771456 bytes. SHA-256:
`ba7aa7287eabf856a05f4faaa54f384ec542b1795dbb79164aa2b46da016708b`.

OS size: 1400832 -> 19868 bytes, starting at container offset 600576.
Allowed change intervals, half-open: metadata [5260, 5268), OS slot
[600576, 2001408). All other bytes, including updater, target SPL, env/env_r,
rodata/data and image.info, compare equal. The standalone verify invocation also
passed. Full report: `artifacts/h0-test-image-v1/report.json`.

114 host tests passed, including rejection of empty/oversize payloads,
CRC-repaired non-OS changes, partition changes, padding changes and truncation.
No firmware source changed in this step; the prior target build remains the
probe's build evidence. This container has not been accepted or booted by AiBurn.

Before physical delivery, resolve live SRAM/TCM alias and DMA ownership and the
loading/recovery procedure. Keeping non-OS component bytes unchanged does not
mean a whole-image burn leaves those NAND regions unwritten. Do not rename this
study artifact into an approved test image or mark it loadable based on the
offline verification result.
