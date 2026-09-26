# Z0 稳定性 Gate 执行手册

本手册定义关闭 Z0 之前必须在**物理硬件**上全部通过的稳定性 Gate，以及
失败时的证据留存约定。它不引入新的诊断轮次，也不改 CLIC 修复逻辑。

## 基线与冻结项

- Z0 kernel baseline：提交 `c0b15e9`（D13x mcause-only CLIC 上下文
  save/restore，MPIL 取 bits[23:16]）+ `4442a91`（第十二轮实板 9/9 PASS、
  MIL 闩锁解除记录）。
- CLIC 修复逻辑（`soc/` 下 save/restore/MRET 路径）已冻结，本 Gate 期间
  不得再改。第十二轮已证明该修复使线程态 MIL 保持 0、9/9 通过。
- 冻结确认项沿用第十二轮：timer frequency、mtimecmp 算法、等待预算、
  线程优先级、WFI 行为、CLICCFG.nlbits=0、SHV、定时器配置、用例清单
  （kernel 9 项 / fpu 1 项）全部不变。
- 本次仅改动 `tests/kernel/src/main.c`、`tests/fpu/src/main.c`（内联 MIL
  心跳，未增删 ztest 用例），并新增 `tests/fpu/product-window.conf` 与
  `scripts/package_gate_trial.py`。`scripts/package_kernel_trial.py` 仍固定
  第十二轮 SHA，未改。
- 第二轮（Gate 项 4 专用镜像）新增独立应用 `tests/z0_stress/`、离线窗口
  检查 `scripts/window_fit.py`、打包器的 `--app stress` 分支，并把必需软件
  Gate 迁到 Ubuntu。CLIC 修复逻辑、`soc/` 路径、timer frequency、mtimecmp
  算法、优先级、WFI、CLICCFG/SHV 与 kernel/fpu 用例清单仍然**一字未改**；
  已交付的 kernel/fpu gate 镜像与哈希不变，本轮不重打它们。

## MIL 心跳监控（线程态必须保持 0）

两处测试在自旋/等待循环内**静默采样** MINTSTATUS（CSR 0x346）顶字节 MIL，
循环外打印一行心跳并断言违例数为 0；采样放在打印之外以免 UART 干扰
定时敏感窗口。仅 D13x 编译进 CSR 读，off-target（QEMU）采样被编译掉、
计数恒 0，QEMU 判定不变。

- kernel：每个自旋/等待用例打印
  `KERNEL-MILHB schema=1 test=<name> samples=<n> violations=<n> mil_max=<hh>`。
- fpu：stress 双线程与监督轮询共同覆盖整个 120 s，打印
  `FPU-MILHB schema=1 samples=<n> violations=<n> mil_worst=<hh> uptime_ms=<t> counts=<a>+<b>`，
  并每 5 s 一次心跳。
- `tests/z0_stress`：MIL 只在**线程上下文**采样（ISR 内只做原子自增，不采样、
  不打印），采样与 5 s 心跳一起并入 `Z0-STRESS-HB` 行的 `mil=` 字段，详见下节。

判读：`violations=0` 且 `mil_max`/`mil_worst=00` 为通过。任一非零即线程态
MIL 离开 0（第十二轮修复所清除的 0xFF 闩锁缺陷复发），该用例 FAIL。

## Gate 项（全部物理硬件，全部必须 PASS）

1. **重复冷启动**：对同一候选镜像做不少于 10 次独立冷启动（断电/Reset
   重启），每次都要到达 `PROJECT EXECUTION SUCCESSFUL`，不得出现挂起、
   fault 或循环重启。记录每次的 Reset flag 与墙钟耗时。
2. **kernel 9/9 多轮实板**：kernel 套件在板上连续多轮（建议 ≥5 轮）全部
   9/9 PASS，每轮 `KERNEL-MILHB ... violations=0`。
3. **FPU 实板上下文测试**：fpu 套件 `artinchip_fpu.context_registers` PASS，
   满足 ≥5000 次/线程的对等抢占校验 + 200 次自愿切换校验，
   `FPU-MILHB ... violations=0`。
4. **≥10 分钟 kernel+FPU stress**：kernel 与 fpu 交替/组合连续运行不少于
   10 分钟，全程 MIL 心跳 `violations=0`，无挂起、无 fault、无重启。
   本项由专用镜像 `D50T_Z0_stress_gate.img`（`tests/z0_stress`，600 s 配置）
   承担，见下节；kernel/fpu 套件自身的 0.529 s / 12.3 s 单轮不构成该项证据。

## Gate 项 4 专用：`tests/z0_stress` 600 s 持续压力应用

这是**独立应用**，不链接 kernel/fpu 的 ztest 套件，也不把它们的输出重印一遍。
它在一个连续 600 s 窗口里同时驱动五条真实路径，每条都有独立计数器：

| 被观测实体 | 覆盖内容 | 计数器字段 |
| --- | --- | --- |
| 机器定时器 | 5 ms `k_timer` 周期到期 + mtimecmp 重编 | `timer_isr`（ISR 内只 `atomic_inc`，不打印、不采样 MIL） |
| 时间片抢占 | 两条同优先级（6）FPU 线程互相抢占 | `fpu_a`、`fpu_b` |
| 自愿切换 | ECALL/yield 后校验 ABI 保留的 f32/f64 全 32 槽与 fcsr | `voluntary` |
| 阻塞睡眠 | 更高优先级（5）工作线程 `k_sleep(20 ms)` 唤醒 | `timeout_wakeups` |
| FPU 上下文 | 每条 peer 载入 NaN-boxed f32 / 有限 f64 专属模式，复用 `tests/fpu/src/probe.S` | `fpu_failures` |
| 线程态 MIL | 仅在线程上下文静默采样 MINTSTATUS 顶字节 | `mil_samples`、`mil_violations`、`mil_worst` |

双时源：`k_uptime_get()` 与原始 mtime 差值同时打印，二者只互为观测，不做
频率判定。

日志行：

