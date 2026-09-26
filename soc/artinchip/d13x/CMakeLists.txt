# SPDX-License-Identifier: Apache-2.0
if(NOT CONFIG_ARTINCHIP_D13X_BOOT_CONTRACT)
  # Bringing up the SoC must not depend on acknowledging the handoff; the
  # acknowledgement is enforced where a build becomes a hardware image, by
  # scripts/package_candidate.py.
  message(WARNING
          "D13x build without CONFIG_ARTINCHIP_D13X_BOOT_CONTRACT: software "
          "candidate only, scripts/package_candidate.py will refuse to collect "
          "it for hardware use; see docs/bringup/d13x-boot-contract.md")
endif()
set(SOC_LINKER_SCRIPT ${ZEPHYR_BASE}/include/zephyr/arch/riscv/common/linker.ld CACHE INTERNAL "")
zephyr_library()
zephyr_library_sources(reset.S)
zephyr_library_sources(soc_irq.S)
zephyr_include_directories(.)
