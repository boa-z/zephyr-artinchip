/* SPDX-License-Identifier: Apache-2.0 */
/* Compile the actual pinned/patched driver; fake only device, MMIO and CSR I/O. */
#include <zephyr/ztest.h>
#include <zephyr/kernel.h>
#include <zephyr/arch/riscv/csr.h>
#include <zephyr/arch/riscv/icsr.h>
#include <zephyr/device.h>
#include <zephyr/drivers/interrupt_controller/riscv_clic.h>
#include <string.h>

#define TEST_BASE 0x100000U
#define TEST_IRQS 96U
static uint8_t registers[0x1000 + 4 * TEST_IRQS];
static uint32_t csr_writes;
static uint32_t info_reads;
static uint32_t threshold_writes;
static const struct device test_device;

static void write32(uint32_t value, uintptr_t address)
{
	uint32_t offset = address - TEST_BASE;

	zassert_true(offset + 4U <= sizeof(registers), "MMIO write out of range");
	zassert_equal(offset % 4U, 0U, "unaligned word write");
	memcpy(&registers[offset], &value, sizeof(value));
	if (offset == 8U) {
		threshold_writes++;
	}
}

static uint32_t read32(uintptr_t address)
{
	uint32_t value;
	uint32_t offset = address - TEST_BASE;

	zassert_true(offset + 4U <= sizeof(registers), "MMIO read out of range");
	memcpy(&value, &registers[offset], sizeof(value));
	if (offset == 4U) {
		info_reads++;
	}
	return value;
}

static void write8(uint8_t value, uintptr_t address)
{
	zassert_true(address >= TEST_BASE && address - TEST_BASE < sizeof(registers));
	registers[address - TEST_BASE] = value;
}

static uint8_t read8(uintptr_t address)
{
	zassert_true(address >= TEST_BASE && address - TEST_BASE < sizeof(registers));
	return registers[address - TEST_BASE];
}

#undef sys_write32
#undef sys_read32
#undef sys_write8
#undef sys_read8
#define sys_write32(value, address) write32(value, address)
#define sys_read32(address) read32(address)
#define sys_write8(value, address) write8(value, address)
#define sys_read8(address) read8(address)
#undef CONFIG_PMP_STACK_GUARD
#undef csr_write
#define csr_write(reg, value) do { ARG_UNUSED(value); csr_writes++; } while (0)
#undef DEVICE_DT_INST_GET
#define DEVICE_DT_INST_GET(index) (&test_device)
#undef DT_INST_FOREACH_STATUS_OKAY
#define DT_INST_FOREACH_STATUS_OKAY(fn)
#undef DT_HAS_COMPAT_STATUS_OKAY
#define DT_HAS_COMPAT_STATUS_OKAY(compat) 1
#undef CONFIG_NUM_IRQS
#define CONFIG_NUM_IRQS TEST_IRQS
#define CONFIG_LEGACY_CLIC_MEMORYMAP_ACCESS 1
#define CONFIG_CLIC_SMCLICCONFIG_EXT 1
#if defined(CONFIG_AIC_CLIC_TEST_LEGACY)
#define CONFIG_CLIC_LEGACY_MMIO_LAYOUT 1
#elif defined(CONFIG_AIC_CLIC_TEST_NUCLEI)
#define CONFIG_NUCLEI_ECLIC 1
#endif

#include "intc_clic.c"

static struct clic_data test_data;
static const struct clic_config test_config = {.base = TEST_BASE};
static const struct device test_device = {.config = &test_config, .data = &test_data};

static void reset(uint8_t bits, uint8_t level)
{
	uint32_t info = ((uint32_t)bits << 21) | TEST_IRQS;

	memset(registers, 0xa5, sizeof(registers));
	memcpy(&registers[4], &info, sizeof(info));
	test_data.intctlbits = bits;
	test_data.nlbits = level;
	csr_writes = 0U;
	info_reads = 0U;
	threshold_writes = 0U;
}

ZTEST(clic_mmio, test_layout_and_threshold)
{
	reset(3U, 2U);
	zassert_equal(clic_init(&test_device), 0);
	if (IS_ENABLED(CONFIG_AIC_CLIC_TEST_LEGACY) || IS_ENABLED(CONFIG_AIC_CLIC_TEST_NUCLEI)) {
		zassert_equal(info_reads, 1U);
		zassert_equal(threshold_writes, 1U);
		zassert_equal(read32(TEST_BASE + 8U), 0U);
		zassert_equal(csr_writes, 0U);
		zassert_equal((registers[0] >> 1) & 15U, 2U);
	} else {
		zassert_equal(info_reads, 0U);
		zassert_equal(threshold_writes, 0U);
		zassert_equal(csr_writes, 1U);
		zassert_equal(registers[0] & 15U, 2U);
	}
	union CLICMTH threshold = {.qw = 0U};
	threshold.b.mth = 0x5aU;
	zassert_equal(threshold.qw, 0x5a000000U);
	for (uint32_t offset = 0x1000U; offset < sizeof(registers); offset++) {
		zassert_equal(registers[offset], 0U);
	}
}

ZTEST(clic_mmio, test_priority_widths)
{
	for (uint8_t bits = 0U; bits <= 8U; bits++) {
		reset(bits, 0U);
		zassert_equal(clic_init(&test_device), 0);
		riscv_clic_irq_priority_set(95U, 0U, 0U);
		zassert_equal(registers[0x1000U + 4U * 95U + 3U], (1U << (8U - bits)) - 1U);
		riscv_clic_irq_priority_set(95U, 255U, 0U);
		zassert_equal(registers[0x1000U + 4U * 95U + 3U], 255U);
	}
}

ZTEST(clic_mmio, test_level_clamp)
{
	reset(2U, 4U);
	if (IS_ENABLED(CONFIG_AIC_CLIC_TEST_LEGACY) || IS_ENABLED(CONFIG_AIC_CLIC_TEST_NUCLEI)) {
		zassert_equal(clic_init(&test_device), 0);
		zassert_equal(test_data.nlbits, 2U);
	}
}

ZTEST(clic_mmio, test_invalid_width)
{
	for (uint8_t bits = 9U; bits < 16U; bits++) {
		reset(bits, 0U);
		zassert_equal(clic_init(&test_device), -EINVAL);
	}
}

ZTEST(clic_mmio, test_irq_edges_enable_pending_shv)
{
	reset(3U, 0U);
	zassert_equal(clic_init(&test_device), 0);
	for (uint32_t irq = 0U; irq < TEST_IRQS; irq += TEST_IRQS - 1U) {
		riscv_clic_irq_enable(irq);
		zassert_equal(riscv_clic_irq_is_enabled(irq), 1);
		zassert_equal(registers[0x1000U + 4U * irq + 1U], 1U);
		riscv_clic_irq_disable(irq);
		zassert_equal(riscv_clic_irq_is_enabled(irq), 0);
		riscv_clic_irq_set_pending(irq);
		zassert_equal(registers[0x1000U + 4U * irq], 1U);
		riscv_clic_irq_priority_set(irq, 1U, 2U);
		uint8_t before = registers[0x1000U + 4U * irq + 2U];
		riscv_clic_irq_vector_set(irq);
		zassert_equal(registers[0x1000U + 4U * irq + 2U], before | 1U);
	}
}

ZTEST_SUITE(clic_mmio, NULL, NULL, NULL, NULL, NULL);
