# zephyr-artinchip

Community-maintained ArtInChip support as an out-of-tree Zephyr module and west
manifest repository. The current scope is P0 infrastructure and a D133ECS
SRAM-only Z0 software candidate. Hardware validation is pending.

## Workspace

Use Python 3.12 or later, CMake, Ninja and Git. In a new workspace, place this
repository in `zephyr-artinchip`, create/activate a Python virtual environment,
install `west`, then run from this repository:

```sh
west init -l .
west update
python -m pip install -r ../zephyr-upstream/scripts/requirements-base.txt
python scripts/install_sdk.py ../toolchains
```

Set `ZEPHYR_SDK_INSTALL_DIR` to the resulting `zephyr-sdk-1.0.1` directory in
the current shell. No global configuration changes are necessary.
The upstream dependency lives in `zephyr-upstream` so an existing `zephyr`
staging fork is not modified. SDK/product source is never a west dependency.

```sh
west manifest --validate
python scripts/environment.py --output artifacts/environment.json
west build -b qemu_riscv32 samples/bringup -d build-qemu -- -DCONFIG_MINIMAL_LIBC=y
west build -d build-qemu -t run
```

The sample asserts module discovery at compile time and calls code from the
module library. Expected runtime lines are `MODULE: zephyr-artinchip` and
`BRINGUP: thread/semaphore/timeout PASS`. A successful build alone is not a
runtime pass. Exit the interactive QEMU session with Ctrl-A, X.

No remote publication or automatic hardware programming is performed.
See `CONTRIBUTING.md` for source licensing and human review requirements.
