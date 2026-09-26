/* SPDX-License-Identifier: Apache-2.0 */
/* Z0 sustained-stress validator: one cold boot, no ztest, >=
 * CONFIG_AIC_Z0_STRESS_DURATION_SEC of machine-timer interrupts, comparator
 * re-arm, timed preemption, voluntary ECALL switch, blocking wakeup, full FPU
 * register/fcsr context and a thread-state MINTSTATUS.MIL watch.
 *
 * This is a verifier, not an experiment: it changes no timer frequency,
 * mtimecmp algorithm, CLIC configuration or context-restore behaviour, and it
 * never samples MIL outside thread context (an interrupt-context MIL is the
 * normal hardware value, not a failure).
 */

#include <zephyr/kernel.h>
#include <zephyr/sys/atomic.h>
#include <zephyr/sys/printk.h>
#include <string.h>

BUILD_ASSERT(IS_ENABLED(CONFIG_FPU) && IS_ENABLED(CONFIG_FPU_SHARING));
BUILD_ASSERT(IS_ENABLED(CONFIG_RISCV_ISA_EXT_D));
BUILD_ASSERT(CONFIG_AIC_Z0_STRESS_DURATION_SEC > 0);
BUILD_ASSERT(CONFIG_AIC_Z0_STRESS_HEARTBEAT_SEC > 0);
BUILD_ASSERT(IS_ENABLED(CONFIG_AIC_Z0_STRESS_INJECT_MIL) +
	     IS_ENABLED(CONFIG_AIC_Z0_STRESS_INJECT_FPU) +
	     IS_ENABLED(CONFIG_AIC_Z0_STRESS_INJECT_TIMER) +
	     IS_ENABLED(CONFIG_AIC_Z0_STRESS_INJECT_PEER) <= 1);

/* Exactly one negative-probe mode per build: the host probes diff the reported
 * reason against this name, and the packager rejects any enabled injection.
 */
#if defined(CONFIG_AIC_Z0_STRESS_INJECT_MIL)
#define AIC_INJECTION "mil"
#elif defined(CONFIG_AIC_Z0_STRESS_INJECT_FPU)
#define AIC_INJECTION "fpu"
#elif defined(CONFIG_AIC_Z0_STRESS_INJECT_TIMER)
#define AIC_INJECTION "timer"
#elif defined(CONFIG_AIC_Z0_STRESS_INJECT_PEER)
#define AIC_INJECTION "peer"
#else
#define AIC_INJECTION "none"
#endif

extern int aic_fpu_preempt_probe(const uint64_t *in, uint64_t *out,
				volatile atomic_t *peer_epoch, uint32_t limit);
extern void aic_fpu_yield_probe(const uint64_t *in, uint64_t *out);

#define PEERS 2
#define REGISTERS 33
#define HEARTBEAT_MS (CONFIG_AIC_Z0_STRESS_HEARTBEAT_SEC * 1000)
#define DURATION_MS ((int64_t)CONFIG_AIC_Z0_STRESS_DURATION_SEC * 1000)

/* probe.S performs the register traffic without an FP-consuming C call inside
 * the preemption window; aic_fpu_yield() is the voluntary-switch hook it calls.
 */
void aic_fpu_yield(void)
{
	k_yield();
}

K_THREAD_STACK_ARRAY_DEFINE(peer_stacks, PEERS, 2048);
K_THREAD_STACK_DEFINE(sleep_stack, 1024);
static struct k_thread peer_threads[PEERS];
static struct k_thread sleep_thread;

static uint64_t patterns[PEERS][REGISTERS] __aligned(8);
static uint64_t observed[PEERS][REGISTERS] __aligned(8);
static atomic_t epochs[PEERS];
static atomic_t fpu_checks[PEERS];
static atomic_t voluntary_checks;
static atomic_t fpu_failures;
static atomic_t timer_expiries;
static atomic_t timeout_wakeups;
static atomic_t stop;

static atomic_t mil_samples;
static atomic_t mil_violations;
static atomic_t mil_worst;

static const char *volatile failure_reason;

#if defined(CONFIG_SOC_SERIES_D13X)
/* MINTSTATUS CSR 0x346, MIL = bits[31:24] (board-trial layout used by the
 * frozen round-12 fix; number corroborated by the SDK accessor name).
 */