```text
Z0-STRESS begin schema=1 duration_s=600 heartbeat_s=5 timer_ms=5 sleep_ms=20 peer_spin_limit=1000000 raw_mtime=1 inject=none
Z0-STRESS-HB schema=1 elapsed_ms=… mtime_delta=… timer_isr=… fpu_a=… fpu_b=… voluntary=… timeout_wakeups=… mil_samples=… mil_violations=… mil_worst=… fpu_failures=…
Z0-STRESS-SUMMARY schema=1 result=PASS runtime_ms=… mtime_delta=… timer_isr=… fpu_a=… fpu_b=… voluntary=… timeout_wakeups=… mil_samples=… mil_violations=… mil_worst=… fpu_failures=…
Z0-STRESS PASS
PROJECT EXECUTION SUCCESSFUL
```

判读规则（任一不满足即 FAIL，**不得**把无输出当成功）：

1. 首行 `duration_s=600` 且 `inject=none`；出现 `inject=<mode>` 说明这是负向
   探针构建，绝不能当硬件 Gate 结果。
2. 每约 5 s 一条 `Z0-STRESS-HB`；串口连续超过约 15 s 无输出即视为挂起，
   保留日志并复位烧回原版。
3. 每条心跳的 `timer_isr`、`fpu_a`、`fpu_b`、`voluntary`、`timeout_wakeups`
   都必须在相邻两次采样间增长；一旦停滞，应用立刻以该字段名收尾 FAIL，
   不等 600 s 结束。D13x 上 `mil_samples` 同受此约束（off-target 采样被编译
   掉，恒 0 属预期，不参与停滞判定）。
4. 全程 `mil_violations=0`、`mil_worst=00`、`fpu_failures=0`。
5. 结尾必须是 `result=PASS` + `Z0-STRESS PASS` + `PROJECT EXECUTION SUCCESSFUL`。
6. `runtime_ms` 应接近 600000；明显偏短说明提前退出，即使写着 PASS 也不算
   该项通过。

两个 profile 是刻意分开的：硬件构建 `CONFIG_AIC_Z0_STRESS_DURATION_SEC=600`
（默认值，`boards/d50t_2_lite_d133ecs.conf` 只加 boot contract），QEMU 用
`boards/qemu_riscv32.conf` 覆盖为 3 s / 1 s 心跳，仅验证应用逻辑与
PASS/FAIL 状态机。打包器对 stress **强制**读取构建 `.config`：缺少该符号、
取值不唯一、或不是 `600` 一律拒绝（短 profile 不可能被打成硬件镜像），
任一 `CONFIG_AIC_Z0_STRESS_INJECT_*` 被启用同样拒绝。

窗口是硬约束：单段 PT_LOAD 必须 `p_memsz <= 65536`。实测目标构建 RAM
44368 B / 64 KiB（**67.70%**）。若后续改动使占用超出，打包器与
`scripts/window_fit.py` 都会**显式失败**；此时不得放宽窗口、不得改硬件假设，
先回报实测占用。

## 构建与打包

构建配方依据第十二轮 `target-build.log` 证据（board `d50t_2_lite/d133ecs`、
显式 overlay、`product-window.conf` 经 EXTRA_CONF_FILE 合并），下列命令已在本
仓库工作区实际执行过（结果见「已构建产物」一节）。用 Windows 短输出路径避免
GNU ar 的 MAX_PATH 问题。重建前先设 `ZEPHYR_BASE`、
`ZEPHYR_SDK_INSTALL_DIR` 并把 `.venv/Scripts` 放入 `PATH`。

```sh
# kernel gate 镜像（含 MIL 心跳）
west build -b d50t_2_lite/d133ecs tests/kernel \
  --build-dir C:/aic-z0-gate-kernel-window --pristine \
  -- -DEXTRA_CONF_FILE=$PWD/tests/kernel/product-window.conf \
     -DDTC_OVERLAY_FILE=$PWD/samples/handoff_probe/product-window.overlay

# fpu gate 镜像（含 MIL 心跳）
west build -b d50t_2_lite/d133ecs tests/fpu \
  --build-dir C:/aic-z0-gate-fpu-window --pristine \
  -- -DEXTRA_CONF_FILE=$PWD/tests/fpu/product-window.conf \
     -DDTC_OVERLAY_FILE=$PWD/samples/handoff_probe/product-window.overlay

# 600 s 持续压力镜像（Gate 项 4；不指定 EXTRA_CONF_FILE 时默认即 600 s，
# 这里仍显式合并 product-window.conf 以复用同一 boot contract/144 槽配置）
west build -b d50t_2_lite/d133ecs tests/z0_stress \
  --build-dir C:/aic-z0-gate-stress-window --pristine \
  -- -DEXTRA_CONF_FILE=$PWD/tests/z0_stress/product-window.conf \
     -DDTC_OVERLAY_FILE=$PWD/samples/handoff_probe/product-window.overlay
```

打包进产品窗口镜像（参考镜像必须为已固定的 known-good 产品图，BASELINE
校验始终强制）：

```sh
# 首次：无可复现的已评审 gate 构建，用 --allow-unpinned 记录 ELF/BIN SHA
python scripts/package_gate_trial.py \
  --reference artifacts/z0-kernel-r12-delivery/RESTORE_original_product.img \
  --build C:/aic-z0-gate-kernel-window/zephyr \
  --output artifacts/z0-gate-kernel-delivery \
  --app kernel --allow-unpinned

python scripts/package_gate_trial.py \
  --reference artifacts/z0-kernel-r12-delivery/RESTORE_original_product.img \
  --build C:/aic-z0-gate-fpu-window/zephyr \
  --output artifacts/z0-gate-fpu-delivery \
  --app fpu --allow-unpinned

python scripts/package_gate_trial.py \
  --reference artifacts/z0-kernel-r12-delivery/RESTORE_original_product.img \
  --build C:/aic-z0-gate-stress-window/zephyr \
  --output artifacts/z0-gate-stress-delivery \
  --app stress --allow-unpinned
```

`--allow-unpinned` 会把计算出的 ELF/BIN SHA-256 写进 `verification.json`。
评审通过后把哈希固定进 `package_gate_trial.py` 的 `PINNED[app]` 字典（或每次
传 `--expect-elf-sha`/`--expect-bin-sha`），此后任何被篡改的探针都会在打包阶段
被拒（exit 1）。这与 kernel 第十二轮两段式固定（提交 49c4f5c）的先例一致。
固定项**按 `--app` 分别索引**是刻意的：早先共用一对全局常量时，一旦 pin 了
FPU 的哈希，合法的 kernel 构建会被误拒。

