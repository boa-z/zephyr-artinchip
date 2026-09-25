# D13x recovery plan: offline review only

Status: Z0.H0 BLOCKED; recovery_verified=false; loadable_image=false.
No device was enumerated, queried, reset, loaded or programmed for this review.
This document is not H1 manual test delivery and contains no executable burn command.

## Known-good reference and operator facts

Known-good product image:
`C:/Users/JCSH/Documents/Project/D50T-2-Lite/luban-lite-jc-d50t-rev/output/d13x_d50t-2-lite_rt-thread_D50T-2-Lite/images/d13x_D50T-2-Lite_page_2k_block_128k_v1.0.0.img`

SHA-256: `b0062dacbd68e8ef6f6de0c99c7cdc6620e602c5e00e913b454af6e93037aaf1`.
The owner reports successful USB whole-image Aiburn programming, a 115200 console,
main-power restart, and Reset + Boot entry to download mode. This is not flash
readback. Exact button press/release order and duration, Aiburn version, terminal
framing and failed-application recovery have not been supplied.

Aiburn is the owner-used recovery tool; installed version is unknown.
`C:/Users/JCSH/Documents/Tools/artinchip-flash/Cargo.toml` declares 0.1.0;
this is a source version, not an attested installed executable version.
Source hashes are in provenance.yml. The tool is an allowed future candidate.

## Priority 1: RAM-only download and execute

The vendor protocol has memory WRITE and EXEC handlers. The local CLI exposes
no RAM-only download/execute subcommand. Its GUI `official.rs` delegates
`ramboot <fwc-name> <ram-address> <image>` to an external upgcmd program;
that implementation and staging semantics have not been validated. Do not use
its default address as an approved address.

Crucially, matching Sep24 ELF `do_ram_boot` at 0x40c0d394 checks an AIC header,
copies the header-specified image length, and calls boot_app at the load address.
Its 100-byte implementation has no FIT loader call. Current source guards the
FIT branch with CONFIG_LPKG_USING_FDTLIB, whereas other FIT code uses
LPKG_USING_FDTLIB. The linked function, not the apparent source capability,
determines this finding. Existing RAM shell command therefore cannot be assumed
to launch the new FIT. No tinySPL modification is proposed.

Protocol EXEC calls a supplied function after dcache clean, but does not perform
the same IRQ masking/icache sequence as boot_app. Sending a Zephyr entry directly
through EXEC is not an equivalent handoff. RAM-only is a capability candidate,
not a closed loading route. RAM-only would intend zero NAND writes, but no
complete reviewed host/loader procedure currently establishes that result.

## Priority 2: OS-only programming

The GUI filters target components using selected_parts; the CLI Burn command has
no partition-selection option and defaults include spl/env/os. The host always
sends FULL_DISK_UPGRADE and image.info before selected targets, and may send
updater.psram and updater.spl beforehand. Therefore a GUI OS checkbox alone is
not proof that PBP, SPL, env/env_r, data and rodata are preserved.
The NAND receiver resolves metadata partition names and erases/writes blocks in
those MTD devices. Bad-block handling, image.info effects and updater behavior
still require end-to-end review and manual recovery evidence.

Desired write set: os only. Required untouched set: PBP, tinySPL, env, env_r,
data, rodata. Actual guaranteed write/untouched sets: UNKNOWN. Do not issue an
OS-only loading procedure until that discrepancy is resolved.

## Priority 3: whole-image study (not generated)

The verified container has updater.psram, updater.spl, image.info and target
spl/env/env_r/os/rodata/data components. Whole-image recovery can rewrite all
listed target partitions; it does not preserve user data just because the input
component bytes are unchanged. PBP is not a separate named component and may
be embedded in SPL containers; preserve entire updater and target SPL bytes.

If a separately authorized offline whole-image experiment becomes necessary:
start from a copy of the known-good image outside product output; change only
the OS payload; rebuild sizes/offsets and CRC metadata; retain all other component
payloads byte-identically; validate every boundary and CRC, extract every
component again, compare SHA-256 and bytes for every non-OS component, and bind
SPL to the matching ELF again. image.info/header metadata may need to change and
must be explicitly classified as metadata differences. Reject added/removed or
renamed partitions. This is a proposed verification algorithm, not an approved
image or proof of NAND side effects. No such container was generated.

## Human recovery rehearsal and failure handling

Before authorizing a diagnostic run, a human must retain the known-good image
and checksum, back up product-owned persistent data, record the exact Aiburn
version/configuration and write set, and demonstrate entry using the board's
Reset + Boot controls. The confirmed combination is known; timings must come
from the operator rather than an invented sequence.

If an authorized payload fails, the human operator re-enters download mode with
the confirmed board procedure, uses the verified Aiburn setup to restore the
known-good product, restarts using the recorded power procedure, and saves raw
serial logs showing the expected Sep24 loader and Sep25 application boot.
The selected write scope and consent to any persistent-data rewrite must be
settled before this recovery rehearsal. Success must be observed after an
unbootable application; earlier successful whole-image programming is insufficient.

Agent-prohibited actions for this phase: automatic USB/serial access, driver
installation, mode entry, RAM write/execute, Aiburn launch, NAND write/erase,
reset, PBP/SPL changes, product data changes, push/release/upstream publication.
Human authorization is a separate later step; none is inferred from this plan.

## H1 gate and test order

No H1 directory is generated while dynamic RAM, recovery or operation approval
is missing. After closure and explicit authorization, delivery must include
probe ITB/ELF/bin, immutable manifest and hashes, loading/recovery procedures and
expected output. Execute manually in order: handoff probe, bringup, kernel, FPU.
Probe must capture state and restore known-good product successfully. Bringup
requires at least 10 independent boots; kernel must demonstrate actual timer
preemption/context switching; FPU must run at least 10 minutes with all FP
register/fcsr and preemptive/voluntary switch checks. Save raw serial files for
each run. No QEMU or build-only result substitutes for these observations.
