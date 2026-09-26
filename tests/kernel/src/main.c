/* SPDX-License-Identifier: Apache-2.0 */
#include <artinchip/module.h>
#include <zephyr/kernel.h>
#include <zephyr/sys/atomic.h>
#include <zephyr/ztest.h>
#if defined(CONFIG_SOC_SERIES_D13X)
#include <zephyr/arch/riscv/csr.h>
#endif

BUILD_ASSERT(IS_ENABLED(CONFIG_ARTINCHIP_MODULE));
K_SEM_DEFINE(signal, 0, 1);
K_THREAD_STACK_DEFINE(worker_stack, 1024);
K_THREAD_STACK_DEFINE(switch_stack, 1024);
static struct k_thread worker_thread;
static struct k_thread switch_thread;
static atomic_t observed;
static atomic_t worker_phase;
static atomic_t isr_probe_count;
static atomic_t switch_stop;

/* Expiry callbacks run in timer-ISR context: no thread scheduling is
 * involved, so this counter isolates ISR delivery from thread wake.
 */
static void isr_probe_expiry(struct k_timer *timer)
{
	ARG_UNUSED(timer);
	atomic_inc(&isr_probe_count);
}

K_TIMER_DEFINE(isr_probe_timer, isr_probe_expiry, NULL);

struct poll_snapshot {
	uint32_t cycles;
	int64_t ticks;
	uint32_t mstatus;
	uint32_t mcause;
};

/* Raw timer/pending sampling for the D13x board trial. Values are
 * reported, not interpreted here: in CLIC mode the meaning of
 * mip/mie bits is a hardware obligation, not a driver assumption.
 * Sampled before k_timer_stop(), which may reprogram the comparator.
 */
struct tick_regs {
	uint64_t mtime;
	uint64_t mtimecmp;
	unsigned long mip;
	unsigned long mie;
	unsigned long mcause;
	unsigned long mintthresh;
	int irq_enabled;
	uint8_t clic_ip;
	uint8_t clic_ie;
	uint32_t clic_mth;
};

/* CSR mintthresh number (0x347) as in drivers/interrupt_controller/intc_clic.h;
 * read raw: the toolchain knows only standard CSR names.
 */
static unsigned long read_mintthresh(void)
{
	unsigned long value = 0;

#if defined(CONFIG_SOC_SERIES_D13X)
	__asm__ volatile("csrr %0, 0x347" : "=r"(value));
#endif
	return value;
}

static struct tick_regs tick_regs_get(void)
{
	struct tick_regs regs = {0, 0, 0, 0, 0, 0, 0, 0, 0, 0};

#if defined(CONFIG_SOC_SERIES_D13X)
	volatile uint32_t *mtime =
		(uint32_t *)DT_REG_ADDR_BY_NAME(DT_INST(0, riscv_machine_timer), mtime);
	uint32_t timer_irq = DT_IRQN(DT_INST(0, riscv_machine_timer));
	volatile uint32_t *mtimecmp = (uint32_t *)(DT_REG_ADDR_BY_NAME(
		DT_INST(0, riscv_machine_timer), mtimecmp) + arch_proc_id() * 8);
	/* CLIC byte layout mirrors drivers/interrupt_controller/intc_clic.h
	 * (union CLICCTRL: IP, IE, ATTR, CTRL at 0x1000 + 4*irq) and the MTH
	 * word at offset 0x8: the same values the shipped driver uses.
	 */
	uintptr_t clic_ip = DT_REG_ADDR(DT_INST(0, riscv_clic)) + 0x1000U +
			    (uintptr_t)timer_irq * 4U;
	uint32_t hi, lo;

	do {
		hi = mtime[1];
		lo = mtime[0];
	} while (mtime[1] != hi);
	regs.mtime = ((uint64_t)hi << 32) | lo;
	do {
		hi = mtimecmp[1];
		lo = mtimecmp[0];
	} while (mtimecmp[1] != hi);
	regs.mtimecmp = ((uint64_t)hi << 32) | lo;
	regs.mip = csr_read(mip);
	regs.mie = csr_read(mie);
	regs.mcause = csr_read(mcause);
	regs.mintthresh = read_mintthresh();
	regs.irq_enabled = irq_is_enabled(timer_irq);
	regs.clic_ip = sys_read8(clic_ip);
	regs.clic_ie = sys_read8(clic_ip + 1U);
	regs.clic_mth = sys_read32(DT_REG_ADDR(DT_INST(0, riscv_clic)) + 0x8U);
#endif
	return regs;
}

