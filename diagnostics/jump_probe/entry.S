/* SPDX-License-Identifier: Apache-2.0
 * Standalone diagnostic, no C runtime, stack, gp, timer or Zephyr entry.
 * Register references: docs/provenance.yml / tinyspl_diagnostic_references.
 */
.option norvc
.option norelax
.section .text.entry,"ax",@progbits
.global _start
_start:
 la t0, snapshot
 sw sp, 0(t0)
 sw gp, 4(t0)
 sw ra, 8(t0)
 sw a0, 12(t0)
 sw a1, 16(t0)
 csrr t1, mstatus
 sw t1, 20(t0)
 csrr t1, mie
 sw t1, 24(t0)
 csrr t1, mtvec
 sw t1, 28(t0)
 csrr t1, 0x7c1 /* mhcr, already sampled by the loader diagnostics */
 sw t1, 32(t0)
 csrci mstatus, 8 /* after capturing entry state, keep output interrupt-free */
 fence rw, rw
 li t2, 0x18710000 /* inherited UART0, no divisor/pinmux/clock writes */
 lw t3, 0x0c(t2)
 andi t3, t3, 0x80
 bnez t3, uart_failed /* THR aliases divisor when DLAB is set */
 la a0, begin_marker
 jal puts
 la s0, snapshot
 li s6, 9
next_word:
 la a0, word_marker
 jal puts
 lw s1, 0(s0)
 li s2, 28
next_nibble:
 srl a0, s1, s2
 andi a0, a0, 15
 li t0, 10
 bltu a0, t0, decimal
 addi a0, a0, 87
 j emit
decimal:
 addi a0, a0, 48
emit:
 jal putc
 addi s2, s2, -4
 bgez s2, next_nibble
 la a0, newline
 jal puts
 addi s0, s0, 4
 addi s6, s6, -1
 bnez s6, next_word
 la a0, end_marker
 jal puts
 la t0, uart_status
 li t1, 1 /* submitted to UART, physical receipt requires external capture */
 sw t1, 0(t0)
 j stopped
puts:
 mv s3, a0
 mv s4, ra
puts_next:
 lbu a0, 0(s3)
 beqz a0, puts_done
 jal putc
 addi s3, s3, 1
 j puts_next
puts_done:
 jr s4
putc:
 li t4, 65536 /* bounded poll; cannot bound an MMIO bus stall */
poll:
 lw t3, 0x14(t2)
 andi t3, t3, 0x20
 bnez t3, send
 addi t4, t4, -1
 bnez t4, poll
 j uart_failed
send:
 sw a0, 0(t2)
 fence iorw, iorw
 ret
uart_failed:
 la t0, uart_status
 li t1, 2
 sw t1, 0(t0)
stopped:
 fence rw, rw
 j stopped /* deliberate stop, no return to the loader; recover with Reset/Boot */
.section .rodata,"a",@progbits
begin_marker: .asciz "H0-JUMP schema=1 fields=9\r\n"
word_marker: .asciz "H0-J "
newline: .asciz "\r\n"
end_marker: .asciz "H0-JUMP STOP hardware=pending\r\n"
.section .data,"aw",@progbits
.balign 16
snapshot: .zero 36
uart_status: .word 0