打包器结构校验（kernel/fpu/stress 共用 `window_binding`）：单一 PT_LOAD、
paddr/vaddr=0x40000000、`0 < p_filesz <= p_memsz <= 65536`、重建 BIN 与
zephyr.bin 逐字节相同、入口 `__start`、`_irq_vector_table=144*4`、
`_sw_isr_table=144*8`。stress 额外要求：读取构建 `.config`，
`CONFIG_AIC_Z0_STRESS_DURATION_SEC` 必须**唯一且等于 600**，且四个
`CONFIG_AIC_Z0_STRESS_INJECT_*` 全部未启用。

> **构建前必须 `python scripts/apply_patches.py --check` 通过（本轮实测教训）**：
> 上述结构校验**覆盖不到 CLIC 补丁状态**。本机同时存在两棵 Zephyr 树，误用未打
> 补丁的那棵时，`soc/artinchip/d13x/Kconfig` 里 `select CLIC_LEGACY_MMIO_LAYOUT`
> 因符号未定义而被静默忽略，构建**照常成功**、144 槽表**照常存在**，只有
> `CONFIG_CLIC_LEGACY_MMIO_LAYOUT` 消失（实测 BIN 少 160 B），从而得到一个与
> boot contract 不符却能通过全部结构校验的镜像。kernel/fpu/stress 三个已交付
> gate 镜像均取自打补丁的树，`.config` 里该符号为 `y`，交付有效。每次 gate 构建
> 后除 `--check` 外再确认一句：
> `grep '^CONFIG_CLIC_LEGACY_MMIO_LAYOUT=y' <build>/zephyr/.config`。

> **FPU 窗口占用（已实测）**：fpu 的栈需求大于 kernel（MAIN 2048 + TEST_EXTRA
> 2048 + 两条 2048 线程栈 + FPU 上下文），目标构建实测 RAM 50624 B / 64 KiB
> （77.25%），**未**溢出。kernel gate 为 53408 B（81.49%），stress gate 为
> 44368 B（67.70%）。若后续改动使任一构建超出，打包器的 `p_memsz <= 65536`
> 检查会**显式失败**（不会静默产出坏镜像）；届时不要放宽窗口或改硬件参数，
> 先回报实测 RAM 占用再决定是否调整测试侧栈配置（属测试侧，不属 CLIC 修复
> 逻辑）。

## 已构建产物（2026-09-26）

三个 gate 镜像已按上述命令构建并打包，均在实验窗口内：

| 项 | kernel gate | fpu gate | stress gate（600 s） |
| --- | --- | --- | --- |
| 目录 | `artifacts/z0-gate-kernel-delivery` | `artifacts/z0-gate-fpu-delivery` | `artifacts/z0-gate-stress-delivery` |
| 镜像 | `D50T_Z0_kernel_gate.img` | `D50T_Z0_fpu_gate.img` | `D50T_Z0_stress_gate.img` |
| 镜像 SHA-256 | `bd76a8bb7eafd22fda4d2567c7c9417994af5efc2785318ecc9d90196f02597f` | `1f322dc1cba4e3e187555d18f429da057ce569069d8b38d2a424e9cb99467bc1` | `eb06085f687b7a2d13ff1caac7d29c797c87db7bc0ba3b2f1abfa7d16137dba9` |
| ELF SHA-256 | `1ab0896753d332e0d6f1075a98512b1b068a161e1bb31e564d1b27507a2cbbe2` | `04eba2449e0a0ee75fcc68f0a1ded1858848effb1c04822a6f914cefb0cc20ea` | `a9d485e1ff8afe90376b2af88c248f6484bccc9943d96ebdb30a0474c9953c8b` |
| BIN SHA-256 | `14549f37cc4df97ed54c1281c0125f4cb60e904fbf00ca670ff4839488a7ebe3` | `a144fbb3be29610c7ed896b6adf391943755e971d4d2d6f9ede8bcbea05735dd` | `c0d7a411a47b6b4fe33442c5b892a4e509bad60ce377e2801b56e1332fe5939d` |
| RAM / payload | 53408 B（81.49%）/ 40328 B | 50624 B（77.25%）/ 34620 B | 44368 B（67.70%）/ 30816 B |
| 状态 | `OFFLINE_VERIFIED`（已固定） | `OFFLINE_VERIFIED`（已固定） | `OFFLINE_VERIFIED`（已固定，**实板结果 pending**） |

配套证据：QEMU qemu_riscv32 全量回归 **8/8 场景、28/28 用例通过、无警告**
（bringup/kernel/fpu/clic/z0_stress；stress 以 3 s 短 profile 参与，交付目录内
`qemu-twister.json` 即该单项记录）。

**复现性（在本轮交付提交全部落地后的干净工作树上实测两次）**：换一个**全新构建
目录**做 `--pristine`
重建，RAM 仍为 44368 B（67.70%），`zephyr.bin` 与固定的 `c0d7a411…` **逐字节
相同**；用固定后的打包器重打，产出镜像与交付镜像 `eb0608…` **逐字节相同**。
两个 ELF 逐段比对：24 段相同，仅 `.debug_info`、`.debug_line`、`.debug_str`、
`.debug_line_str` 四段不同（DWARF 内嵌构建目录路径），全部可加载内容一致。
结论是 **BIN 固定才代表载荷内容**；换目录重建时 ELF 哈希必然变化，此时传
`--expect-elf-sha <新哈希>` 即可，BIN 固定与 BASELINE 参考图校验照常强制生效
——这是路径指纹差异，不是篡改，不要用 `--allow-unpinned` 绕过。

哈希**已固定**进 `scripts/package_gate_trial.py` 的 `PINNED['kernel']`、
`PINNED['fpu']` 与 `PINNED['stress']`。kernel/fpu 两镜像已实板 PASS；stress 的
固定只表示**已评审构建**（600 s profile、窗口内、BIN 与交付镜像可跨目录逐字节
复现），其实板结果
仍 pending。初次未固定的记录保留为各交付目录的
`verification-initial-unpinned.json`，未被覆盖。每个目录另含
`READ_ME_FIRST.md`（操作与判读）、`RESTORE_original_product.img`、
`verification.json`、`source-inventory.json`（记录 `c0b15e9`+`4442a91`
基线、交付提交、脏状态与源码哈希）、`SHA256SUMS.txt`、`zephyr.elf/bin/map/dts`、
`product-window.conf/overlay` 与 `target-build.log`。

