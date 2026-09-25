/* SPDX-License-Identifier: Apache-2.0 */
#ifndef AIC_H0_DIAG_H
#define AIC_H0_DIAG_H
#include <stdint.h>
void h0_begin(void);
void h0_event(uint32_t kind, uintptr_t address, uint32_t size, uint32_t result);
void h0_state(uint32_t stage);
int h0_dump(uintptr_t entry);
/* Record an existing stop operation's result; do not add a new stop. */
#define H0_DMA_STOP(channel) do { \
    int h0_result = hal_dma_chan_stop(channel); \
    h0_event(6, (uintptr_t)(channel), 0, (uint32_t)h0_result); \
} while (0)
#endif
