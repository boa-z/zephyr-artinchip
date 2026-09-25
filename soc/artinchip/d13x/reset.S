/* SPDX-License-Identifier: Apache-2.0
 * Register-level adaptation from ArtInChip D13x system.c/startup_gcc.S.
 * Copyright (c) 2022-2025, ArtInChip Technology Co., Ltd
 * Copyright (C) 2017-2019 Alibaba Group Holding Limited
 * Modified: stackless Zephyr hook; no SDK trap handler or cache reinitialization.
 */
#include <zephyr/toolchain.h>
#include <zephyr/linker/sections.h>

GTEXT(soc_reset_hook)
SECTION_FUNC(TEXT, soc_reset_hook)
	/* The bootloader must already have masked interrupts before __start. */
	csrci mstatus, 8
	/* Zephyr owns software stacking: disable E907 SPUSHEN and SPSWAPEN. */
	li t0, ((1 << 16) | (1 << 17))
	csrc 0x7e1, t0
	fence iorw, iorw
	ret
