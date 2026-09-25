# Prerequisite series

Base: official Zephyr `839728050444f90d06870b5fc9bbbda106d91459`.
First patch: legacy CLICCFG layout and MMIO threshold, 3 files, 10 additions/2 deletions.
Staging branch: `prereq/d13x-clic` in the isolated `zephyr-d13x-staging` tree.
The user's original `zephyr` fork remains unchanged. See series.json for commit,
patch checksum and resulting Git blob identities.

Why no SoC hook: generic clic_init unconditionally writes CSR mintthresh for
non-Nuclei hardware and uses newer CLICCFG bit positions. A reset hook cannot
correct those later writes. Misidentifying E907 as Nuclei would hide the mismatch.
The opt-in layout flag reuses the existing legacy MMIO initialization; no trap or
context switch replacement is introduced. Fixed SDK core_rv32.h documents
CLICCFG level bits 1..4 and MMIO threshold at offset 8, bits 24..31.

Apply: `python scripts/apply_patches.py`. It checks the exact base and a clean
initial tree, runs git apply --check and then applies; subsequent calls verify
only the recorded modifications exist. `--check` is read-only and rejects
unrecorded edits or patch hash drift. Run this again after every west update.
The dependency HEAD remains the official base **with recorded working-tree
patches**. A frozen west manifest alone is insufficient to reproduce this build;
ship the series and run the verifier. No dependency is silently switched to a fork.

Impact: D13x opts into the new register layout. QEMU uses no CLIC and is a generic
regression gate only. D13x builds are checked; real register/IRQ semantics remain
HARDWARE_PENDING. Human sign-off and upstream review remain pending.

Removal condition: an upstream equivalent supports the actual E907 register
layout. Update the base, remove the patch and replay/regress both targets in one
change. Future upstream staging must include a consumer and hardware evidence.

## Width-validation prerequisite

The second patch rejects INTCTLBITS greater than the eight-bit control register
and a level width greater than the effective control width. Zero control/level
bits remain valid. It follows the layout patch on the same base and changes only
clic_init; no trap, scheduler or interrupt return code changes. Invalid widths
previously reached negative priority shift counts. The fake-MMIO suite reproduced
initialization accepting values 9..15 before this guard. Legacy and Nuclei keep
the existing level clamp; the generic branch rejects an inconsistent configured
level. Valid generic/Nuclei layouts retain their register encoding.

The initial staging commit in series.json applies to patch 1 only. Patch 2 is a
replayable diff applied with git apply --check to the isolated dependency. Both
hashes and final blobs are verified. tests/clic compiles this actual driver under
legacy, generic and Nuclei configurations on QEMU with injected register I/O.
This tests register access/encoding, not real E907 CSR/trap/mret behavior. Remove
the guard patch when an equivalent checked initialization is in the pinned base.
