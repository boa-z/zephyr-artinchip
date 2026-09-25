/* SPDX-License-Identifier: Apache-2.0
 * Original stackless diagnostic entry. Register definitions referenced in
 * docs/provenance.yml. Only t0..t3 are scratch; no loader stack or gp use.
 */
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
 li t1, 0xe0800004 /* SDK CLICINFO */
 lw t2, 0(t1)
 sw t2, 56(t0)
 li t1, 0xe000bff8 /* SDK CORET MTIME */
2:
 lw t2, 4(t1)
 lw t3, 0(t1)
 sw t3, 60(t0)
 lw t3, 4(t1)
 bne t2, t3, 2b
 sw t2, 64(t0)
 li t1, 0x48305031 /* H0P1, written last */
 sw t1, 0(t0)
 fence rw, rw
 tail __start
.size aic_handoff_entry, .-aic_handoff_entry