static unsigned long mil_now(void)
{
	unsigned long value = 0;

	__asm__ volatile("csrr %0, 0x346" : "=r"(value));
	return (value >> 24) & 0xFFU;
}
#endif

static void mil_sample(void)
{
#if defined(CONFIG_SOC_SERIES_D13X)
	unsigned long mil = mil_now();

	atomic_inc(&mil_samples);
	if (mil != 0UL) {
		atomic_inc(&mil_violations);
		if (mil > atomic_get(&mil_worst)) {
			atomic_set(&mil_worst, (atomic_val_t)mil);
		}
	}
#endif
}

/* Independent progress clock: raw mtime, so a stalled uptime cannot mask a
 * stalled timer. D13x only, like the kernel gate's accessor; on QEMU the field
 * reads 0 and that platform is never hardware evidence. Converted with the
 * configured frequency, not measured.
 */
#if defined(CONFIG_SOC_SERIES_D13X)
static uint64_t raw_mtime(void)
{
	volatile uint32_t *mtime = (uint32_t *)DT_REG_ADDR_BY_NAME(
		DT_INST(0, riscv_machine_timer), mtime);
	uint32_t hi, lo;

	do {
		hi = mtime[1];
		lo = mtime[0];
	} while (mtime[1] != hi);
	return ((uint64_t)hi << 32) | lo;
}
#define AIC_RAW_MTIME 1
#else
static uint64_t raw_mtime(void)
{
	return 0ULL;
}
#define AIC_RAW_MTIME 0
#endif

static void timer_expiry(struct k_timer *timer)
{
	ARG_UNUSED(timer);
	/* ISR/sys-clock context: counter only, never printk and never MIL. */
	atomic_inc(&timer_expiries);
}

K_TIMER_DEFINE(stress_timer, timer_expiry, NULL);

static void peer_failure(const char *reason, uintptr_t id, int probe)
{
	if (atomic_get(&stop) != 0) {
		return;
	}
	failure_reason = reason;
	atomic_inc(&fpu_failures);
	printk("Z0-STRESS-FAULT peer=%u probe=%d counts=%ld+%ld\n", (unsigned int)id,
	       probe, (long)atomic_get(&fpu_checks[0]), (long)atomic_get(&fpu_checks[1]));
	atomic_set(&stop, 1);
}

static bool voluntary_context_intact(uintptr_t id)
{
	/* Only callee-saved FP registers and fcsr survive a voluntary switch;
	 * the same rule the FPU gate applies around aic_fpu_yield_probe().
	 */
	for (size_t reg = 0; reg < 32; ++reg) {
		if ((reg == 8 || reg == 9 || (reg >= 18 && reg <= 27)) &&
		    patterns[id][reg] != observed[id][reg]) {
			return false;
		}
	}
	return observed[id][REGISTERS - 1] == patterns[id][REGISTERS - 1];
}

static void peer_body(void *arg, void *unused1, void *unused2)
{
	uintptr_t id = (uintptr_t)arg;

	ARG_UNUSED(unused1);
	ARG_UNUSED(unused2);
	if (id == 1 && IS_ENABLED(CONFIG_AIC_Z0_STRESS_INJECT_PEER)) {
		return;
	}
	while (atomic_get(&stop) == 0) {
		mil_sample();
		aic_fpu_yield_probe(patterns[id], observed[id]);
		if (IS_ENABLED(CONFIG_AIC_Z0_STRESS_INJECT_FPU)) {
			observed[id][8] ^= 1U;
		}
		if (!voluntary_context_intact(id)) {
			peer_failure("voluntary_context_mismatch", id, -1);
			return;
		}
		atomic_inc(&voluntary_checks);

		atomic_inc(&epochs[id]);
		int probe = aic_fpu_preempt_probe(patterns[id], observed[id],
						  &epochs[1 - id],
						  CONFIG_AIC_Z0_STRESS_PEER_SPIN_LIMIT);
		if (atomic_get(&stop) != 0) {
			return;
		}
		if (probe != 0 || memcmp(patterns[id], observed[id], sizeof(patterns[id])) != 0) {
			peer_failure(probe != 0 ? "peer_preemption_missed"
					       : "fpu_register_mismatch", id, probe);
			return;
		}
		atomic_inc(&fpu_checks[id]);
	}
}

