/* SPDX-License-Identifier: Apache-2.0 */
#ifndef AIC_H0_DIAG_H
#define AIC_H0_DIAG_H
#include <stdint.h>
void h0_begin(void);
void h0_begin_transfer(void);
void h0_dma_stop(uintptr_t channel, uint32_t result);
void h0_event(uint32_t kind, uintptr_t address, uint32_t size, uint32_t result);
void h0_state(uint32_t stage);
int h0_dump(uintptr_t entry);
/* Fixed original-product FIT profile, independently checked against its image.
 * Numeric interval guard only; not an alias or bus-master ownership proof.
 */
static inline int h0_read_allowed(uintptr_t address, uint32_t size, uint32_t offset)
{
    if (offset == 0 && (size == 40 || size == 732))
        return address >= 0x40c80000U && address <= 0x41000000U - size;
    return address == 0x40000000U && size == 1397820U && offset == 0x800U;
}
/* Record an existing stop operation's result; do not add a new stop. */
#define H0_DMA_STOP(channel) do { \
    int h0_result = hal_dma_chan_stop(channel); \
    h0_dma_stop((uintptr_t)(channel), (uint32_t)h0_result); \
} while (0)
#endif