static struct poll_snapshot poll_snapshot_get(void)
{
	struct poll_snapshot result = {0};

#if defined(CONFIG_SOC_SERIES_D13X)
	result.mstatus = csr_read(mstatus);
	result.mcause = csr_read(mcause);
#endif
	result.cycles = k_cycle_get_32();
	result.ticks = k_uptime_ticks();
	return result;
}

/* A tick-dependent deadline cannot diagnose a stopped tick. Cycle reads do
 * not require timer IRQ delivery; the iteration budget also covers a static
 * cycle counter, but cannot protect against a stalled MMIO transaction.
 */
static bool wait_for_worker(void)
{
	struct poll_snapshot before = poll_snapshot_get();
	uint32_t start = before.cycles;
	const char *reason = "iterations";
	uint32_t budget = k_ms_to_cyc_ceil32(1000);

	for (uint32_t spins = 0; spins < 10000000U; spins++) {
		if (atomic_get(&observed)) {
			reason = "worker";
			break;
		}
		if ((uint32_t)(k_cycle_get_32() - start) >= budget) {
			reason = "cycles";
			break;
		}
		compiler_barrier();
	}
	/* Capture before printing or aborting: UART and cleanup can change timing. */
	struct poll_snapshot after = poll_snapshot_get();
	bool woke = atomic_get(&observed) != 0;
	int phase = atomic_get(&worker_phase);

	printk("KERNEL-POLL schema=1 reason=%s woke=%u phase=%d priority=%d "
	       "tick_delta=%lld cycle_delta=%u\n", reason, (unsigned int)woke, phase,
	       k_thread_priority_get(k_current_get()),
	       (long long)(after.ticks - before.ticks), after.cycles - before.cycles);
#if defined(CONFIG_SOC_SERIES_D13X)
	printk("KERNEL-CSR before_mstatus=%08x after_mstatus=%08x "
	       "before_mcause=%08x after_mcause=%08x\n",
	       before.mstatus, after.mstatus, before.mcause, after.mcause);
#endif
	return woke;
}

static void delayed_worker(void *a, void *b, void *c)
{
	ARG_UNUSED(a);
	ARG_UNUSED(b);
	ARG_UNUSED(c);
	atomic_set(&worker_phase, 1);
	k_sleep(K_MSEC(20));
	atomic_set(&worker_phase, 2);
	atomic_set(&observed, 1);
	k_sem_give(&signal);
}

static void *kernel_preflight(void)
{
	int priority = k_thread_priority_get(k_current_get());
	int64_t uptime = k_uptime_get();
	uint32_t cycles = k_cycle_get_32();

	printk("KERNEL-PREFLIGHT begin irq_slots=%u\n", CONFIG_NUM_IRQS);
	k_sem_reset(&signal);
	atomic_clear(&observed);
	atomic_clear(&worker_phase);
	k_thread_create(&worker_thread, worker_stack, K_THREAD_STACK_SIZEOF(worker_stack),
			delayed_worker, NULL, NULL, NULL, priority - 1, 0, K_NO_WAIT);
	bool woke = wait_for_worker();
	if (!woke) {
		k_thread_abort(&worker_thread);
	}
	zassert_true(woke, "tick wake/preemption failed within bounded polling budget");
	zassert_ok(k_thread_join(&worker_thread, K_NO_WAIT));
	printk("KERNEL-PREFLIGHT PASS uptime_delta_ms=%lld cycle_delta=%u\n",
	       (long long)(k_uptime_get() - uptime),
	       (uint32_t)(k_cycle_get_32() - cycles));
	k_sem_reset(&signal);
	return NULL;
}

ZTEST(artinchip_kernel, test_module)
{
	zassert_str_equal(artinchip_module_identity(), "zephyr-artinchip");
}

ZTEST(artinchip_kernel, test_thread_semaphore)
{
	k_sem_reset(&signal);
	atomic_clear(&observed);
	atomic_clear(&worker_phase);
	k_thread_create(&worker_thread, worker_stack, K_THREAD_STACK_SIZEOF(worker_stack),
			delayed_worker, NULL, NULL, NULL, 1, 0, K_NO_WAIT);
	zassert_ok(k_sem_take(&signal, K_SECONDS(1)));
	zassert_equal(atomic_get(&observed), 1);
	zassert_ok(k_thread_join(&worker_thread, K_SECONDS(1)));
}

