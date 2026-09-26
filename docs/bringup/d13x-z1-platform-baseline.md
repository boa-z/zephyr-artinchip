# D13x Z1 platform baseline and CLIC upstream candidates

**Status: Z1 in progress. No pull request, push to an upstream remote, issue or
release has been created for any candidate in this file.** Z0 closed as
`hardware validated within Z0 scope` at tag `d13x-z0-validated` (annotated tag
object `ee91db0`, commit `2fa4c80`); this document records what changed after
that tag and what each CLIC candidate still needs before a human can submit it.

Everything below is downstream work by a community maintainer, not ArtInChip or
Zephyr official support (`docs/upstream-policy.md`). No commit here carries a
`Signed-off-by`; human DCO review is pending and `Assisted-by: Qoder` is used for
AI-assisted commits.

## 1. Baseline after the A1 / A3 / A2' steps

| Step | Commit | What changed | Behaviour delta | Board re-validation owed |
| --- | --- | --- | --- | --- |
| A1 | `3f8ba06` | SoC DTSI declares 1 MiB SRAM at `0x30040000` and 16 MiB PSRAM at `0x40000000` from the read-only SDK; the experimental window is named as PSRAM; boot-contract doc corrected | None: no `chosen` change, no address or size change, link targets identical | None for the map itself (comments plus two inert nodes) |
| A3 | `1d6dea0` | `CONFIG_ARTINCHIP_D13X_BOOT_CONTRACT` no longer gates compilation (`CMakeLists.txt` warns); it gates `scripts/package_candidate.py` collection | Build-only: a board build without the flag now configures instead of failing | One kernel-suite boot is enough to confirm nothing in the handoff moved |
| A2' | `8469dee` | `CONFIG_ARTINCHIP_D13X_DIAGNOSTIC_144_IRQS` deleted; `NUM_IRQS` defaults to 144 in `soc/artinchip/d13x/Kconfig.defconfig`; `tests/kernel` compares CLICINFO against `CONFIG_NUM_IRQS` | None intended: the same 144-slot tables, and the same compared constant | One kernel-suite boot (9/9), because the interrupt-table configuration path changed |

Deliberately **not** done in A2, both rejected on evidence grounds:

- No private `riscv,clic` binding adding a `num-irqs` property. The count would
  still come from one register read on one board, and it would need an app-tree
  binding shadowing the pinned upstream one.
- No `$(dt_highest_controller_irq_number,...)` derivation, which would have given
  `NUM_IRQS=77` (the DT only describes IRQ 7 and 76). That is not a cosmetic
  change: `intc_clic.c` initialises slots `0..CONFIG_NUM_IRQS-1`, so slots 77..143
  would keep whatever the bootloader left in `clicintattr`/`clicintie`. IRQ-path
  behaviour is exactly where Z0 lost eleven rounds, so this stays closed until a
  board run proves otherwise.

