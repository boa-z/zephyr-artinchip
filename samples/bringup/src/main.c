/* SPDX-License-Identifier: Apache-2.0 */
#include <artinchip/module.h>
#include <zephyr/kernel.h>
#include <zephyr/sys/printk.h>

BUILD_ASSERT(IS_ENABLED(CONFIG_ARTINCHIP_MODULE), "ArtInChip Kconfig not loaded");
K_SEM_DEFINE(wakeup, 0, 1);
K_SEM_DEFINE(done, 0, 1);

static void fail(const char *reason)
{
	printk("BRINGUP: FAIL: %s\nPROJECT EXECUTION FAILED\n", reason);
	k_panic();
}

static void worker(void *a, void *b, void *c)
{
	ARG_UNUSED(a);
	ARG_UNUSED(b);
	ARG_UNUSED(c);
	if (k_sem_take(&wakeup, K_FOREVER) != 0) {
		fail("semaphore wait failed");
	}
	k_sleep(K_MSEC(20));
	if (!IS_ENABLED(CONFIG_ARTINCHIP_BRINGUP_DROP_SIGNAL)) {
		k_sem_give(&done);
	}
}

K_THREAD_DEFINE(worker_id, 1024, worker, NULL, NULL, NULL, 2, 0, 0);

int main(void)
{
	int64_t start = k_uptime_get();

	printk("MODULE: %s\n", artinchip_module_identity());
	k_sem_give(&wakeup);
	if (k_sem_take(&done, K_SECONDS(1)) != 0) {
		fail("worker did not complete");
	}
	if (k_uptime_get() - start < 20) {
		fail("timer did not advance");
	}
	if (k_sem_take(&done, K_MSEC(20)) != -EAGAIN) {
		fail("timeout failed");
	}
	printk("BRINGUP: thread/semaphore/timeout PASS\n");
	return 0;
}