ZTEST(artinchip_kernel, test_timeout)
{
	int64_t start = k_uptime_get();

	k_sem_reset(&signal);
	zassert_equal(k_sem_take(&signal, K_MSEC(25)), -EAGAIN);
	zassert_true(k_uptime_get() - start >= 25);
}

ZTEST(artinchip_kernel, test_timer_isr_delivery)
{
	/* While this thread spins without yielding, only a 5 ms periodic
	 * k_timer is armed. Its expiry runs in timer-ISR context, so a
	 * growing count proves timeout interrupts are delivered during the
	 * spin even if no thread wake/preemption is involved. A zero count
	 * at budget expiry points at ISR delivery/arming instead.
	 */
	struct poll_snapshot before = poll_snapshot_get();
	uint32_t start = before.cycles;
	uint32_t budget = k_ms_to_cyc_ceil32(1000);
	const char *reason = "iterations";

	atomic_clear(&isr_probe_count);
	k_timer_start(&isr_probe_timer, K_MSEC(5), K_MSEC(5));
	struct tick_regs armed = tick_regs_get();
	for (uint32_t spins = 0; spins < 10000000U; spins++) {
		if (atomic_get(&isr_probe_count) >= 20) {
			reason = "isr";
			break;
		}
		if ((uint32_t)(k_cycle_get_32() - start) >= budget) {
			reason = "cycles";
			break;
		}
		compiler_barrier();
	}
	/* Sample before stopping: k_timer_stop() may reprogram mtimecmp. */
	struct tick_regs at_exit = tick_regs_get();
	k_timer_stop(&isr_probe_timer);
	/* Capture before printing: UART can change timing. */
	struct poll_snapshot after = poll_snapshot_get();
	unsigned int count = (unsigned int)atomic_get(&isr_probe_count);

	printk("KERNEL-ISRPROBE schema=1 reason=%s count=%u priority=%d "
	       "tick_delta=%lld cycle_delta=%u\n", reason, count,
	       k_thread_priority_get(k_current_get()),
	       (long long)(after.ticks - before.ticks), after.cycles - before.cycles);
	printk("KERNEL-TICKDBG schema=1 armed_mtime=%llu armed_cmp=%llu "
	       "exit_mtime=%llu exit_cmp=%llu exit_mip=%08lx exit_mie=%08lx "
	       "exit_irqen=%d exit_clic_ip=%u exit_clic_ie=%u exit_clic_mth=%08x "
	       "exit_mcause=%08lx exit_mintthresh=%08lx\n",
	       (unsigned long long)armed.mtime, (unsigned long long)armed.mtimecmp,
	       (unsigned long long)at_exit.mtime, (unsigned long long)at_exit.mtimecmp,
	       at_exit.mip, at_exit.mie, at_exit.irq_enabled,
	       at_exit.clic_ip, at_exit.clic_ie, at_exit.clic_mth,
	       at_exit.mcause, at_exit.mintthresh);
	zassert_true(count >= 20, "no timer-ISR expiry observed while spinning");
}

ZTEST(artinchip_kernel, test_timer_spin_yield)
{
	/* Same 5 ms k_timer, but the spin calls k_yield() every 1000
	 * iterations: the thread never blocks, yet the kernel switch path
	 * runs. A passing count here while the plain spin fails implicates
	 * the switch path (re-arm/unmask); an identical failure leaves
	 * block/wfi as the remaining differentiator. Bounded like the rest.
	 */
	struct poll_snapshot before = poll_snapshot_get();
	uint32_t start = before.cycles;
	uint32_t budget = k_ms_to_cyc_ceil32(1000);
	const char *reason = "iterations";

	atomic_clear(&isr_probe_count);
	k_timer_start(&isr_probe_timer, K_MSEC(5), K_MSEC(5));
	for (uint32_t spins = 0; spins < 10000000U; spins++) {
		if (atomic_get(&isr_probe_count) >= 20) {
			reason = "isr";
			break;
		}
		if ((uint32_t)(k_cycle_get_32() - start) >= budget) {
			reason = "cycles";
			break;
		}
		if ((spins % 1000U) == 0U) {
			k_yield();
		}
		compiler_barrier();
	}
	k_timer_stop(&isr_probe_timer);
	/* Capture before printing: UART can change timing. */
	struct poll_snapshot after = poll_snapshot_get();
	unsigned int count = (unsigned int)atomic_get(&isr_probe_count);

	printk("KERNEL-SPINPROBE schema=1 mode=yield reason=%s count=%u priority=%d "
	       "tick_delta=%lld cycle_delta=%u\n", reason, count,
	       k_thread_priority_get(k_current_get()),
	       (long long)(after.ticks - before.ticks), after.cycles - before.cycles);
	zassert_true(count >= 20, "no timer-ISR expiry observed while yielding");
}

