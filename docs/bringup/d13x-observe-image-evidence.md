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
