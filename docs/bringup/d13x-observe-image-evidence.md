# H0 observe-only image evidence

The owner requested completion through a usable manual flashing experiment.
The selected first experiment deliberately stops before OS reads. It is an H0
observation and recovery trial, not a Zephyr H1 load/run release.

Construction: `scripts/instrument_tinyspl.py --observe-only` in the existing
isolated SDK, then the same SCons build. The patched FIT entry's linked body is
34 bytes at 0x40c133aa. Reviewed instructions call h0_begin, call h0_dump(0),
print the stop message and return -1. The caller do_nand_boot checks the error
and returns to the console instead of calling boot_app. Function machine-code
SHA-256 is pinned by the image builder as well as the complete reviewed BIN.

BIN: 247216 bytes,
`ddb228cf1e60f1a22df71cf2cded750c92724b831017c2743b2dc1d6e63f6a72`.
ELF: `d85d34b1ca42b8a93490bda796718dfce57467d1ec40cd170526c46109a53ac5`.

The original AIC wrapper was first recreated with its original SPL BIN and
compared byte-for-byte: exact match. The new wrapper retains the first 23552
bytes (PBP image/header/padding) and all loader private resource bytes. It updates
only second-header checksum, image length, loader length, MD5 offset and private
resource offset, with zero loader alignment padding. New MD5 and additive
checksum are independently checked. Signed/encrypted or unmodeled profiles fail.
New target SPL component length is 273168 bytes, fitting the original slot.

Whole-container changes are restricted to target SPL length/CRC metadata and
its original payload slot. Unused slot bytes are 0xff; no component offsets or
partition fields change. The original updater SPL is retained deliberately:
USB upgrade uses the already-associated original updater, while subsequent
NAND boot runs the observation SPL. Target and updater SPL now intentionally
differ; the old audit that required their equality must not be used for this
experiment. This dedicated verifier binds both explicitly.

Whole image SHA-256:
`0ab10b5c239c859757846ae65db39aa1fff96812d06fc7919be23fe7d491659f`.
All other component bytes match the known-good product, including OS and
image.info. Original recovery image and hashes are included in the delivery.

Validation: 127 host tests PASS; wrapper original roundtrip PASS; new wrapper
checksum/MD5 and resource comparison PASS; container component CRCs, unchanged
regions and written-file readback PASS; observe-only linked control flow reviewed.
The target build succeeded with the pre-existing SDK preprocessing warning
already recorded in the earlier baseline. No physical execution or AiBurn
acceptance is claimed before the user trial.

`artifacts/h0-observe-delivery/` includes the image, restoration image, hashes,
operator guide, ELF/BIN/MAP, config, build log and applied patch/input hashes.
`scripts/check_observation_log.py` validates a single 54-record log and reports
nonzero DMA enable reads without promoting hardware safety. Transfer-time DMA,
all memory aliases, actual device identity and recovery still require evidence.
Operator steps and stop conditions are in [the flashing guide](d13x-observe-flash-guide.md).

## User-supplied board observation (2026-09-25)

The owner supplied a pasted serial transcript showing the Sep25 22:17:03
observation SPL booting from SPINAND and returning to the tinySPL console.
This is user-reported physical evidence, not an agent-captured raw serial file.
The pasted backslash escapes were retained; line endings were serialized locally.
The local transcript is `artifacts/h0-observe-user-evidence/observation-pasted.log`
(2570 bytes, SHA-256
`6fe3eba0f6b9461d2a7ac5072850e198cdee39200ee840ead80d944496e328ad`).
The checker output is alongside it in `check.json`. These local artifacts are
not part of the original delivery and do not modify its manifest or hashes.

`scripts/check_observation_log.py` returned PASS: exactly 54 correctly ordered
events, zero dropped records, entry zero, and the required observe-only stop
marker. All register values match across stages 1 and 3. Both snapshots precede
OS reads; stage 3 here is the dump snapshot, not a payload handoff snapshot.

Observed values in both snapshots:

| Register group | Value |
| --- | --- |
| mstatus / mie | 0x80006088 / 0x00000000 |
| mtvec / mhcr | 0x40c00383 / 0x0000103f |
| SYSCFG at 0x18000160 | 0x00000002 |
| SYSMAP, 16 words from 0x2ffff000 | Identical across snapshots |
| Eight sampled DMA enable registers | All zero |

This supports the expected observation and stop behavior. It does not prove
transfer-time DMA quiescence, all bus-master inactivity, alias safety, or Zephyr
execution. In particular mie=0 is not a global-interrupt-disabled assertion:
mstatus bit 3 is set and CLIC behavior needs its own analysis.

The reset decoder reports 0x500, Watchdog-Reset / Command-Reboot. This capture
must not be labeled an external-pin Reset trial (the earlier product transcript
reported 0x100). It alone does not establish an unexpected watchdog crash or
which tool initiated the reboot.

The owner subsequently confirmed that flashing `RESTORE_original_product.img`
restored normal operation. Recovery is accepted as owner-reported physical
validation; no restoration serial transcript or AiBurn result file was supplied.
Do not describe this as independently inspected recovery telemetry or require
the owner to repeat the successful restoration solely for this record.

The bounded observation-and-restoration trial is now complete on the strength
of the checked observation transcript and the owner's recovery confirmation.
Current recovery status is `recovery_verified=true`, with evidence basis
`owner_report`. The immutable delivery manifest records the earlier pre-trial
state and is not rewritten. Overall `hardware_validation=pending` and the
Zephyr H1 gate `loadable_image=false` remain: the next work is offline design
and review of transfer-time destination/buffer lifetime and DMA-stop evidence,
plus unresolved memory alias and handoff requirements. This confirmation does
not authorize automatic flashing or establish Zephyr runtime acceptance.
