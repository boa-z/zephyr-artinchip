/* SPDX-License-Identifier: Apache-2.0 */
#include <stdint.h>
#include <zephyr/kernel.h>
#include <zephyr/sys/printk.h>

/* The entry stores every field before Zephyr's BSS clearing; no stack use. */
uint32_t aic_handoff_snapshot[33] __attribute__((section(".noinit"), aligned(16)));
uint32_t aic_early_uart_status __attribute__((section(".noinit"), aligned(4)));
extern void aic_handoff_entry(void);

int main(void)
{
 static const char *const names[] = {
  "marker", "sp", "gp", "boot_device_a0", "boot_args_a1", "mstatus", "mie",
  "mip", "mtvec", "mtvt", "mexstatus", "mxstatus", "mhcr", "fcsr_or_skipped",
  "clicinfo", "mtime_low", "mtime_high"
 };
 printk("H0-PROBE sequence=1 source=%s entry=%p buffer=%p bytes=%u\n",
        PROBE_SOURCE, aic_handoff_entry, aic_handoff_snapshot,
        (unsigned int)sizeof(aic_handoff_snapshot));
 printk("ELF_SHA256=external:candidate.json privilege=expected-M-not-measured\n");
 printk("H0-PROBE stage=main early_uart_status=%u (1=attempted,2=submitted,3=DLAB,4=timeout)\n",
        aic_early_uart_status);
 if (aic_handoff_snapshot[0] != 0x48305031) {
  printk("H0-PROBE FAIL snapshot marker\n");
  return 1;
 }
 for (unsigned int i = 0; i < ARRAY_SIZE(names); i++) {
  printk("%s=0x%08x\n", names[i], aic_handoff_snapshot[i]);
 }
 for (unsigned int i = 0; i < 8; i++) {
  printk("sysmap%u_addr=0x%08x cfg=0x%08x\n", i,
         aic_handoff_snapshot[17 + 2 * i], aic_handoff_snapshot[18 + 2 * i]);
 }
 printk("TCM=not-captured; no-unverified-register-probes\n");
 printk("H0-PROBE CAPTURED hardware-acceptance=pending\n");
 return 0;
}