static void sleeper_body(void *unused1, void *unused2, void *unused3)
{
	ARG_UNUSED(unused1);
	ARG_UNUSED(unused2);
	ARG_UNUSED(unused3);
	while (atomic_get(&stop) == 0) {
		k_sleep(K_MSEC(CONFIG_AIC_Z0_STRESS_SLEEP_MS));
		atomic_inc(&timeout_wakeups);
		mil_sample();
	}
}

struct progress {
	uint32_t timer;
	uint32_t peer[PEERS];
	uint32_t voluntary;
	uint32_t wakeups;
	uint32_t mil;
};

static void progress_snapshot(struct progress *sample)
{
	sample->timer = (uint32_t)atomic_get(&timer_expiries);
	sample->peer[0] = (uint32_t)atomic_get(&fpu_checks[0]);
	sample->peer[1] = (uint32_t)atomic_get(&fpu_checks[1]);
	sample->voluntary = (uint32_t)atomic_get(&voluntary_checks);
	sample->wakeups = (uint32_t)atomic_get(&timeout_wakeups);
	sample->mil = (uint32_t)atomic_get(&mil_samples);
}

static const char *stalled_path(const struct progress *previous,
			       const struct progress *current)
{
	if (current->timer == previous->timer) {
		return "timer_isr";
	}
	if (current->peer[0] == previous->peer[0]) {
		return "fpu_a";
	}
	if (current->peer[1] == previous->peer[1]) {
		return "fpu_b";
	}
	if (current->voluntary == previous->voluntary) {
		return "voluntary";
	}
	if (current->wakeups == previous->wakeups) {
		return "timeout_wakeups";
	}
#if defined(CONFIG_SOC_SERIES_D13X)
	/* Off D13x the CSR read is compiled out, so a constant zero is the
	 * expected value there rather than a stalled counter.
	 */
	if (current->mil == previous->mil) {
		return "mil_samples";
	}
#endif
	return NULL;
}

static void report(int64_t elapsed_ms, uint64_t mtime_delta, const char *result,
		   const char *reason)
{
	printk("Z0-STRESS-SUMMARY schema=1 result=%s runtime_ms=%lld mtime_delta=%llu "
	       "timer_isr=%ld fpu_a=%ld fpu_b=%ld voluntary=%ld timeout_wakeups=%ld "
	       "mil_samples=%ld mil_violations=%ld mil_worst=%02lx fpu_failures=%ld%s%s\n",
	       result, (long long)elapsed_ms, (unsigned long long)mtime_delta,
	       (long)atomic_get(&timer_expiries), (long)atomic_get(&fpu_checks[0]),
	       (long)atomic_get(&fpu_checks[1]), (long)atomic_get(&voluntary_checks),
	       (long)atomic_get(&timeout_wakeups), (long)atomic_get(&mil_samples),
	       (long)atomic_get(&mil_violations), (unsigned long)atomic_get(&mil_worst),
	       (long)atomic_get(&fpu_failures),
	       reason != NULL ? " reason=" : "", reason != NULL ? reason : "");
}

static void finish(bool passed, int64_t elapsed_ms, uint64_t mtime_delta,
		   const char *reason)
{
	atomic_set(&stop, 1);
	for (size_t id = 0; id < PEERS; ++id) {
		(void)k_thread_join(&peer_threads[id], K_SECONDS(30));
	}
	(void)k_thread_join(&sleep_thread, K_SECONDS(30));
	k_timer_stop(&stress_timer);
	report(elapsed_ms, mtime_delta, passed ? "PASS" : "FAIL", reason);
	printk("%s\n", passed ? "Z0-STRESS PASS\nPROJECT EXECUTION SUCCESSFUL"
			      : "Z0-STRESS FAIL\nPROJECT EXECUTION FAILED");
}

