/* SPDX-License-Identifier: Apache-2.0
 * Original bounded diagnostic recorder. Register facts: docs/provenance.yml.
 * Offline diagnostic SPL only; not a hardware safety or recovery assertion.
 */
#include <stdint.h>
#include <stdio.h>
#include <h0_diag.h>

struct event { uint32_t kind, address, size, result; };
static struct event events[256];
static unsigned int used, dropped, active;
static uint32_t irq_lock(void)
{
    uint32_t state;
    __asm__ volatile ("csrrci %0, mstatus, 8" : "=r"(state) :: "memory");
    return state;
}
static void irq_restore(uint32_t state)
{
    if (state & 8)
        __asm__ volatile ("csrsi mstatus, 8" ::: "memory");
}
void h0_event(uint32_t kind, uintptr_t address, uint32_t size, uint32_t result)
{
    uint32_t state = irq_lock();
    if (active) {
        if (used < sizeof(events) / sizeof(events[0]))
            events[used++] = (struct event){kind, address, size, result};
        else if (dropped != ~0U)
            dropped++;
    }
    irq_restore(state);
}
static uint32_t reg_read(uintptr_t address)
{
    return *(volatile uint32_t *)address;
}
void h0_state(uint32_t stage)
{
    uint32_t state = irq_lock(), mie, mtvec, cache;
    __asm__ volatile ("csrr %0, mie" : "=r"(mie));
    __asm__ volatile ("csrr %0, mtvec" : "=r"(mtvec));
    __asm__ volatile ("csrr %0, 0x7c1" : "=r"(cache));
    h0_event(10, stage, state, mie);
    h0_event(11, stage, mtvec, cache);
    /* Source-defined SYSCFG TCM/SRAM configuration and SYSMAP pairs.
     * Readback is raw: no claim that these exhaust all aliases or bus masters.
     */
    h0_event(12, 0x18000160, stage, reg_read(0x18000160));
    for (unsigned int i = 0; i < 16; i++)
        h0_event(13, 0x2ffff000 + i * 4, stage, reg_read(0x2ffff000 + i * 4));
    for (unsigned int i = 0; i < 8; i++)
        h0_event(14, 0x10000100 + i * 0x40, stage, reg_read(0x10000100 + i * 0x40));
    irq_restore(state);
}
void h0_begin(void)
{
    uint32_t state = irq_lock();
    used = dropped = 0;
    active = 1;
    irq_restore(state);
    h0_state(1);
    printf("H0-SPL begin schema=1 instrumentation=active acceptance=pending\n");
}
int h0_dump(uintptr_t entry)
{
    h0_state(3);
    uint32_t state = irq_lock();
    active = 0;
    irq_restore(state);
    printf("H0-SPL entry=%08lx count=%u dropped=%u\n", (unsigned long)entry, used, dropped);
    for (unsigned int i = 0; i < used; i++)
        printf("H0-E %u %u %08lx %08lx %08lx\n", i, (unsigned int)events[i].kind,
               (unsigned long)events[i].address, (unsigned long)events[i].size,
               (unsigned long)events[i].result);
    printf("H0-SPL end evidence=%s hardware=pending\n", dropped ? "INCOMPLETE" : "CAPTURED");
    return dropped ? -1 : 0;
}
