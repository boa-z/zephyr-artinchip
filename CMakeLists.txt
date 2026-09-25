# SPDX-License-Identifier: Apache-2.0
zephyr_library_named(artinchip_module)
zephyr_library_sources(src/module.c)
zephyr_include_directories(include)
message(STATUS "ArtInChip out-of-tree module loaded")
