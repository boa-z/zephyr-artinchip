# SPDX-License-Identifier: Apache-2.0
if(NOT CONFIG_ARTINCHIP_D13X_BOOT_CONTRACT)
  message(FATAL_ERROR "D13x requires explicit boot contract opt-in; see docs/bringup/d13x-boot-contract.md")
endif()
set(SOC_LINKER_SCRIPT ${ZEPHYR_BASE}/include/zephyr/arch/riscv/common/linker.ld CACHE INTERNAL "")
zephyr_library()
zephyr_library_sources(reset.S)
zephyr_library_sources(soc_irq.S)
zephyr_include_directories(.)