/* Companion spinner at the same priority: forces real context switches
 * on k_yield (a lone thread never switches: do_swap skips identical threads).
 */
static void switch_spinner(void *a, void *b, void *c)
{
	ARG_UNUSED(a);
	ARG_UNUSED(b);
	ARG_UNUSED(c);
	while (!atomic_get(&switch_stop)) {
		compiler_barrier();
	}
}

ZTEST(artinchip_kernel, test_timer_spin_switch)
{
	/* Same 5 ms k_timer, but a same-priority peer forces genuine
	 * ecall context switches on every k_yield: neither thread ever
	 * blocks, yet the full switch path (timeslice reset, re-arm
	 * evaluation) runs. Count growing here while plain spins fail
	 * implicates the switch path; identical failure leaves block/wfi
	 * as the remaining differentiator. Bounded like the rest.
	 */
	int priority = k_thread_priority_get(k_current_get());
	struct poll_snapshot before = poll_snapshot_get();
	uint32_t start = before.cycles;
	uint32_t budget = k_ms_to_cyc_ceil32(1000);
	const char *reason = "iterations";

	atomic_clear(&isr_probe_count);
	atomic_clear(&switch_stop);
	k_thread_create(&switch_thread, switch_stack, K_THREAD_STACK_SIZEOF(switch_stack),
			switch_spinner, NULL, NULL, NULL, priority, 0, K_NO_WAIT);
	k_timer_start(&isr_probe_timer, K_MSEC(5), K_MSEC(5));
	for (uint32_t spins = 0; spins < 10000000U; spins++) {
		if (atomic_get(&isr_probe_count) >= 20) {
			reason = "isr";
			break;
		}
		if ((uint32_t)(k_cycle_get_32() - start) >= budget) {
			reason = "cycles";
			break;
		}
		if ((spins % 1000U) == 0U) {
			k_yield();
		}
		compiler_barrier();
	}
	k_timer_stop(&isr_probe_timer);
	atomic_set(&switch_stop, 1);
	/* Capture before printing: UART can change timing. */
	struct poll_snapshot after = poll_snapshot_get();
	unsigned int count = (unsigned int)atomic_get(&isr_probe_count);

	printk("KERNEL-SPINPROBE schema=1 mode=switch reason=%s count=%u priority=%d "
	       "tick_delta=%lld cycle_delta=%u\n", reason, count,
	       k_thread_priority_get(k_current_get()),
	       (long long)(after.ticks - before.ticks), after.cycles - before.cycles);
	zassert_ok(k_thread_join(&switch_thread, K_SECONDS(1)));
	zassert_true(count >= 20, "no timer-ISR expiry observed across switches");
}

ZTEST(artinchip_kernel, test_timer_preemption)
{
	int priority = k_thread_priority_get(k_current_get());

	k_sem_reset(&signal);
	atomic_clear(&observed);
	atomic_clear(&worker_phase);
	k_thread_create(&worker_thread, worker_stack, K_THREAD_STACK_SIZEOF(worker_stack),
			delayed_worker, NULL, NULL, NULL, priority - 1, 0, K_NO_WAIT);
	/* No yield/sleep here: the timer must wake and preempt this thread. */
	bool woke = wait_for_worker();
	if (!woke) {
		k_thread_abort(&worker_thread);
	}
	zassert_true(woke, "timer did not preempt within bounded polling budget");
	zassert_ok(k_thread_join(&worker_thread, K_SECONDS(1)));
	k_sem_reset(&signal);
}

ZTEST(artinchip_kernel, test_owned_memory)
{
	static volatile uint32_t memory[256] __aligned(32);

	for (size_t i = 0; i < ARRAY_SIZE(memory); ++i) {
		memory[i] = 0xa55a0000U ^ (uint32_t)i;
	}
	k_sleep(K_MSEC(10));
	for (size_t i = 0; i < ARRAY_SIZE(memory); ++i) {
		zassert_equal(memory[i], 0xa55a0000U ^ (uint32_t)i);
		memory[i] = ~memory[i];
	}
	for (size_t i = 0; i < ARRAY_SIZE(memory); ++i) {
		zassert_equal(memory[i], ~(0xa55a0000U ^ (uint32_t)i));
	}
}

ZTEST_SUITE(artinchip_kernel, NULL, kernel_preflight, NULL, NULL, NULL);
