/* SPDX-License-Identifier: Apache-2.0
 * D13x CLIC trap context save/restore (mcause only).
 *
 * Algorithm modeled on upstream ESP32-C5 soc_irq.S (Apache-2.0, Espressif):
 * on CLIC the preemption level lives in mcause.mpil and MRET reloads
 * mintstatus.mil from mcause.mpil only when mcause.interrupt (bit 31) is
 * set. The saved mcause cannot be written back verbatim when returning to
 * a thread frame saved by a different trap type: an interrupt-entered trap
 * returning to an exception/ecall-saved frame forces interrupt=1 and
 * MPIL=0 so the final MRET restores MIL to 0; an exception-entered trap
 * keeps the interrupt bit cleared.
 *
 * E907 adaptations (single functional variable for the round-12 trial):
 * - No mintthresh member: the threshold is MMIO-only here and CSR 0x347
 *   traps Illegal instruction, so only mcause is saved/restored.
 * - The fixed value is deposited into the ARCH ESF mcause slot instead of
 *   the CSR: D13x selects CLIC_SUPPORT_INTERRUPT_LEVEL, whose generic
 *   restore runs after __soc_restore_context and would otherwise clobber
 *   a CSR write with the unfixed entry value. The generic restore then
 *   carries the fixed value to MRET.
 * - MPIL field is bits[23:16] (E907/CLIC board-trial rule, corroborated
 *   by the upstream 0xFF00FFFF mask); timer/IRQ dispatch stays on the
 *   generic path (__soc_handle_irq is deliberately not defined here).
 */

#include <zephyr/toolchain.h>
#include <zephyr/offsets.h>
#include <zephyr/arch/riscv/irq.h>

/* Exports */
GTEXT(__soc_save_context)
GTEXT(__soc_restore_context)

SECTION_FUNC(exception.other, __soc_save_context)
	csrr t0, mcause
	sw t0, __soc_esf_t_mcause_OFFSET(a0)
	ret

SECTION_FUNC(exception.other, __soc_restore_context)
	lw t0, __soc_esf_t_mcause_OFFSET(a0)
	/* live mcause = entry type of this trap */
	csrr t2, mcause
	bltz t2, 1f
	/* Exception-entered: keep mcause.interrupt clear; mil stays 0. */
	li t1, 0x7FFFFFFF
	and t0, t0, t1
	j 2f
1:	/* Interrupt-entered: set mcause.interrupt so mret reloads mil from
	 * mpil; exception-saved frames resume at mil 0.
	 */
	bltz t0, 2f
	li t1, 0xFF00FFFF
	and t0, t0, t1
	li t1, RISCV_MCAUSE_IRQ_BIT
	or t0, t0, t1
	/* Deposit into the arch ESF slot (soc_context is its last member,
	 * so the delta fits an addi); the generic CLIC restore below loads
	 * this fixed value to the CSR before MRET.
	 */
2:	addi t3, a0, (__struct_arch_esf_mcause_OFFSET - __struct_arch_esf_soc_context_OFFSET)
	sw t0, 0(t3)
	ret
