/* SPDX-License-Identifier: Apache-2.0
 * Original stackless diagnostic entry. Register definitions referenced in
 * docs/provenance.yml. Only t0..t4 are scratch; no loader stack or gp use.
 */
#include <zephyr/devicetree.h>
.section .text.aic_handoff_entry,"ax",@progbits
.balign 4
.global aic_handoff_entry
.type aic_handoff_entry,@function
aic_handoff_entry:
 .option push
 .option norelax
 la t0, aic_handoff_snapshot
 .option pop
 sw sp, 4(t0)
 sw gp, 8(t0)
 sw a0, 12(t0)
 sw a1, 16(t0)
 csrr t1, mstatus
 sw t1, 20(t0)
 csrr t2, mie
 sw t2, 24(t0)
 csrr t2, mip
 sw t2, 28(t0)
 csrr t2, mtvec
 sw t2, 32(t0)
 csrr t2, 0x307 /* mtvt: SDK and Zephyr CLIC */
 sw t2, 36(t0)
 csrr t2, 0x7e1 /* mexstatus */
 sw t2, 40(t0)
 csrr t2, 0x7c0 /* mxstatus */
 sw t2, 44(t0)
 csrr t2, 0x7c1 /* mhcr: cache enables */
 sw t2, 48(t0)
 li t2, 0x6000
 and t1, t1, t2
 li t2, -1
 beqz t1, 1f
 csrr t2, fcsr /* no write; read only if entry mstatus.FS != Off */
1:
 sw t2, 52(t0)
 li t1, 0x20800004 /* SDK non-QEMU CLICINFO; matching loader SystemInit */
 lw t2, 0(t1)
 sw t2, 56(t0)
 li t1, 0x2000bff8 /* SDK non-QEMU CORET MTIME; matching loader time read */
2:
 lw t2, 4(t1)
 lw t3, 0(t1)
 sw t3, 60(t0)
 lw t3, 4(t1)
 bne t2, t3, 2b
 sw t2, 64(t0)
 /* SDK SYSMAPADDR/CFG0..7, read only. CPU_BASE + 0x0ffff000. */
 li t1, 0x2ffff000
 addi t2, t0, 68
 addi t3, t0, 132
3:
 lw t4, 0(t1)
 sw t4, 0(t2)
 addi t1, t1, 4
 addi t2, t2, 4
 bne t2, t3, 3b
 li t1, 0x48305031 /* H0P1, written last */
 sw t1, 0(t0)
 fence rw, rw
 /* Snapshot first, then best-effort output on inherited UART0. No clock,
  * divisor, pinmux, FIFO or IRQ configuration changes. LSR reads may clear
  * error flags; this output therefore intentionally follows the snapshot.
  * A bounded poll does not protect against a bus fault or stalled MMIO read.
  */
 .option push
 .option norelax
 la t0, aic_early_uart_status
 la t1, .Learly_marker
 .option pop
 li t2, DT_REG_ADDR(DT_NODELABEL(uart0))
 li t3, 1 /* attempted */
 sw t3, 0(t0)
 lw t3, 0x0c(t2) /* LCR */
 andi t3, t3, 0x80 /* DLAB: THR would alias the divisor latch */
 bnez t3, .Luart_dlab
.Luart_next:
 lbu t3, 0(t1)
 beqz t3, .Luart_done
 li t4, 65536 /* iteration budget per byte, not a time unit */
.Luart_poll:
 lw t3, 0x14(t2) /* LSR */
 andi t3, t3, 0x20 /* THR empty, SDK AIC_LSR_TRANS_EMPTY */
 bnez t3, .Luart_send
 addi t4, t4, -1
 bnez t4, .Luart_poll
 li t3, 4 /* timeout; continue boot without waiting forever */
 j .Luart_status
.Luart_send:
 lbu t3, 0(t1)
 sw t3, 0(t2)
 fence iorw, iorw
 addi t1, t1, 1
 j .Luart_next
.Luart_dlab:
 li t3, 3 /* skipped: divisor latch selected */
 j .Luart_status
.Luart_done:
 li t3, 2 /* bytes submitted, not proof of physical serial reception */
.Luart_status:
 sw t3, 0(t0)
 fence rw, rw
 tail __start
.size aic_handoff_entry, .-aic_handoff_entry
.section .rodata.aic_early_marker,"a",@progbits
.Learly_marker:
 .asciz "H0-PROBE stage=snapshot-before-zephyr\r\n"
