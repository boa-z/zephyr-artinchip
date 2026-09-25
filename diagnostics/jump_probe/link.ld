/* SPDX-License-Identifier: Apache-2.0 */
OUTPUT_ARCH(riscv)
ENTRY(_start)
PHDRS { probe PT_LOAD FLAGS(7); }
SECTIONS {
  . = 0x40000000;
  .text : { KEEP(*(.text.entry)) *(.text*) } :probe
  .rodata : { *(.rodata*) } :probe
  .data : { *(.data*) } :probe
  .bss : { *(.bss*) *(COMMON) } :probe
  ASSERT(SIZEOF(.bss) == 0, "No uninitialized runtime storage allowed")
  ASSERT(. <= 0x4015543c, "Probe exceeds previously exercised product span")
  /DISCARD/ : { *(.comment) *(.eh_frame*) }
}