## Gate 项 4 的失败路径探针（证明它真的会 FAIL）

一个只会打印 PASS 的压力应用没有价值，所以失败判定本身也被测过。

运行期探针：在 qemu_riscv32 上各构建一次，每次只启用一个
`CONFIG_AIC_Z0_STRESS_INJECT_*`，由 `scripts/runtime_probes.py` 断言退出码非 0、
未超时、begin 行含 `inject=<mode>`、SUMMARY 行含 `result=FAIL` 与预期
`reason=<预期>`、且全日志不含 `Z0-STRESS PASS`。`scripts/evidence.py::check_probes`
进一步要求四项探针**齐全**，缺项或任一项未按预期失败即整体 FAIL——沉默或
「跑不出结果」不能通过。

| 注入项 | 预期 `reason` | 实测 |
| --- | --- | --- |
| `INJECT_MIL` | `mil_violation` | FAIL，twister 退出码 1 |
| `INJECT_FPU` | `voluntary_context_mismatch` | FAIL，退出码 1 |
| `INJECT_TIMER` | `timer_isr`（计数器停滞） | FAIL，退出码 1 |
| `INJECT_PEER` | `peer_preemption_missed` | FAIL，退出码 1 |

> 注入只把**判定路径**逼出来，不代表复现了真实硬件缺陷：`INJECT_MIL` 直接驱动
> 违例计数器，并不声称读到了非零 CSR。

打包期拒绝由 `tests/host/test_package_gate.py` 常驻覆盖（7 项，各自断言拒绝
原因）：`.config` 缺少或歧义的 600 s 符号、被缩短的 coverage profile、启用了
任一注入、被篡改的 BIN、被篡改的 ELF、跨 app 混用（kernel 构建当作 `--app
stress`/`fpu` 传入，或未知 app）、参考镜像非 BASELINE。这 7 项在 CI 每次运行。

## 烧录、观察与恢复

1. 用已验证的 AiBurn、先 Reset 再 Boot 流程烧入 gate 镜像。
2. COM11 / 115200 保存**完整**串口日志；烧完仅按 Reset 启动。
3. kernel 预期：`KERNEL-PREFLIGHT begin irq_slots=144` → PASS，9 项用例
   全 PASS、`SUITE PASS (pass=9)`、`PROJECT EXECUTION SUCCESSFUL`，且每条
   `KERNEL-MILHB ... violations=0`。fpu 预期：`FPU-MILHB ... violations=0`
   且 `counts` 达标、`PROJECT EXECUTION SUCCESSFUL`。stress 预期：首行
   `duration_s=600 ... inject=none`，每约 5 s 一条 `Z0-STRESS-HB`，收尾
   `result=PASS` + `Z0-STRESS PASS` + `PROJECT EXECUTION SUCCESSFUL`。
4. 只到达 banner/begin、或 30 s（kernel）/ 180 s（fpu）内无完整结果、或
   出现异常/循环重启：保留日志、复位并烧回原版，不把无输出当成功。
   stress 的观察时限是**自身**的：约 10 分钟墙钟，判据是心跳连续性——连续
   超过约 15 s 无任何 `Z0-STRESS-HB`/`Z0-STRESS-SUMMARY` 输出即视为挂起。
   不要按 kernel 的 30 s 判断它挂起，也不要在它跑到 600 s 之前拔电。
5. 每个 Gate 项完成后烧回包内 `RESTORE_original_product.img` 并确认恢复
   正常，再进行下一项。

## 失败证据留存（任一 Gate 项失败即触发）

- 完整原始串口日志（不截断、不改写），存
  `artifacts/z0-gate-<kernel|fpu|stress>-board-result/board-log.txt`。
- 候选镜像 SHA-256（`D50T_Z0_<app>_gate.img`）与 `verification.json`
  中记录的 ELF/BIN SHA-256、Zephyr build id。
- 摘要 `user-result.json`：失败用例、`KERNEL-MILHB`/`FPU-MILHB`/
  `Z0-STRESS-HB`+`Z0-STRESS-SUMMARY` 行、Reset flag、墙钟耗时、失败点
  main.c 行号。
- 保留失败日志并解释后续修复，**不得**用新日志替换失败日志，**不得**
  关闭断言把失败变成 PASS。

## 实板结果记录

### 2026-09-26 FPU gate 镜像：Gate 项 3 PASS（FPU 实板首次）

`D50T_Z0_fpu_gate.img` 由用户烧入，连续两次启动均完整通过。原始日志
`artifacts/z0-gate-fpu-board-result/board-log.txt`，摘要同目录
`user-result.json`。

- 板上 `spl read: 34620 byte` 与打包 `zephyr.bin` 尺寸一致，Zephyr build
  `839728050444`。串口不回报镜像 SHA-256，故身份为「尺寸 + 操作上下文」
  关联，**不是**独立哈希证明。
- `SUITE PASS [artinchip_fpu]: pass=1, fail=0, skip=0`，12.306 / 12.307 秒，
  两次均 `PROJECT EXECUTION SUCCESSFUL`。
- 抢占校验 5003 + 5004（阈值 ≥5000/线程），自愿切换 200 次，33 槽模式比对
  干净、无 `FPU failure` 行 → FPU 上下文寄存器在真实硬件上未被破坏。
- **MIL 心跳**：`samples=11121 violations=0 mil_worst=00`（两次一致）。
  11121 次采样 ≈ 10007 次 stress 迭代 + 10 ms 监督轮询，与「心跳确实发生在
  线程上下文」自洽。第十二轮的 mcause-only 修复在 FPU 共享 + 时间片抢占这一
  最重上下文下仍未见 MIL 离开 0。
- 复现性：两次启动计数器完全相同（5 s 2047+2047、10 s 4090+4090、终值
  5003+5004），仅 uptime 差约 1 ms。该负载时序规整，适合做回归探针。
- Reset flag：第一次 `0x501` Watchdog-Reset / Command-Reboot（烧录后命令重启）；
  第二次 `0x101`，tinySPL 报 `Unknown reset reason: 2 - 1`（分类未知，不影响
  本轮判定，留作后续冷启动分类观察项）。