Offline verification for the three steps: `scripts/lint.py` and
`scripts/check_provenance.py` PASS, 146 host tests OK, and the required CI
workflow (D13x target builds plus the QEMU suites, `--build-only`) is green on
head `8469dee` as run [19](https://github.com/boa-z/zephyr-artinchip/actions/runs/36240870504).
CI carries no board evidence: the re-validation entries in the table above are
still open.

### Reproducibility consequence

The Z0 pins in `scripts/package_gate_trial.py` (`PINNED`) are hashes of builds
made from `2fa4c80`. A1 touches the DTS and A2' the test source line numbering, so
a rebuild at this head is **not** expected to reproduce those ELF hashes. The pins
are historical evidence for the tagged baseline; re-pinning a Z1 build requires
`--allow-unpinned` once plus a fresh board log, and the Z0 tag stays the address
for the validated images.

## 2. Platform fundamentals: closed and open

Closed by Z1 so far: the memory map is stated from a cited source instead of from
practice; the boot-contract acknowledgement sits where it can actually be
enforced; the interrupt-table width has one home.

Still open, each with the reason it matters:

- `boards/boa/d50t_2_lite/` has no `board.cmake`, no board-level
  `Kconfig.defconfig`, no `revisions.yml` and no `docs/board/*.rst`. Without
  `board.cmake` there is no runner configuration, so this board can only be built
  (`--build-only`) and never booted by Twister; that is also why every hardware
  result in this repository comes from a manual flash by the board owner.
- No clock, pinctrl, reset or GPIO provider nodes. `uart0` carries
  `clock-frequency = <48000000>` asserted in a comment as bootloader-supplied, and
  the timer's 4 MHz is a `timebase-frequency` property. Neither is derived from a
  clock provider, so no peripheral beyond the console can be described honestly.
- `tests/clic/src/main.c` compiles the driver by `#include "intc_clic.c"`. That is
  the right shape for a host-side register test and the wrong shape for upstream;
  it needs to become either a unit test with a fake MMIO region provided through
  the driver's own API or a documented test-only shim before submission.
- `soc/artinchip/d13x/reset.S` clears E907 `mexstatus` bits 16/17 (SPUSHEN,
  SPSWAPEN) through raw CSR `0x7e1`. Correct on this core, not a generic RISC-V
  construct; it stays downstream and it is not candidate material.
- `CLIC_PARAMETER_MNLBITS=0` (no nesting bits reserved) is a bring-up choice, not
  a claim about the hardware, and is excluded from the candidates for the same
  reason.
- Board YAML `ram: 512` describes the Zephyr-usable window, not the SoC SRAM; it
  stays that way until the loader's reservation is established rather than assumed.

## 3. Three CLIC upstream candidates

Per `docs/upstream-policy.md:17-20` the order is generic architecture
prerequisite, then minimal SoC/driver/board consumer, then independently testable
peripheral. Three candidates are not necessarily three pull requests; the grouping
decision is recorded at the end of this section.

### Candidate 1 - legacy CLIC register layout and MMIO threshold

- Patch: `patches/zephyr/0001-clic-legacy-mmio-layout.patch`, SHA-256
  `d493c9797d801138ef5017f7bbfe418073bcd902e7cb08698dafe78fb9454339`, 3 files,
  +10/-2 on base `839728050444f90d06870b5fc9bbbda106d91459`.
- Staging state: commit `1a42179e57c7dc50c481210edcfe3a100c686835` on branch
  `prereq/d13x-clic` in the isolated `zephyr-d13x-staging` tree. The user's own
  `zephyr` fork is untouched.
- Purpose: the E907 implements the pre-standard CLICCFG encoding (level bits 1..4)
  and keeps the threshold in MMIO at offset 8, bits 24..31. The pinned generic
  `clic_init` uses the newer CLICCFG positions and unconditionally writes CSR
  `mintthresh`. A SoC reset hook cannot repair that because it runs before the
  driver's own writes, and pretending the core is Nuclei would hide the encoding
  mismatch instead of describing it. The patch adds an opt-in layout symbol and
  reuses the existing legacy MMIO path.
- Evidence for: QEMU `tests/clic` compiles the patched driver under legacy,
  generic and Nuclei configurations with injected register I/O, so the encoding
  and the non-regression of the other two layouts are checked. Every D13x board
  result in Z0 was produced with this patch applied, so the patched driver is
  end-to-end consistent with real hardware - but that evidence covers the patched
  tree, not the patch in isolation, and a reviewer must be told so.
- What the evidence does not show: real E907 CSR/trap/`mret` timing, and anything
  about cores that implement neither layout.
- Removal condition: upstream supports the actual E907 register layout. Then
  update the pinned base, drop the patch, and replay both targets in one change.

### Candidate 2 - reject impossible control and level widths

- Patch: `patches/zephyr/0002-clic-validate-control-width.patch`, SHA-256
  `39a8e07cd95372c6ad3089ac1fc134079b7301e0b355058825bfc734837aa15f`.
- Staging state: commit `ce422750430903b3bb274741287c1af55d84229e` on
  `prereq/d13x-clic`, directly on top of candidate 1's `1a42179e57c…` and on the
  same base, so the two can be reviewed and replayed as one series. It was made by
  `git apply --check` followed by `git apply` of the recorded patch, and the three
  resulting Git blob identities were re-hashed against `series.json` before
  committing - the staged series and the applied working-tree series are therefore
  the same content, not two independently maintained copies. Local only: nothing
  has been pushed from the staging tree.
- Purpose: `INTCTLBITS` is the width of an eight-bit control register, and the
  level width cannot exceed the effective control width. Before the guard, values
  9..15 were accepted by initialisation - the fake-MMIO suite reproduced that -
  and an over-wide level produced negative priority shift counts. Zero control and
  level bits stay valid, which matters for implementations that expose no
  programmable priority at all.
- Scope discipline: only `clic_init` changes. Legacy and Nuclei keep their existing
  level clamp; the generic branch rejects the inconsistent configuration. No trap,
  scheduler or interrupt-return path is touched.
- Evidence for: the negative case is demonstrated, not argued - the suite accepts
  9..15 without the patch and rejects it with the patch, with valid layouts
  unchanged in all three configurations.
- Dependency: follows candidate 1 on the same base. Upstream could take it
  independently of the E907 layout question, which is the main argument for keeping
  it as its own commit rather than folding it in.

### Candidate 3 - mcause-only CLIC context with MPIL at bits 23:16

- Origin: commit `c0b15e9` (`Add D13x mcause-only CLIC context save/restore; fix
  MPIL to bits 23:16`), downstream files `soc/artinchip/d13x/soc_irq.S`,
  `soc_context.h`, `soc_offsets.h`, plus `Kconfig` selecting
  `RISCV_SOC_CONTEXT_SAVE`. Validated on the board in round 12.
- Purpose: with CLIC, the pending interrupt's priority level has to be read back out
  of `mcause` on the way out of the handler. This core reports it in `mcause`
  bits 23:16, so the save path keeps `mcause` as the whole saved context
  (`SOC_ESF_MEMBERS unsigned long mcause`) and masks `0xFF00FFFF` on the way back.
  The E907 hardware stack push must be off for that to be the kernel's job, which is
  what the reset hook clears.
- Evidence for: the discriminating pair is round 11 against round 12. Round 11 read
  `MINTSTATUS` top byte `ff` at every failure point and `00` in preflight
  (`docs/bringup/d13x-kernel-trial.md:529-532`),
  i.e. the accessor is sensitive to what this hardware reports; after the fix the
  same read is `00` in thread context across 2,333,061 samples in the Z0 gate runs
  with zero violations, kernel 9/9, the FPU context matrix, and a 601.789 s
  continuous stress window. That is a hardware-observed before/after on the exact
  register involved.
- What the evidence does not show: that 144 slots, `MNLBITS=0` or the E907
  `mexstatus` clearing are generic. Only one core, one board and one clock
  configuration are covered, and the failure-mode analysis for rounds 1-11 is
  specific to this CLIC revision's `mcause` layout.
- Upstream form, unresolved and to be settled before submission: either (a) an
  `arch/riscv` statement that a CLIC mode 3 handler must preserve and restore
  `mcause` with MPIL at bits 23:16, which needs a second implementation to
  corroborate; or (b) a documented `RISCV_SOC_CONTEXT_SAVE` consumer example, which
  upstreams nothing generic. Prefer (a) only if another CLIC owner confirms the
  bit positions; otherwise submit nothing and keep it downstream.
- Excluded from this candidate on purpose: `reset.S`'s raw CSR access,
  `CLIC_PARAMETER_MNLBITS=0`, and the 144-slot width. None is a generic claim.

### Grouping decision

Candidates 1 and 2 touch the same driver file and the same initialisation function
on the same base, and 2's rationale is easiest to review with 1's opt-in visible,
so they are prepared as one two-patch series on `prereq/d13x-clic`. Candidate 3 is
architecturally separate (architecture trap path, not driver configuration) and its
upstream form is still an open question, so it is prepared alone and submitted last,
or not at all. Nothing is opened while `human_signoff_pending: true` in
`docs/provenance.yml`.

## 4. Non-claims

This file states what is prepared, not what is accepted. It does not establish
CAN, display, GE/MPP, storage, DMA or cache coherency, GPIO, clock/reset/pinctrl,
PSRAM or XSPI drivers, DMA-capable SRAM placement, or upstream readiness of any
kind. The Z0 scope sentence in `README.md` remains the boundary of the hardware
claims. No board evidence in this repository was produced by CI, and no candidate
here has been flashed, pushed or published by an agent.
