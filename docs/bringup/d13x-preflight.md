# D133ECS preflight

Status: software candidate / HARDWARE_PENDING, 2026-09-25.
Current installed-board observations and unknowns: d13x-handoff.yml.
Target: `d50t_2_lite/d133ecs`. Family/series/part identifiers describe ArtInChip
D13x / D133ECS; `boa` denotes a downstream community board, not an official vendor.

## Evidence and boundaries

| Item | Evidence | Disposition |
|---|---|---|
| E907FDP, RV32IMAFDC, ILP32D | Fixed SDK d13x/rtconfig.py; owner-confirmed part | GNU standard ISA subset; no vendor DSP/P extension |
| 1 MiB SRAM, 16 MiB PSRAM | Owner requirement; product board documentation | Preserve nominal sizes; PSRAM disabled |
| SRAM S0 origin 0x30040000 | Fixed aic_soc.h and gcc_aic_nopsram.ld.S | Link only 0x30080000..0x30100000; actual loader availability BLOCKED |
| TCM / SRAM S1 | Product configuration disables TCM and S1 | No remap writes; actual installed loader state BLOCKED |
| CLIC base 0xe0800000, 96 slots | Fixed aic_soc.h / core_rv32.h | Legacy MMIO control layout with recorded prerequisite patch |
| CLICCFG level bits 1..4, threshold +8 bits 24..31 | Fixed Alibaba CSI core_rv32.h | Not the newer generic CLIC layout; read implemented priority width from CLICINFO |
| Machine timer 0xe000bff8, compare 0xe0004000, IRQ 7 | Fixed core_rv32.h / aic_soc.h / time.c | In-tree machine timer performs coherent reads and compare rearming |
| Timer input 4 MHz | Fixed sys_freq.c non-QEMU path | Must measure real elapsed time on board |
| UART0 0x18710000, IRQ 76 | Fixed aic_soc.h / UART HAL | Word-spaced, 32-bit DesignWare APB NS16550 access |
| UART 48 MHz, 115200 8N1 | Product current configuration, clock source setup | Loader must supply this clock; fixed SDK helper's 24 MHz is not substituted |
| UART TX PA0 / RX PA1, function 5 | Product target pinmux.c | Software configuration evidence only; PCB wiring/voltage not confirmed |
| Power hold PE16 high | Product target board.c | Loader obligation; candidate has no GPIO driver initialization |
| Clock / oscillator / boot media | Product configuration references PLL and external NAND | No oscillator, storage or CMU driver copied; actual board/loader log required |
| Cache line 32 bytes | Fixed D13x Kconfig.chip and core header | Preserve inherited cache/map state; maintenance validation NOT_RUN |
| Current product/loader artifacts | Current rebuilt product has September 24 SPL, byte-identical to available ELF/bin; map exists | Historical September 21 mismatch is superseded; dynamic ownership still unresolved; see d13x-product-image-evidence.md |

Sources and exact original hashes are recorded in `../provenance.yml`.
The fixed SDK has no D50T board. Product-specific evidence is additional evidence,
not a replacement SoC baseline. Existing product dirty files were not changed.

## Interrupt contract

Zephyr owns mtvec/mtvt, software trap frames, FPU state and scheduler. The reset
hook disables E907 automatic stack push/swap before Zephyr trap setup. The generic
CLIC driver is patched only for the legacy register layout; level nesting bits
are zero for this candidate. Priority width is read from hardware. IRQ masking,
pending/enable and selective hardware vectoring use the actual CLIC registers.
No SDK ISR, tick stub, or alternative RTOS context switch is linked.
The raw reset path, CLIC CSR availability and interrupt return still need real
E907 validation; QEMU virt does not emulate this controller.

## Before connecting hardware

Obtain board revision/schematic or verified UART wiring, electrical levels,
installed bootloader version/hash/config, loader RAM map including active stack,
heap and DMA, accepted signed/container format and a recovery procedure. Capture
M-mode entry, mstatus, mxstatus/mexstatus, cache/map/TCM state, mtvec/mtvt,
CLICINFO and UART clock information. Do not probe unknown CSRs on a live product.
No flashing or load command is provided while these inputs are unresolved.
