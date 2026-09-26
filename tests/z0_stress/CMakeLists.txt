# SPDX-License-Identifier: Apache-2.0
cmake_minimum_required(VERSION 3.20.0)
find_package(Zephyr REQUIRED HINTS $ENV{ZEPHYR_BASE})
project(artinchip_z0_stress)
# Reuse the audited FPU register-lifetime probe instead of reinventing it.
target_sources(app PRIVATE src/main.c ${CMAKE_CURRENT_SOURCE_DIR}/../fpu/src/probe.S)
