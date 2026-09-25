# Baseline

Date: 2026-09-25. Zephyr is pinned to official commit
`839728050444f90d06870b5fc9bbbda106d91459` (source VERSION 4.4.99).
The owner's separate `boa-z/zephyr` checkout is at that commit and was clean
at entry. Normal dependencies use a separate `zephyr-upstream` clone with the
official remote. Initial bootstrap used no patches. The final D13x candidate applies the explicit
legacy CLIC prerequisite in patches/zephyr; its exact base and diff are verified.

Luban-Lite SoC reference: `boa-w/luban-lite`, commit
`c5807f9e7d18292f920dafaa018b8174635085c4`. That Git object is available locally
in the product SDK and is read using `git show`, without changing its checkout.
The fixed SDK's D13x targets do not include D50T-2-Lite.

Board reference: owner-supplied `boa-w/luban-lite-jc-d50t-rev`, branch
`pocketjs-d13x`, commit `0ac5adf01f6c5e7f60f3e5b37c56076cbd09c29b`.
Its existing changes are `.vscode/settings.json`, the D50T application submodule,
`packages/custom/lvgl-aic`, and an untracked mbedTLS certificate source.
These are preserved. Product-specific board evidence supplements, rather than
replaces, the fixed SoC baseline. No product build/test result is inherited.

The hardware requirement is D50T-2-Lite, D133ECS, E907FDP, 1 MiB SRAM and 16 MiB
PSRAM. Capacity is not a claim that either memory is wholly available to Zephyr.

Local tools initially installed: Python 3.13.15, CMake 4.4.3, Ninja 1.13.2.
Project-local west is 1.5.0. The pinned source requests Zephyr SDK 1.0.1;
its Windows x86_64 minimal bundle and GNU RISC-V archive were downloaded and
verified against the publisher's release SHA-256 list. GNU GCC is 14.3.0.
WSL was unavailable; validation uses native Windows tooling.

SDK archive SHA-256:

- `zephyr-sdk-1.0.1_windows-x86_64_minimal.7z`:
  `17a557e7c6cea5e5c589508fe45a3f26aca4fa2c6153fe3e7b03aeb4b93fea4b`
- `toolchain_gnu_windows-x86_64_riscv64-zephyr-elf.7z`:
  `8d816b4452c4e6e08630f7e9837a6cca7d80ec88584e26997f63a4442831003a`

Dependency SHA pinning does not establish bit-for-bit binary reproducibility.
Record source commit/dirty state and tool versions alongside every artifact.
