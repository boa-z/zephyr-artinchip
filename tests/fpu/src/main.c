/* SPDX-License-Identifier: Apache-2.0 */
#include <zephyr/kernel.h>
#include <zephyr/sys/atomic.h>
#include <zephyr/ztest.h>
#include <string.h>

BUILD_ASSERT(CONFIG_FPU && CONFIG_FPU_SHARING);
BUILD_ASSERT(CONFIG_RISCV_ISA_EXT_D);

extern int aic_fpu_preempt_probe(const uint64_t *in, uint64_t *out,
				volatile atomic_t *peer_epoch, uint32_t limit);
extern void aic_fpu_yield_probe(const uint64_t *in, uint64_t *out);

K_THREAD_STACK_ARRAY_DEFINE(stacks, 2, 2048);
static struct k_thread threads[2];
static atomic_t epochs[2];
static atomic_t counts[2];
static atomic_t failures;
static atomic_t stop;
K_SEM_DEFINE(phase_ready, 0, 2);
K_SEM_DEFINE(phase_go, 0, 2);
static uint64_t patterns[2][33] __aligned(8);
static uint64_t observed[2][33] __aligned(8);

/* Continuous thread-state MIL watch for the Z0 stability gate. Board-trial
 * rule: in thread context MINTSTATUS.MIL (top byte) must stay 0; a 0xFF latch
 * blocks all interrupts (the defect the round-12 mcause-only context fixup
 * clears). Sampled silently in both the stress threads (between preemption
 * probes) and the supervising poll loop, so the whole 120 s FPU stress is
 * covered without perturbing peer-epoch throughput. D13x only: off-target the
 * read is compiled out, counters stay zero and QEMU judgement is unchanged.
 */
static atomic_t mil_samples;
static atomic_t mil_violations;
static atomic_t mil_worst;

#if defined(CONFIG_SOC_SERIES_D13X)
static unsigned long fpu_read_mintstatus(void)
{
	unsigned long value = 0;

	__asm__ volatile("csrr %0, 0x346" : "=r"(value));
	return value;
}
#endif

static void fpu_mil_sample(void)
{
#if defined(CONFIG_SOC_SERIES_D13X)
	unsigned long mil = (fpu_read_mintstatus() >> 24) & 0xFFU;

	atomic_inc(&mil_samples);
	if (mil != 0UL) {
		atomic_inc(&mil_violations);
		atomic_set(&mil_worst, (atomic_val_t)mil);
	}
#endif
}

static void fpu_mil_report(int64_t uptime_ms)
{
	printk("FPU-MILHB schema=1 samples=%ld violations=%ld mil_worst=%02lx "
	       "uptime_ms=%lld counts=%ld+%ld\n",
	       (long)atomic_get(&mil_samples), (long)atomic_get(&mil_violations),
	       (unsigned long)atomic_get(&mil_worst), (long long)uptime_ms,
	       (long)atomic_get(&counts[0]), (long)atomic_get(&counts[1]));
}

void aic_fpu_yield(void)
{
	k_yield();
}

static void stress(void *arg, void *unused1, void *unused2)
{
	uintptr_t id = (uintptr_t)arg;

	ARG_UNUSED(unused1);
	ARG_UNUSED(unused2);
	for (uint32_t iteration = 0; iteration < 100; ++iteration) {
		aic_fpu_yield_probe(patterns[id], observed[id]);
		for (size_t reg = 0; reg < 32; ++reg) {
			if ((reg == 8 || reg == 9 || (reg >= 18 && reg <= 27)) &&
			    patterns[id][reg] != observed[id][reg]) {
				atomic_inc(&failures);
			}
		}
		if (observed[id][32] != patterns[id][32]) {
			atomic_inc(&failures);
		}
	}
	/* Both peers must finish voluntary checks before timed preemption. */
	k_sem_give(&phase_ready);
	k_sem_take(&phase_go, K_FOREVER);
	while (atomic_get(&stop) == 0) {
		atomic_inc(&epochs[id]);
		fpu_mil_sample();
		int result = aic_fpu_preempt_probe(patterns[id], observed[id],
						  &epochs[1 - id], CONFIG_AIC_FPU_PEER_SPIN_LIMIT);
		if (atomic_get(&stop) != 0) {
			break;
		}
		if (result != 0 || memcmp(patterns[id], observed[id], sizeof(patterns[id])) != 0) {
			printk("FPU failure: thread %u result %d peer %ld\n", (unsigned int)id, result, (long)atomic_get(&epochs[1-id]));
			for (size_t r = 0; r < 33; ++r) {
				if (patterns[id][r] != observed[id][r]) {
					printk("register %u expected %llx actual %llx\n", (unsigned int)r, patterns[id][r], observed[id][r]);
				}
			}
			atomic_inc(&failures);
			break;
		}
		atomic_inc(&counts[id]);
	}
}

ZTEST(artinchip_fpu, test_context_registers)
{
	int64_t deadline = k_uptime_get() + 120000;

	printk("FPU: peer spin limit %d iterations; target deadline 120 s\n",
	       CONFIG_AIC_FPU_PEER_SPIN_LIMIT);
	atomic_clear(&mil_samples);
	atomic_clear(&mil_violations);
	atomic_clear(&mil_worst);
	int64_t last_hb = k_uptime_get();

	for (size_t thread = 0; thread < 2; ++thread) {
		for (size_t reg = 0; reg < 32; ++reg) {
			/* Alternate NaN-boxed f32 and finite f64, unique per register/thread. */
			patterns[thread][reg] = (reg % 2 == 0 ?
				0xffffffff3f800000ULL : 0x3ff0000000000000ULL) |
				((uint64_t)(thread + 1) << 12) | reg;
		}
		patterns[thread][32] = thread + 1; /* distinct fflags; round-to-nearest */
		k_thread_create(&threads[thread], stacks[thread],
				K_THREAD_STACK_SIZEOF(stacks[thread]), stress,
				(void *)thread, NULL, NULL, 5, K_FP_REGS, K_FOREVER);
	}
	k_thread_start(&threads[0]);
	k_thread_start(&threads[1]);
	zassert_ok(k_sem_take(&phase_ready, K_SECONDS(10)));
	zassert_ok(k_sem_take(&phase_ready, K_SECONDS(10)));
	k_sem_give(&phase_go);
	k_sem_give(&phase_go);
	while ((atomic_get(&counts[0]) < 5000 || atomic_get(&counts[1]) < 5000) &&
	       atomic_get(&failures) == 0 && k_uptime_get() < deadline) {
		fpu_mil_sample();
		if (k_uptime_get() - last_hb >= 5000) {
			last_hb = k_uptime_get();
			fpu_mil_report(last_hb);
		}
		k_sleep(K_MSEC(10));
	}
	atomic_set(&stop, 1);
	for (size_t thread = 0; thread < 2; ++thread) {
		zassert_ok(k_thread_join(&threads[thread], K_SECONDS(10)));
	}
	printk("FPU: preemption checks %ld + %ld; voluntary checks 200\n",
	       (long)atomic_get(&counts[0]), (long)atomic_get(&counts[1]));
	fpu_mil_report(k_uptime_get());
	zassert_equal(atomic_get(&mil_violations), 0,
		      "thread-state MIL went non-zero during FPU stress");
	zassert_equal(atomic_get(&failures), 0);
	zassert_true(atomic_get(&counts[0]) >= 5000);
	zassert_true(atomic_get(&counts[1]) >= 5000);
}

ZTEST_SUITE(artinchip_fpu, NULL, NULL, NULL, NULL, NULL);
