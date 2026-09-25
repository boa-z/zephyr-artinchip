# NAND FIT route: remaining evidence boundary

The offline container uses the original NAND OS boot path. It does not depend
on the loader RAM shell command. H0 remains BLOCKED, loadable_image=false,
hardware_validation=pending and recovery_verified=false.

## Route-specific audit

Use `scripts/audit_loader_memory.py --route nand-fit` with the existing SDK,
loader-audit, objdump and fresh output arguments. Default `--route all` retains
the RAM-only questions for broader investigation. NAND FIT mode removes only
the host RAM staging/executor requirement; it retains NAND buffers, heap users,
DMA, inherited mappings and recovery requirements. Unknown route names fail.

The audit now includes disassembly of startup through __exit, save_boot_params,
hal_dma_init, hal_dma_chan_stop and hal_qspi_master_transfer_sync, bound to the
matching ELF hash. Reset_Handler's own symbol covers only its first jump, so
disassembling that symbol alone would miss the startup continuation.

## Findings from the matching linked loader

- Startup [0x40c00100, 0x40c00188) sets vectors/stacks, enables caches, clears
  BSS, relocates private parameters and calls SystemInit/main. Its separate
  save_boot_params routine saves registers and returns to the continuation.
  The working source's optional AIC_TCM_EN, AIC_SRAM1_EN and PSRAM_UNCACHED_EN
  startup sequences are absent from this inspected startup span. This does not
  prove TCM is disabled: PBP or other called routines can establish state.
- SystemInit [0x40c21dd8, 0x40c21ef4) configures CPU/cache/CLIC and clocks.
  It is not a complete readback of the physical memory map at payload entry.
- hal_dma_init at 0x40c1e52c sets software channel bases to 0x10000100 plus
  0x40 per channel, builds its software task free list and writes zero to DMA
  base offsets 0 and 4. The referenced DMA source identifies these writes as
  IRQ-enable registers. They must not be treated as channel-disable writes.
  This function is not evidence that every inherited DMA channel was stopped.
- boot_app at 0x40c12f22 performs cache maintenance, clears local MIE and jumps
  to the payload. Its inspected body does not globally stop DMA/display/USB.
  QSPI's per-transfer stop path is narrower than global bus-master quiescence.

These findings narrow the questions but cannot establish a safe handoff by
themselves. Source references and binary instruction evidence are distinct;
the source/config-to-loader build receipt is still missing.

## No-debugger observation proposal (not implemented)

The owner has COM11 at 115200 and no debugger interface. A diagnostic OS runs
only after the loader has written its payload. Therefore an OS entry probe
cannot observe the earlier allocation and transfer lifetime, and cannot prove
that those writes were safe.

If a future scope change permits diagnostic tinySPL instrumentation, first
create a disposable SDK worktree/copy preserving the user's reference tree.
Reproduce a baseline build and classify its differences against the matching
ELF before adding instrumentation. Retain PBP bytes, original product image,
partition map and recovery components; verify any packaging changes explicitly.
Do not assume building a different SPL preserves PBP automatically.

The minimum proposed instrumentation has three observation points:

1. Before writing an OS destination: report resolved load/entry/length, loader
   stack/heap bounds, and documented SRAM/TCM mapping fields.
2. Around NAND/FIT reads: record destination intervals, bounce-buffer and DMA
   descriptor ownership/lifetime, and transfer/stop return status. Use bounded
   records; avoid adding allocations or blocking logging inside DMA/IRQ code.
3. Before boot_app's final jump: print the accumulated records and documented
   active-channel state. CPU exception/FPU/cache state must be captured before
   diagnostic printing can alter it. Record instrumentation effects explicitly.

This proposal does not authorize arbitrary register probing, globally resetting
peripherals, changing PBP, or board writes. Every register requires a source or
manual definition. Unknown PBP aliases may still need vendor evidence even with
instrumentation. The first build would remain an offline candidate, not an
approved image. Recovery demonstration follows a reviewed and separately
authorized physical procedure.

The original H0 task explicitly prohibits modifying tinySPL. That scope must be
changed explicitly before this instrumentation is implemented. Until then,
retain the offline probe container and do not request a trial flash to discover
whether the memory assumptions happen to work.
