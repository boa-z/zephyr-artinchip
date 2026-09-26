/* SPDX-License-Identifier: Apache-2.0
 * D13x SOC offset symbols for the trap context above.
 */
#ifndef ZEPHYR_ARTINCHIP_D13X_SOC_OFFSETS_H_
#define ZEPHYR_ARTINCHIP_D13X_SOC_OFFSETS_H_

#ifdef CONFIG_RISCV_SOC_OFFSETS

#define GEN_SOC_OFFSET_SYMS() GEN_OFFSET_SYM(soc_esf_t, mcause)

#endif /* CONFIG_RISCV_SOC_OFFSETS */

#endif /* ZEPHYR_ARTINCHIP_D13X_SOC_OFFSETS_H_ */
