/* SPDX-License-Identifier: Apache-2.0 */
#include <artinchip/module.h>
#include <zephyr/kernel.h>
#include <zephyr/sys/atomic.h>
#include <zephyr/ztest.h>

BUILD_ASSERT(IS_ENABLED(CONFIG_ARTINCHIP_MODULE));
K_SEM_DEFINE(signal, 0, 1);
K_THREAD_STACK_DEFINE(worker_stack, 1024);
static struct k_thread worker_thread;
static atomic_t observed;

static void delayed_worker(void *a, void *b, void *c)
{
	ARG_UNUSED(a);
	ARG_UNUSED(b);
	ARG_UNUSED(c);
	k_sleep(K_MSEC(20));
	atomic_set(&observed, 1);
	k_sem_give(&signal);
}

ZTEST(artinchip_kernel, test_module)
{
	zassert_str_equal(artinchip_module_identity(), "zephyr-artinchip");
}

ZTEST(artinchip_kernel, test_thread_semaphore)
{
	k_sem_reset(&signal);
	atomic_clear(&observed);
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

ZTEST(artinchip_kernel, test_timer_preemption)
{
	int priority = k_thread_priority_get(k_current_get());
	int64_t deadline = k_uptime_get() + 1000;

	k_sem_reset(&signal);
	atomic_clear(&observed);
	k_thread_create(&worker_thread, worker_stack, K_THREAD_STACK_SIZEOF(worker_stack),
			delayed_worker, NULL, NULL, NULL, priority - 1, 0, K_NO_WAIT);
	/* No yield/sleep here: the timer must wake and preempt this thread. */
	while ((atomic_get(&observed) == 0) && (k_uptime_get() < deadline)) {
		compiler_barrier();
	}
	zassert_equal(atomic_get(&observed), 1);
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

ZTEST_SUITE(artinchip_kernel, NULL, NULL, NULL, NULL, NULL);
