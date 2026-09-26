/* SPDX-License-Identifier: Apache-2.0
 * D13x CLIC trap context: mcause only. Unlike the ESP32-C5/P4 model there
 * is no mintthresh member here: the E907 threshold is MMIO-only, and CSR
 * 0x347 traps Illegal instruction (round-6 board result).
 */
#ifndef ZEPHYR_ARTINCHIP_D13X_SOC_CONTEXT_H_
#define ZEPHYR_ARTINCHIP_D13X_SOC_CONTEXT_H_

#ifdef CONFIG_RISCV_SOC_CONTEXT_SAVE

#define SOC_ESF_MEMBERS unsigned long mcause

#define SOC_ESF_INIT 0

#endif /* CONFIG_RISCV_SOC_CONTEXT_SAVE */

#endif /* ZEPHYR_ARTINCHIP_D13X_SOC_CONTEXT_H_ */