范围声明：单次 FPU 通过不等于长时间稳定性。本项只关闭 Gate 项 3。

### 2026-09-26 kernel gate 镜像：9/9 实板 PASS（多轮要求的第一轮）

`D50T_Z0_kernel_gate.img` 由用户烧入，一次启动即 9/9 通过。原始日志
`artifacts/z0-gate-kernel-board-result/board-log.txt`，摘要同目录
`user-result.json`。板上 `spl read: 40328 byte` 与打包 `zephyr.bin` 尺寸一致，
Zephyr build `839728050444`；串口不回报 SHA-256，身份仍为尺寸加操作上下文
关联。`SUITE PASS [artinchip_kernel]: pass=9, fail=0, skip=0`，0.529 秒，
`PROJECT EXECUTION SUCCESSFUL`，Reset flag `0x501` Command-Reboot。

MIL 心跳：六个用例各一行，`violations=0`、`mil_max=00`，样本合计
**2,101,657** 次，全部为 0。四个未采样用例（module/owned_memory/
thread_semaphore/timeout 合计 0.059 s）走阻塞而非自旋，故线程态 MIL 覆盖
套件墙钟约 89%；preflight 另在第一次阻塞等待前后钉住
MINTSTATUS=00000000。FPU 镜像的 12.3 s 采样更密，两者互补。

第十二轮修复的预测增量逐条对上（这些用例在第三至十一轮均失败）：

- 比较器确实被 ISR 重编：`armed_cmp=1756000 → exit_cmp=2156000`，差
  400000 周期，按已配置 4 MHz 换算即 100 ms = 恰 20×5 ms 到期（配置频率
  换算，不是外部时钟测量）。
- pending 被消费：`exit_clic_ip=0`、`exit_timer_ctrl=1fc00100`（尾字节 IP=0；
  第五至十一轮故障态为 IP=1 / `1fc00101`）。
- 三个自旋探针均 `count=20 reason=isr`（此前 `count=0`）。
- wfi 现在真的 trap：`stage=pre ip=1` 后 `woke=1 count=1 cmp_changed=1`
  （第九轮为 `woke=1 count=0 cmp_changed=0`，直接穿过）。
- MIL 闩锁已清：`pre_mil=00`、`exit_mil=00`、`exit_mintstatus=00000000`
  （第十一轮两点均为 `ff000000`）。
- MPIL 按修正后的 bits[23:16] 读数全为 `00`。
- 静态接线与第十轮收敛结果一致：`mtvec=40000383`、`medeleg=mideleg=0`、
  `clic_info=00600090`、`clic_cfg=00000001`。

范围声明：这是单轮通过。项 2 仍要求连续多轮，项 1 本镜像计 1 次冷启动。

### 2026-09-26 stress gate 镜像：Gate 项 4 PASS（600 s 持续压力首次）

`D50T_Z0_stress_gate.img`（`tests/z0_stress`，600 s profile）由用户烧入并跑完整
窗口。操作者回传的是**日志尾部片段**（最后两条 `Z0-STRESS-HB` +
`Z0-STRESS-SUMMARY` + 两行结论），已原样存
`artifacts/z0-gate-stress-board-result/board-log.txt`，摘要同目录
`user-result.json`。

收尾计数：`runtime_ms=601789`、`timer_isr=120360`、`fpu_a=fpu_b=90300`、
`voluntary=180602`、`timeout_wakeups=28560`、`mil_samples=209162`、
`mil_violations=0`、`mil_worst=00`、`fpu_failures=0`，结论 `result=PASS` +
`Z0-STRESS PASS` + `PROJECT EXECUTION SUCCESSFUL`。

计数器彼此自洽，不是只看一个 PASS 字：

- `mil_samples - voluntary - timeout_wakeups` 在两条心跳行都是 1、收尾为 0。
  sleeper 每次超时唤醒也采一次 MIL（`tests/z0_stress/src/main.c:215`），peer 循环
  每次先采样再计自愿切换，所以残差只可能是 1 次在途迭代——没有回绕，也没有撕裂读。
- `voluntary - 2×fpu_a = 2`：两个 peer 共用自愿计数器，残差同样是在途那一对。
- 两条心跳之间 `timer_isr +1003`、`elapsed_ms +5015`，而 1003 × 5 ms = 5015 ms
  精确对齐。
- `mtime_delta` 差值恰为 4000 ticks/ms，且两行相对 `uptime × 4 MHz` 的偏移同为
  3260 ticks（0.815 ms）——两个独立时源在整个窗口内率一致，只差一个亚毫秒常数偏移。
- `timeout_wakeups` 28560 次 / 601.789 s = 每 21.07 ms 一次，对 20 ms 睡眠即约
  1.07 ms 稳定唤醒开销，无累积漂移。

**MIL=00 是有判别力的测量**：同一个 CSR 0x346 顶字节读法在第十一轮实板的每个
失败点读到的是 `ff`（`d13x-kernel-trial.md:528`），第十二轮修复之后才恒为 `00`。
所以本项不是「位域读错导致恒零」的假绿。

四条注入分支都不可能产生这段日志：`INJECT_MIL` 预先置违例数（必以
`reason=mil_violation` 收尾）、`INJECT_TIMER` 使 `timer_isr` 停滞、`INJECT_PEER`
使 `fpu_b` 恒 0、`INJECT_FPU` 让自愿校验立刻失配；打包器又拒绝任何启用注入或
非 600 s 的构建被打成硬件镜像。据此判据 1（`inject=none`）的**实质内容**成立。

判据的**字面**缺口须同时记下：回传片段没有首行 `Z0-STRESS begin`，也没有中间约
120 条心跳，因此「全程无 >15 s 串口空窗」这一条取的是操作者陈述，本仓库没有可
独立复核的全文日志；片段里也没有 tinySPL banner，所以这次运行的板上 `spl read`
字节数与 build id 无法像 kernel/fpu 两条那样再核一次，镜像身份按「操作者指明的
文件 + 只有该应用能产生的计数集合」关联，**不是**独立哈希证明。要补齐请回传完整
`.txt`（含 begin 行与全部心跳），本文不改写成「已归档完整日志」。

范围声明：一次 601.789 s 连续窗口关闭 Gate 项 4，不构成重复性声明；
`loadable_image` 仍为 false。

### 2026-09-26 操作者口径证据：Gate 项 1 与项 2 收口

