# Read-only SPL identity and static-range audit

Follow-up date: 2026-09-25. No product/SDK file, firmware runtime, reference Zephyr
tree or physical hardware was modified. The tool is a software evidence gate,
not a FIT packager, flash command or hardware acceptance certificate.

## Reproduce

Run from the zephyr-artinchip root using the existing project Python environment:

~~~powershell
$sdkOutput = 'C:/Users/JCSH/Documents/Project/D50T-2-Lite/luban-lite-jc-d50t-rev/output'
.venv/Scripts/python.exe scripts/audit_loader.py --product "$sdkOutput/d13x_d50t-2-lite_rt-thread_D50T-2-Lite/images" --loader "$sdkOutput/d13x_d50t-2-lite_baremetal_bootloader/images" --candidates artifacts/r1-delivery/candidates --output artifacts/h0-loader-audit/report.json
~~~

Choose a new output filename for another run. Output is forbidden inside any
input directory. The tool never runs vendor utilities or accesses a device.

Exit codes:

- 0: local byte association and the modeled static ranges pass. H0 remains blocked.
- 2: a valid inspection found a loader identity mismatch or static overlap. The
  JSON report is retained and the result must not be counted as a pass.
- 1: invalid input, corrupt data, unsupported layout or unsafe output path.

The CLI validates AIC.FW boundaries, every component CRC, duplicate/overlapping
records, and equality of the updater and target SPL. It binds the packaged raw
loader to those actual components. It then verifies the separate loader raw bin
against the complete suffix of its ELF PT_LOAD, including section gaps, and
compares every byte of the packaged loader by ELF section/symbol. No banner or
data difference is silently ignored or automatically allowed.

Every candidate's existing payload manifest is checked, and its ELF is parsed
again. Full PT_LOAD memory sizes, including BSS, are compared against the known
reference loader PT_LOAD and default heap; stack symbols are checked to lie in
the modeled loader segment. This is NOT a complete RAM ownership model: PBP,
additional/reserved heaps, DMA, temporary buffers, memory aliases/TCM and actual
installed-state evidence are outside these static spans.

## Historical result (superseded for current Sep24 product)

artifacts/h0-loader-audit/report.json records exit 2 / audit_status=BLOCKED:

- All container component CRCs pass and the same raw SPL is found inside the
  updater and target components.
- The separate loader ELF/bin pair matches exactly under the fixed raw-bin
  profile. Its executable section bytes match the packaged September 21 SPL.
- Nine bytes differ in .rodata build banners and one in the rgb .data object.
  The binaries are not identical; the ELF remains reference-only for this gate.
- None of the three Zephyr candidate PT_LOAD spans overlap the reference
  [0x40c00000, 0x40c442b8) loader segment or [0x40c80000, 0x41000000) default heap.
- hardware_validation=pending, handoff_status=BLOCKED, loadable_image=false.

The byte-level association narrows the earlier version mismatch, but does not
prove live memory ownership or CPU/cache/interrupt handoff. It cannot authorize
loading at 0x30080000 or changing the product's NAND partitions.

## CI follow-up

Remote run 36096131063 at 6dfaf90 completed with FAILURE. Bootstrap passed;
host tests had 52 passes and one failure in test_local_archive_is_included.
The assertion compared a resolved archive path with an unresolved temporary
root. This can fail for a Windows temporary-directory alias/junction even when
the archive belongs to that directory. The fix canonicalizes the comparison
root; a parent-directory alias regression also checks the archive and direct
object identities. Production archive parsing was not weakened.

The failure archive's staging, upload, download and hash verification all passed
on GitHub. A separate local download was verified at
artifacts/ci-36096131063/software-evidence.zip. It contains three failure logs and
no candidate success index. Thus failure-path transport has remote evidence;
successful candidate transport was still pending at that snapshot. This failed
run did not execute QEMU or D13x builds. Follow-up run 36099116552 at a607310
subsequently passed the complete workflow and independent downloaded-archive
verification, including all three .config files; see validation-r1-report.md.

The original audit host suite passed 75 tests (53 previous + one path-alias case
+ 21 loader-audit cases). Log: artifacts/logs/h0-host-loader-audit.log. Original
R1 firmware/QEMU results remain historical evidence; these host-tool changes do
not constitute a new target run. The CI fixture correction had not yet been
validated remotely at that snapshot; run 36099116552 subsequently passed it.

## Next hardware-dependent boundary

The current Sep24 packaged/updater/target SPL matches the available ELF/bin with
zero changed bytes; retain the Sep21 mismatch above as historical evidence.
Analyze the matching Sep24 loader dynamic memory and CPU handoff.
Confirm the recoverable RAM download or partition-selective aiburn path, then
close the remaining H0 fields before generating a loadable Zephyr FIT/container.
No loader replacement, product-data rewrite or Z1 peripheral expansion is part
of this audit.

## H0 closure follow-up

Current product SHA-256 is b0062dacbd68e8ef6f6de0c99c7cdc6620e602c5e00e913b454af6e93037aaf1.
The preserved rebuilt audit refers to historical f2ce05e candidates. New closure
candidates must have fresh build receipts and a new audit under artifacts/h0-current.
Static disjointness is static_memory_overlap=pass, never ram_ownership=verified.
