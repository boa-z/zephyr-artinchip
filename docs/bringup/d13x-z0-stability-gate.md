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
```

`--allow-unpinned` 会把计算出的 ELF/BIN SHA-256 写进 `verification.json`。
评审通过后把哈希固定进 `package_gate_trial.py` 的 `PINNED[app]` 字典（或每次
传 `--expect-elf-sha`/`--expect-bin-sha`），此后任何被篡改的探针都会在打包阶段
被拒（exit 1）。这与 kernel 第十二轮两段式固定（提交 49c4f5c）的先例一致。
固定项**按 `--app` 分别索引**是刻意的：早先共用一对全局常量时，一旦 pin 了
FPU 的哈希，合法的 kernel 构建会被误拒。

打包器结构校验（kernel/fpu 共用）：单一 PT_LOAD、paddr/vaddr=0x40000000、
`0 < p_filesz <= p_memsz <= 65536`、重建 BIN 与 zephyr.bin 逐字节相同、
入口 `__start`、`_irq_vector_table=144*4`、`_sw_isr_table=144*8`。

> **FPU 窗口占用（已实测）**：fpu 的栈需求大于 kernel（MAIN 2048 + TEST_EXTRA
> 2048 + 两条 2048 线程栈 + FPU 上下文），目标构建实测 RAM 50624 B / 64 KiB
> （77.25%），**未**溢出。kernel gate 为 53408 B（81.49%）。若后续改动使任一
> 构建超出，打包器的 `p_memsz <= 65536` 检查会**显式失败**（不会静默产出坏
> 镜像）；届时不要放宽窗口或改硬件参数，先回报实测 RAM 占用再决定是否调整
> 测试侧栈配置（属测试侧，不属 CLIC 修复逻辑）。

## 已构建产物（2026-09-26）

两个 gate 镜像已按上述命令构建并打包，均在实验窗口内：

| 项 | kernel gate | fpu gate |
| --- | --- | --- |
| 目录 | `artifacts/z0-gate-kernel-delivery` | `artifacts/z0-gate-fpu-delivery` |
| 镜像 | `D50T_Z0_kernel_gate.img` | `D50T_Z0_fpu_gate.img` |
| 镜像 SHA-256 | `bd76a8bb7eafd22fda4d2567c7c9417994af5efc2785318ecc9d90196f02597f` | `1f322dc1cba4e3e187555d18f429da057ce569069d8b38d2a424e9cb99467bc1` |
| ELF SHA-256 | `1ab0896753d332e0d6f1075a98512b1b068a161e1bb31e564d1b27507a2cbbe2` | `04eba2449e0a0ee75fcc68f0a1ded1858848effb1c04822a6f914cefb0cc20ea` |
| BIN SHA-256 | `14549f37cc4df97ed54c1281c0125f4cb60e904fbf00ca670ff4839488a7ebe3` | `a144fbb3be29610c7ed896b6adf391943755e971d4d2d6f9ede8bcbea05735dd` |
| RAM / payload | 53408 B（81.49%）/ 40328 B | 50624 B（77.25%）/ 34620 B |
| 状态 | `OFFLINE_VERIFIED`（已固定） | `OFFLINE_VERIFIED`（已固定） |

配套证据：QEMU qemu_riscv32 全量回归 **7/7 场景、27/27 用例通过、无警告**
（bringup/kernel/fpu/clic，`qemu-twister.json`）；复现性——同一命令增量重建
后 ELF/BIN 与打包时逐字节相同；三项篡改负检查均被拒（exit 1）：固定 BIN 被
改、未固定但 BIN 与 ELF 重建不一致、参考镜像非 BASELINE。

哈希**已固定**进 `scripts/package_gate_trial.py` 的 `PINNED['kernel']` 与
`PINNED['fpu']`（两镜像均已实板 PASS）。用固定后的打包器重打两个 app，产出
镜像与交付镜像**逐字节相同**；三项负检查均被拒（exit 1）：篡改 kernel BIN、
篡改 fpu BIN、以及把 kernel 构建当作 `--app fpu` 传入。初次未固定的记录保留为
各交付目录的 `verification-initial-unpinned.json`，未被覆盖。每个目录另含
`READ_ME_FIRST.md`（操作与判读）、`RESTORE_original_product.img`、
`verification.json`、`source-inventory.json`（记录 `c0b15e9`+`4442a91`
基线、交付提交、脏状态与源码哈希）、`SHA256SUMS.txt`、`zephyr.elf/bin/map/dts`、
`product-window.conf/overlay` 与 `target-build.log`。

## 烧录、观察与恢复

1. 用已验证的 AiBurn、先 Reset 再 Boot 流程烧入 gate 镜像。
2. COM11 / 115200 保存**完整**串口日志；烧完仅按 Reset 启动。
3. kernel 预期：`KERNEL-PREFLIGHT begin irq_slots=144` → PASS，9 项用例
   全 PASS、`SUITE PASS (pass=9)`、`PROJECT EXECUTION SUCCESSFUL`，且每条
   `KERNEL-MILHB ... violations=0`。fpu 预期：`FPU-MILHB ... violations=0`
   且 `counts` 达标、`PROJECT EXECUTION SUCCESSFUL`。
4. 只到达 banner/begin、或 30 s（kernel）/ 180 s（fpu）内无完整结果、或
   出现异常/循环重启：保留日志、复位并烧回原版，不把无输出当成功。
5. 每个 Gate 项完成后烧回包内 `RESTORE_original_product.img` 并确认恢复
   正常，再进行下一项。

## 失败证据留存（任一 Gate 项失败即触发）

- 完整原始串口日志（不截断、不改写），存
  `artifacts/z0-gate-<kernel|fpu>-board-result/board-log.txt`。
- 候选镜像 SHA-256（`D50T_Z0_<app>_gate.img`）与 `verification.json`
  中记录的 ELF/BIN SHA-256、Zephyr build id。
- 摘要 `user-result.json`：失败用例、`KERNEL-MILHB`/`FPU-MILHB` 行、
  Reset flag、墙钟耗时、失败点 main.c 行号。
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

### Gate 进度

| 项 | 要求 | 状态 |
| --- | --- | --- |
| 1 重复冷启动 | 同一候选 ≥10 次独立冷启动全通过 | 进行中（FPU 候选 2 次、kernel 候选 1 次，均通过） |
| 2 kernel 9/9 多轮 | 心跳版 kernel 镜像板上连续多轮 9/9（建议 ≥5） | 进行中：第 1 轮 **PASS**（9/9，2.1 M 心跳样本 0 违例） |
| 3 FPU 实板上下文 | 1/1 + ≥5000 抢占/线程 + 200 自愿 | **PASS**（两次启动均通过） |
| 4 ≥10 分钟 kernel+FPU stress | 组合连续 ≥10 min，MIL 全程 0 | NOT_RUN（kernel 单轮 0.529 s、FPU 单轮 12.3 s） |
| MIL 线程态保持 0 | 全部心跳 `violations=0` | 两镜像已观测合计 2,123,899 个样本全部为 0 |

## 通过判据与收尾

四项 Gate 全部 PASS、全程线程态 MIL=0、恢复原版正常 → 关闭 Z0，不再增加
诊断轮次。随后才进入 Z1（把实验性 D13x support 重构为正式 Zephyr platform
fundamentals，并独立整理 CLIC 三项 upstream candidate）。Z1 完成前不开始
CAN/display/GE/MPP。

标准候选 `loadable_image=false` 与 `hardware_validation` 状态按
`d13x-z0-validation.md` 的证据规则更新：只有对应物理测试通过后才把
`hardware_validation` 改为 verified。