以下为 **owner-observed hardware evidence**（操作者报告），与上文逐次留档的日志
不同，须按这个口径引用：

- 同一候选镜像已完成 **≥10 次独立冷启动**，均正常完成，无挂起 / fault / 循环重启。
- 心跳版 kernel 镜像已完成 **≥5 轮连续 9/9**，每轮 `KERNEL-MILHB violations=0`。
- stress 跑完已按 runbook 第 5 步烧回 `RESTORE_original_product.img`，并确认原版
  正常启动 → 恢复路径本轮**已验证**。

这些次数的**逐次串口日志与 Reset flag 没有回流**到本仓库（此处只有 FPU 候选 2 次、
kernel 候选 1 次、stress 候选 1 次的日志），项 1 要求的「每次记录 Reset flag 与
墙钟耗时」因此是一处已知留档缺口。按操作者指示以 owner-observed 口径记为通过，
但**不得**在任何位置写成 CI / 自动化证据，也**不得**写成「本仓库日志已覆盖 10 次
启动」。遗留观察项照记：FPU 第二次启动的 Reset flag `0x101`（tinySPL 报
`Unknown reset reason: 2 - 1`）分类仍未定。

### Gate 进度

| 项 | 要求 | 状态 |
| --- | --- | --- |
| 1 重复冷启动 | 同一候选 ≥10 次独立冷启动全通过 | **PASS（owner-observed）**：操作者报告同一候选 ≥10 次独立冷启动全部正常完成；本仓库逐次留档的启动为 4 次（FPU 2、kernel 1、stress 1），逐次 Reset flag 未回流 |
| 2 kernel 9/9 多轮 | 心跳版 kernel 镜像板上连续多轮 9/9（建议 ≥5） | **PASS（owner-observed）**：操作者报告 ≥5 轮连续 9/9、每轮 `violations=0`；本仓库留档第 1 轮（9/9，2,101,657 个心跳样本 0 违例） |
| 3 FPU 实板上下文 | 1/1 + ≥5000 抢占/线程 + 200 自愿 | **PASS**（两次启动均通过，日志留档） |
| 4 ≥10 分钟 kernel+FPU stress | 组合连续 ≥10 min，MIL 全程 0 | **PASS**：`D50T_Z0_stress_gate.img` 实板 601789 ms 连续窗口，`timer_isr=120360`、`fpu_a=fpu_b=90300`、`voluntary=180602`、`timeout_wakeups=28560`、`mil_samples=209162`、`mil_violations=0`、`mil_worst=00`、`fpu_failures=0`、`result=PASS` |
| MIL 线程态保持 0 | 全部心跳 `violations=0` | 三镜像留档样本合计 **2,333,061**（kernel 2,101,657 + FPU 22,242 + stress 209,162），违例 **0** |

> **证据口径**：项 3 与项 4 的依据是本仓库留有日志的实板结果（FPU 候选 2 次启动、
> kernel 候选 1 次启动、stress 候选 1 次 601.789 s 窗口；`artifacts/` 被
> gitignore，日志随交付目录而非 Git 树走）。项 1 与项 2 的收口次数是
> **操作者报告**（owner-observed hardware evidence），逐次串口日志与 Reset flag
> 未回流，因此不得引用成「日志已覆盖 10 次启动 / 5 轮 9/9」，也不得与自动化 CI
> 证据混写。两类口径都**不是** CI 产物：CI 没有板子，Gate 项 1–4 与 Actions 运行
> 结果彼此独立。

## 软件 Gate 的 CI 主机（本轮迁移）

必需软件 Gate 现在跑在 **`ubuntu-26.04` + bash**（`.github/workflows/ci.yml`）：
主机包 `cmake ninja-build device-tree-compiler xz-utils file qemu-system-riscv`，
Python 依赖来自**新写的** `requirements-linux.lock`，SDK 由
`scripts/install_sdk.py` 按 `sha256.sum` 校验后安装，中间产物落在
`$RUNNER_TEMP/aic-{qemu,d13x,negative,sdk,stress-window}`。主 CI 里不再出现
`pwsh`、`C:/`、`$env:`、`Start-Transcript` 或 Windows 锁文件。Windows 降级为
**仅手动触发**的兼容跑（`.github/workflows/ci-windows.yml`，
`workflow_dispatch`），不参与 push/PR 必过判定。

**为什么是 26.04 而不是任务书写的 24.04（书面偏离，已实测）**：24.04 的
`qemu-system-misc` 只有 **QEMU 8.2.2**，它没有 `rv32i` 这个 CPU 模型；而固定的
Zephyr 修订版由 devicetree 自行拼出 `-cpu`
（`boards/common/qemu_riscv.board.cmake` 取 `riscv,isa-base`=`rv32i` +
`riscv,isa-extensions`（含 `zkr`）+ `pmp=on,u=on`），board.cmake 直接把它传给
QEMU，**没有命令行覆盖入口**。后果不是报错而是 28 个用例全部 `unexpected eof`、
零串口输出——run 36229599824 就是这样，诊断步实录
`qemu-system-riscv32: unable to find CPU model 'rv32i'`（run 36230313020）。
26.04 的 apt 是 **QEMU 10.2.1**，与我本机验证用的 QEMU 10.0.2 同大版本；
CI 所装的 **Linux 版** SDK 不带 `hosttools/qemu`（runner 上
`find … -iname '*qemu*'` 为空），而本机装的 Windows 版 SDK 自带 10.0.2，这正
是「本地全绿、Ubuntu 全挂」的差别所在，所以 CI 的模拟器只能来自宿主包。
**而宿主包名在 26.04 上变了**：resolute 把 RISC-V 系统模拟器从
`qemu-system-misc` 拆进独立的 `qemu-system-riscv`（`1:10.2.1+ds-1ubuntu3`，文
件清单里是 `/usr/bin/qemu-system-riscv32` 与 `-riscv64`），沿用 24.04 的包名
就会出现「包装好了、可执行文件不存在」——run 36234333782 因此停在
`Install host packages`，日志末行 `qemu-system-riscv32: command not found`
（exit 127），QEMU 10.2.1 本身已正确落盘。现在装包步骤依次是：装
`qemu-system-riscv` → `command -v qemu-system-riscv32` 断言可执行文件存在 →
`qemu-system-riscv32 -cpu help` 断言 `rv32i` 模型存在（结果分别留在
`artifacts/r1-logs/host-packages.log` 与 `qemu-cpu-models.log`），任何一步不满
足就以写明原因的状态退出，不再退化成一片 `unexpected eof`。

