/* SPDX-License-Identifier: Apache-2.0
 * Original register-lifetime probes: no FP-consuming C calls in the
 * preemption window. Preserve ABI callee-saved registers on return.
 */
#include <zephyr/toolchain.h>
#include <zephyr/linker/sections.h>
.text
.balign 4

.macro save_context
	addi sp, sp, -128
	sw ra, 112(sp)
	sw a0, 116(sp)
	sw a1, 120(sp)
	frcsr t0
	sw t0, 96(sp)
	fsd f8, 0(sp)
	fsd f9, 8(sp)
	fsd f18, 16(sp)
	fsd f19, 24(sp)
	fsd f20, 32(sp)
	fsd f21, 40(sp)
	fsd f22, 48(sp)
	fsd f23, 56(sp)
	fsd f24, 64(sp)
	fsd f25, 72(sp)
	fsd f26, 80(sp)
	fsd f27, 88(sp)
.endm

.macro load_pattern
	fld f0, 0(a0)
	fld f1, 8(a0)
	fld f2, 16(a0)
	fld f3, 24(a0)
	fld f4, 32(a0)
	fld f5, 40(a0)
	fld f6, 48(a0)
	fld f7, 56(a0)
	fld f8, 64(a0)
	fld f9, 72(a0)
	fld f10, 80(a0)
	fld f11, 88(a0)
	fld f12, 96(a0)
	fld f13, 104(a0)
	fld f14, 112(a0)
	fld f15, 120(a0)
	fld f16, 128(a0)
	fld f17, 136(a0)
	fld f18, 144(a0)
	fld f19, 152(a0)
	fld f20, 160(a0)
	fld f21, 168(a0)
	fld f22, 176(a0)
	fld f23, 184(a0)
	fld f24, 192(a0)
	fld f25, 200(a0)
	fld f26, 208(a0)
	fld f27, 216(a0)
	fld f28, 224(a0)
	fld f29, 232(a0)
	fld f30, 240(a0)
	fld f31, 248(a0)
	lw t0, 256(a0)
	fscsr t0
.endm

.macro store_pattern
	lw a1, 120(sp)
	fsd f0, 0(a1)
	fsd f1, 8(a1)
	fsd f2, 16(a1)
	fsd f3, 24(a1)
	fsd f4, 32(a1)
	fsd f5, 40(a1)
	fsd f6, 48(a1)
	fsd f7, 56(a1)
	fsd f8, 64(a1)
	fsd f9, 72(a1)
	fsd f10, 80(a1)
	fsd f11, 88(a1)
	fsd f12, 96(a1)
	fsd f13, 104(a1)
	fsd f14, 112(a1)
	fsd f15, 120(a1)
	fsd f16, 128(a1)
	fsd f17, 136(a1)
	fsd f18, 144(a1)
	fsd f19, 152(a1)
	fsd f20, 160(a1)
	fsd f21, 168(a1)
	fsd f22, 176(a1)
	fsd f23, 184(a1)
	fsd f24, 192(a1)
	fsd f25, 200(a1)
	fsd f26, 208(a1)
	fsd f27, 216(a1)
	fsd f28, 224(a1)
	fsd f29, 232(a1)
	fsd f30, 240(a1)
	fsd f31, 248(a1)
	frcsr t0
	sw t0, 256(a1)
	sw zero, 260(a1)
.endm

.macro restore_context
	fld f8, 0(sp)
	fld f9, 8(sp)
	fld f18, 16(sp)
	fld f19, 24(sp)
	fld f20, 32(sp)
	fld f21, 40(sp)
	fld f22, 48(sp)
	fld f23, 56(sp)
	fld f24, 64(sp)
	fld f25, 72(sp)
	fld f26, 80(sp)
	fld f27, 88(sp)
	lw t0, 96(sp)
	fscsr t0
	lw ra, 112(sp)
	addi sp, sp, 128
	ret
.endm

GTEXT(aic_fpu_preempt_probe)
SECTION_FUNC(TEXT, aic_fpu_preempt_probe)
	save_context
	load_pattern
	/* Snapshot only after loading every FP register. A changed peer epoch
	 * proves another thread ran while those register values were live. */
	lw t1, 0(a2)
1:
	lw t2, 0(a2)
	bne t1, t2, 2f
	addi a3, a3, -1
	bnez a3, 1b
	li a0, 1
	j 3f
2:
	li a0, 0
3:
	store_pattern
	restore_context

GTEXT(aic_fpu_yield_probe)
SECTION_FUNC(TEXT, aic_fpu_yield_probe)
	save_context
	load_pattern
	call aic_fpu_yield
	store_pattern
	restore_context
