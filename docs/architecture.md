# Architecture

This repository is both the west manifest repository and an out-of-tree module.
The manifest pins official Zephyr. `zephyr-upstream` intentionally differs from
the owner's existing `zephyr` fork path, preventing west from checking out or
updating that fork. One explicit legacy CLIC register-layout prerequisite is replayed; see
`patches/zephyr/README.md` and its checksummed series.

`zephyr/module.yml` supplies board, DTS and SoC roots. The module CMake library
provides a real linked identity function; its Kconfig symbol is asserted by the
bringup sample and tests. No per-build ROOT environment variables are required.

The D133ECS candidate uses Zephyr reset, exception handling, scheduler, FPU
sharing, generic CLIC and machine timer. UART0 uses the word-access DesignWare
NS16550 path. There is no RT-Thread runtime, SDK HAL, DSP archive or kernel fork.
The small reset hook masks interrupts and disables E907 hardware context
stacking. It deliberately preserves cache and system-map state.

CLIC uses the legacy MMIO register layout, reads implemented priority width from
CLICINFO, and reserves zero bits for interrupt-level nesting. The generic driver
still owns enable/pending/priority/vector operations. The 96 slots and register
offsets come from fixed SDK headers. Nested-priority validation remains pending.

Nominal board capacity is 1 MiB SRAM and 16 MiB PSRAM. Only SRAM S0
`[0x30080000,0x30100000)` is linked. Neither the lower 256 KiB nor the upper
256 KiB of SRAM is used. PSRAM, TCM remapping and DMA are not initialized here.
Loader compatibility and this region's availability remain hardware obligations.