`requirements-linux.lock` 是 Windows 锁的逐条镜像，只去掉 Windows 专用的
`windows-curses`。它**已经在 Ubuntu runner 上真实执行过**：run 36229599824 与
36230313020 中，`pip install -r requirements-linux.lock`、`west init/update`、
`apply_patches.py`、`west manifest --validate`、lint、provenance 与主机单测
（含 stress 打包的拒绝用例）、以及按 `sha256.sum` 校验的 SDK 安装**全部通过**，
唯一失败的是 QEMU 运行 Gate，且原因在宿主模拟器而非 Python 栈（见上）。
第三次 run 36234333782（已切到 26.04）失败点更早，在 `Install host packages`
一步，原因就是上面那条包名拆分；这些步骤级结论都取自
`gh run view --json jobs` 的逐步 conclusion，不是推测。此后的 run
36234634318 全绿，这条锁才算在 Linux 上从头到尾跑通过一次；是否裁剪到最小
依赖集仍是后续单独决定，本轮没有动它。

CI 覆盖：lint、provenance、主机单测（含 stress 打包的 7 项拒绝）、QEMU 运行
Gate（5 个 `-T` 路径，含 `tests/z0_stress` 的 3 s 短 profile）、运行期负向
探针、D13x build-only Gate（4 个 `-T` 路径）与四个 candidate 构建/收集，
另加一步专门确认 stress 硬件窗口构建：`scripts/window_fit.py` 读
`zephyr.elf`/`zephyr.bin`/`.config`，断言单段 PT_LOAD 在 0x40000000、
`p_memsz <= 65536` 且 `CONFIG_AIC_Z0_STRESS_DURATION_SEC=600`。

CI **不做**的事，是设计而非遗漏：

- 不打包产品镜像。`artifacts/` 被 gitignore，runner 上没有 known-good 产品
  参考图，BASELINE 校验无从谈起；打包仍是本地/持有参考图一侧的操作。
  `window_fit.py` 因此只做结构与 profile 检查，并显式标注
  `loadable_image=false`、`hardware_validation=pending`。
- 不跑 10 分钟硬件 stress。CI 没有板子；Gate 项 1–4 的实板结果只来自操作者
  回传的日志，见下节。
- 短 QEMU profile 永远不打成硬件镜像：打包器读到 `!=600` 直接拒绝。

Ubuntu 跑的现状：`ubuntu-24.04` 上 run 36229599824 / 36230313020 失败在
`QEMU runtime gate`（`0 of 28`、零串口输出），`ubuntu-26.04` 上 run
36234333782 失败在 `Install host packages`，根因见上一节；随后 **run
36234634318 全绿**（8/8 配置、28/28 用例、D13x 4 个 build-only、证据链
verify 通过），环境数据按任务书 §21 记在本文最后。这不改变实板口径：Gate
项 1–4 仍只认操作者回传的串口日志。

## 通过判据与收尾

四项 Gate 全部 PASS、全程线程态 MIL=0、恢复原版正常 → 关闭 Z0，不再增加
诊断轮次。随后才进入 Z1（把实验性 D13x support 重构为正式 Zephyr platform
fundamentals，并独立整理 CLIC 三项 upstream candidate）。Z1 完成前不开始
CAN/display/GE/MPP。

标准候选 `loadable_image=false` 与 `hardware_validation` 状态按
`d13x-z0-validation.md` 的证据规则更新：只有对应物理测试通过后才把
`hardware_validation` 改为 verified。

### Z0 关闭时的范围声明（必须随结论一起写）

四项 Gate 全 PASS 后，Z0 关闭所**断言**的只有这些：在 D50T-2-Lite
（`d50t_2_lite/d133ecs`，D133ECS）上、以第十二轮冻结的 mcause-only CLIC
上下文修复、在实验性 0x40000000/64 KiB 产品窗口内、以 144 槽诊断 profile
构建的 kernel/fpu/stress 三个镜像，能在重复冷启动与 ≥10 分钟连续压力下
不挂起、不 fault、不循环重启，且线程态 MINTSTATUS.MIL 全程为 0。

Z0 关闭**不**断言（这些必须留在 Z1 或后续里程碑，不得被稳定性 Gate 顺带
「毕业」）：

- 默认 SRAM 布局、启动地址与产品分区归属——本 Gate 全部跑在实验窗口内。
- 定时器频率精度——`mtime` 与 uptime 互为观测，无外部时基测量；比较器周期
  只按已配置频率换算。
- 外设与总线（CAN/display/GE/MPP/DMA/PSRAM/cache 一致性）——未启用、未测。
- 已安装 loader 的 RAM 归属与手工失败恢复——仍按 H0/H1 记录为 BLOCKED/NOT_RUN。
- 96 槽默认配置的等价性——144 是控制器上报槽数，不是外设映射表扩展。
- 「产品可发布」——`loadable_image` 仍为 false，交付物是手工实验用镜像。
- upstream 就绪度——CLIC 三项 upstream candidate 属 Z1，且需人类 DCO/评审。

## Z0 关闭记录（2026-09-26）

**状态：Z0 CLOSED —— hardware validated within Z0 scope。**

关闭条件逐项对上：项 1 与项 2 以 owner-observed 口径收口（≥10 次同候选独立冷
启动、≥5 轮连续 kernel 9/9），项 3 与项 4 以本仓库留档日志收口（FPU 两次启动、
601.789 s 单次连续 stress 窗口），三镜像留档合计 **2,333,061** 个线程态 MIL 样本
**0** 违例、`fpu_failures=0`，且烧回 `RESTORE_original_product.img` 后原版确认
正常启动。按本文「通过判据与收尾」的约定，**不再增加诊断轮次**。

冻结范围随本关闭一起生效：`c0b15e9` 引入的 D13x mcause-only 上下文修复（MPIL 取
bits[23:16]）为最终形态，Z0 之内不再改 CLIC、timer frequency、mtimecmp 算法、
WFI 行为、`CLICCFG.nlbits`、SHV 与优先级；后续如需触碰，属于 Z1 的重构议题并
需重新实板验证。