int main(void)
{
	const int64_t start = k_uptime_get();
	const uint64_t start_mtime = raw_mtime();
	struct progress previous = {0};
	struct progress current = {0};
	int64_t last_heartbeat = start;
	bool first = true;

	printk("Z0-STRESS begin schema=1 duration_s=%d heartbeat_s=%d timer_ms=%d sleep_ms=%d "
	       "peer_spin_limit=%d raw_mtime=%d inject=%s\n",
	       CONFIG_AIC_Z0_STRESS_DURATION_SEC, CONFIG_AIC_Z0_STRESS_HEARTBEAT_SEC,
	       CONFIG_AIC_Z0_STRESS_TIMER_PERIOD_MS, CONFIG_AIC_Z0_STRESS_SLEEP_MS,
	       CONFIG_AIC_Z0_STRESS_PEER_SPIN_LIMIT, AIC_RAW_MTIME,
	       AIC_INJECTION);

	for (size_t id = 0; id < PEERS; ++id) {
		for (size_t reg = 0; reg < 32; ++reg) {
			/* Alternate NaN-boxed f32 and finite f64, unique per thread/register. */
			patterns[id][reg] = (reg % 2 == 0 ? 0xffffffff3f800000ULL
					 : 0x3ff0000000000000ULL) |
					    ((uint64_t)(id + 1) << 12) | reg;
		}
		patterns[id][REGISTERS - 1] = id + 1;
	}

	/* The blocking worker must outrank the spinning peers, or it never gets
	 * the CPU between their yields; the peers keep equal priority so the
	 * tick timeslice preempts one by the other.
	 */
	for (size_t id = 0; id < PEERS; ++id) {
		k_thread_create(&peer_threads[id], peer_stacks[id],
				K_THREAD_STACK_SIZEOF(peer_stacks[id]), peer_body,
				(void *)id, NULL, NULL, 6, K_FP_REGS, K_FOREVER);
	}
	k_thread_create(&sleep_thread, sleep_stack, K_THREAD_STACK_SIZEOF(sleep_stack),
			sleeper_body, NULL, NULL, NULL, 5, 0, K_FOREVER);

	k_timer_start(&stress_timer, K_MSEC(CONFIG_AIC_Z0_STRESS_TIMER_PERIOD_MS),
		      K_MSEC(CONFIG_AIC_Z0_STRESS_TIMER_PERIOD_MS));
	if (IS_ENABLED(CONFIG_AIC_Z0_STRESS_INJECT_TIMER)) {
		k_timer_stop(&stress_timer);
	}
	if (IS_ENABLED(CONFIG_AIC_Z0_STRESS_INJECT_MIL)) {
		atomic_inc(&mil_violations);
	}
	k_thread_start(&peer_threads[0]);
	k_thread_start(&peer_threads[1]);
	k_thread_start(&sleep_thread);

	while (true) {
		k_sleep(K_MSEC(50));
		const int64_t now = k_uptime_get();
		const int64_t elapsed = now - start;

		if (atomic_get(&mil_violations) != 0 && failure_reason == NULL) {
			failure_reason = "mil_violation";
		}
		if (atomic_get(&fpu_failures) != 0 && failure_reason == NULL) {
			failure_reason = "fpu_failure";
		}
		if (failure_reason != NULL) {
			finish(false, elapsed, raw_mtime() - start_mtime, failure_reason);
			return 1;
		}

		if (now - last_heartbeat < HEARTBEAT_MS) {
			continue;
		}
		last_heartbeat = now;
		progress_snapshot(&current);
		printk("Z0-STRESS-HB schema=1 elapsed_ms=%lld mtime_delta=%llu timer_isr=%ld "
		       "fpu_a=%ld fpu_b=%ld voluntary=%ld timeout_wakeups=%ld mil_samples=%ld "
		       "mil_violations=%ld mil_worst=%02lx fpu_failures=%ld\n",
		       (long long)elapsed,
		       (unsigned long long)(raw_mtime() - start_mtime),
		       (long)current.timer, (long)current.peer[0], (long)current.peer[1],
		       (long)current.voluntary, (long)current.wakeups, (long)current.mil,
		       (long)atomic_get(&mil_violations),
		       (unsigned long)atomic_get(&mil_worst),
		       (long)atomic_get(&fpu_failures));

		if (!first) {
			const char *stalled = stalled_path(&previous, &current);

			if (stalled != NULL) {
				finish(false, elapsed, raw_mtime() - start_mtime, stalled);
				return 1;
			}
		}
		first = false;
		previous = current;

		if (elapsed >= DURATION_MS) {
			finish(true, elapsed, raw_mtime() - start_mtime, NULL);
			return 0;
		}
	}
}
