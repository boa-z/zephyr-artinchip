/* SPDX-License-Identifier: Apache-2.0 */
#include <artinchip/module.h>
#include <zephyr/kernel.h>
#include <zephyr/sys/printk.h>

BUILD_ASSERT(IS_ENABLED(CONFIG_ARTINCHIP_MODULE), "ArtInChip Kconfig not loaded");
K_SEM_DEFINE(wakeup, 0, 1);
K_SEM_DEFINE(done, 0, 1);

static void worker(void *a, void *b, void *c)
{
	ARG_UNUSED(a);
	ARG_UNUSED(b);
	ARG_UNUSED(c);
	__ASSERT(k_sem_take(&wakeup, K_FOREVER) == 0, "semaphore wait failed");
	k_sleep(K_MSEC(20));
	k_sem_give(&done);
}

K_THREAD_DEFINE(worker_id, 1024, worker, NULL, NULL, NULL, 2, 0, 0);

int main(void)
{
	int64_t start = k_uptime_get();

	printk("MODULE: %s\n", artinchip_module_identity());
	k_sem_give(&wakeup);
	__ASSERT(k_sem_take(&done, K_SECONDS(1)) == 0, "worker did not complete");
	__ASSERT(k_uptime_get() - start >= 20, "timer did not advance");
	__ASSERT(k_sem_take(&done, K_MSEC(20)) == -EAGAIN, "timeout failed");
	printk("BRINGUP: thread/semaphore/timeout PASS\n");
	return 0;
}