软件基线与证据标识：

| 字段 | 值 |
| --- | --- |
| 本仓库 HEAD（软件基线） | `fee21ae9790ca51ca49282a8a1eaee083b976ffc` |
| Z0 kernel baseline | `c0b15e9` + `4442a91` |
| Zephyr 固定源 | `839728050444f90d06870b5fc9bbbda106d91459`（dirty：补丁改的三个 CLIC 文件） |
| Linux 必需软件 Gate | run **36235471896**（全 18 步 success），环境记录见下一节 run 36234634318 |
| kernel gate 镜像 | `D50T_Z0_kernel_gate.img` `bd76a8bb…`（BIN `14549f37…`，40328 B） |
| fpu gate 镜像 | `D50T_Z0_fpu_gate.img` `1f322dc1…`（BIN `a144fbb3…`，34620 B） |
| stress gate 镜像 | `D50T_Z0_stress_gate.img` `eb06085f…`（BIN `c0d7a411…`，30816 B，RAM 44368/65536） |
| baseline marker | 附注标签 `d13x-z0-validated`，含以上 HEAD/Zephyr/CI/镜像 SHA 与硬件摘要 |

**未做的事**：没有创建 GitHub Release，也没有发布任何制品——按仓库规则
release 需人工批准，本轮只落 tag 与本文记录。三项 `verification.json` 里的
`loadable_image=false` 与 `hardware_validation` 字段一字未改（那三个文件已被
`SHA256SUMS.txt` 钉住，改动会破坏交付一致性）；实板结论只写进本文与
`d13x-handoff.yml` 的 observed 条目。

关闭 Z0 之后进入 Z1：把实验性 D13x support 重构为正式 Zephyr platform
fundamentals，并独立整理 CLIC 三项 upstream candidate。CAN / display / GE / MPP
在 Z1 完成前不开始。

## 首次全绿的 Ubuntu run（任务书 §21 环境记录）

Run **36234634318**（workflow `P0 and D13x software gates`，event `push`，
head `163269d2e331aa306d05cb3a907ad8a74a186cea`）自 2026-09-26T10:03:43Z
起约 6 分钟完成，**job conclusion = success**，从 `Set up job` 到
`Complete job` 的每一步结论都是 success——这是必需软件 Gate 第一次在 Linux
上全绿。此前三次失败（36229599824、36230313020、36234333782）按 run 号记录
在上文，不因为这次绿了就抹掉。

| 项 | runner 实测值 |
| --- | --- |
| 镜像 | `ubuntu-26.04`，Image `20260920.143.1`，Provisioner `20260828.587`，runner `2.337.0` |
| OS | Ubuntu 26.04.1；`platform.platform()` = `Linux-7.0.0-1012-azure-x86_64-with-glibc2.43` |
| QEMU | `QEMU emulator version 10.2.1 (Debian 1:10.2.1+ds-1ubuntu3.2)`，包名 `qemu-system-riscv` |
| 主机构建工具 | cmake `4.4.3`、DTC `1.7.2` |
| Python | `3.13.15`（`requirements-linux.lock` 安装通过） |
| 交叉工具链 | `riscv64-zephyr-elf-gcc (Zephyr SDK 1.0.1) 14.3.0`，装在 `/home/runner/work/_temp/aic-sdk/zephyr-sdk-1.0.1` |
| Zephyr 源 | HEAD `839728050444f90d06870b5fc9bbbda106d91459`，dirty=true（正是补丁改动的三个 CLIC 文件），`environment.py` 报告 `status: PASS` |
| 本仓库源 | HEAD 等于上面的 run head，dirty=false |

同一 run 内各 Gate 的结果：

- QEMU 运行 Gate：`8 test scenarios (8 configurations) selected`，0 过滤，
  **8/8 配置通过、28/28 用例通过、0 warning，用时 80.48 s**。
- 运行期负向探针：通过；输出含 `claims_pass: false` 的
  `peer_preemption_missed` 场景与 `hardware_validation: "pending"`。
- D13x build-only Gate：`5 selected, 1 filtered`，**4 built (not run)、
  0 failed、0 errored，用时 34.97 s**；按既定口径不计为任何运行通过。
- stress 硬件窗口步：`window_fit.py` **status = PASS**，
  `window_start = entry = 0x40000000`、`p_filesz = 30832`、
  `p_memsz = 44384`、`ram_utilization_percent = 67.72`、
  `CONFIG_AIC_Z0_STRESS_DURATION_SEC = 600`、`loadable_image = false`；
  CI 那次构建的 ELF/BIN 为 `1a3a8ee5…` / `bd38641a…`。
- 证据链：stage → upload → download → `evidence.py verify` 全部通过，
  `status: PASS`、`software_audit: pass`、165 个文件的清单与 SHA-256 一致；
  下载回的 `software-evidence.zip` 为 1339156 B，
  sha256 `e9c5a927dd12ab24cc174a1eae31c1e0d5417da192c40b5c3148c66183655407`。

**必须同时记下的差异**：同一份源码在 CI 上的 stress 窗口镜像是 44384 B /
67.72%，本机固定并交付的那次是 44368 B / 67.70%；默认 SRAM 的 stress
candidate 也一样，43808 B vs 43792 B，差值同为 16 B。本轮**未定位**该差值
的成因（宿主 cmake/DTC 版本与本机不同只是候选，没有证据）。因此前文
「换目录重建 BIN 逐字节相同」的结论**只对本机那条命令成立**，不要读成
「任何主机重建都逐字节相同」；CI 本来也不做这个比对——`artifacts/` 被忽略，
runner 上没有 known-good 参考图。要在 CI 断言跨主机字节一致，需要先固定
宿主工具版本并解释这 16 B，属 Z1 事项。

这次全绿改变的是**软件 Gate 的主机状态**，不改变实板口径：Gate 项 1–4 仍只看
操作者回传的串口日志。交付头 `fee21ae9790ca51ca49282a8a1eaee083b976ffc`（在
`163269d` 之后只含文档改动）自身的 run **36235471896** 同样全绿，从 `Set up job`
到 `Complete job` 共 18 步全部 `success`；上表的环境数据取自首次全绿的那次
（36234634318），两者主机与工具版本相同。实板侧其后已收口，见「Z0 关闭记录」。
