# Z0 内核与 tick 实板实验

前一轮已到达实验地址窗口内的 Zephyr main，并确认可恢复原产品。
本轮运行现有 artinchip_kernel 的五项 ztest：模块、线程/信号量、超时、
定时器抢占和测试自身拥有的内存。不启用产品外设，不做全内存扫描。

## 中断槽核查与修改

SDK aic_soc.h 的外设枚举止于 CIR_IRQn=95，MAX_IRQn=96，这解释了默认
配置的来源。实测 CLICINFO=0x00600090 按 SDK/Zephyr 位定义报告 144
槽和 3 个控制位。144 是控制器槽数，不是新增外设映射。
实验开关 CONFIG_ARTINCHIP_D13X_DIAGNOSTIC_144_IRQS 让 NUM_IRQS=144，
使当前驱动的初始化循环覆盖所报告槽位，并扩展默认向量/软件处理表。
板级默认仍为 96；不会仅凭这次实验将所有平台改成 144。

首次直接在 .conf 写 CONFIG_NUM_IRQS=144 被隐藏 Kconfig 选项忽略，
产生警告且实际表仍为 96，该构建未交付。修正为有提示的显式实验开关后，
最终 .config 为 144；ELF 的 _irq_vector_table=576 字节，_sw_isr_table=1152
字节，分别等于 144*4 与 144*8。打包器重新校验这些尺寸。

## tick 故障诊断

原抢占测试使用 uptime 超时，在 tick 失效时可能一直自旋。现在以
k_cycle_get_32 的无符号差值及独立迭代上限约束等待；先运行相同机制的
KERNEL-PREFLIGHT，再执行五项测试。工作线程先睡眠，只有定时中断使其
唤醒并抢占忙等线程才能通过。失败时中止工作线程并交给 ztest 报错。

周期预算按配置频率换算，不是外部时钟测量。循环不能保护停滞的 MMIO；
后续阻塞测试仍可能在新的硬件故障下停止输出，所以本轮也需要保存完整
日志并设置人工观察时限。通过不等于定时精度或长期稳定性验收。

## 验证与交付

QEMU qemu_riscv32：Twister 1/1 场景、5/5 用例通过，无警告；报告位于
C:/aic-z0-kernel-qemu-v1。该结果验证测试逻辑，不验证 E907 CLIC。
D13x 目标构建：C:/aic-z0-kernel-window-v2，45728 字节内存，范围
[0x40000000, 0x4000b2a0)，仍在原实验 64 KiB 窗口内。文件字节34236，
入口为 __start=0x40000000；不包含上一轮 H0-PROBE 入口快照。

固定 ELF/BIN profile 的 scripts/package_kernel_trial.py 验证 FIT、地址、
入口、两张中断表和所有非 OS 字节。原版 PBP、target SPL、updater 与
分区布局保持不变。源码配置及哈希随实验包保存；未以脏工作区构建冒充
标准 clean-source release receipt。首轮物理测试已完成，结果为 FAIL，详见下节。

目录：artifacts/z0-kernel-144irq-delivery。
镜像：D50T_Z0_kernel_144irq.img，SHA-256：

```text
d1828558837f561edaba52dbd371967e358cb7e6fbcfdeb529142c0ad0eb2520
```

## 操作

1. 使用已验证的 AiBurn 与先 Reset 再 Boot 流程烧入测试镜像。
2. COM11 / 115200 保存完整串口日志，烧完仅按 Reset 启动。
3. 预期看到 KERNEL-PREFLIGHT begin irq_slots=144、KERNEL-PREFLIGHT PASS，
   五项用例均 PASS、SUITE PASS（pass=5，fail=0，skip=0），以及
   PROJECT EXECUTION SUCCESSFUL。只到达 begin 或只打印 boot banner 不算通过。
4. 若 30 秒内没有完整结果，或出现异常/循环重启，保留日志并恢复原版；
   不将无输出当作成功。完成后烧回包内 RESTORE_original_product.img。
5. 回传完整结果及恢复是否正常。本轮没有 UI，也不要求屏幕变化。

manual_experiment_ready=true；hardware_validation=pending；标准候选的
loadable_image=false 继续保留。默认 SRAM、全中断源、FPU 上下文、频率精度
和长时间稳定性仍不由本轮自动关闭。

## 首轮实板结果：失败，恢复成功

用户回传日志对应 34236 字节 payload，Zephyr build 839728050444。
镜像身份由本轮操作上下文关联；串口未回报镜像 SHA-256，不视为独立哈希证明。
预检 irq_slots=144，PASS，uptime_delta_ms=25，cycle_delta=96849。
五项测试中 module、owned_memory、thread_semaphore、timeout 通过；
timer_preemption 在 main.c:106 因 woke=false 失败，耗时 1.017 秒。
套件 pass=4、fail=1、skip=0，最终 PROJECT EXECUTION FAILED。
用户确认烧回 RESTORE_original_product.img 恢复正常。

本结果证明启动和所列四项测试在本次运行通过，不满足本轮内核验收。
预检成功与后续抢占失败并存，不能断言 tick 从未工作，也不能据此确认
持续中断或抢占可靠。默认 SRAM、全中断源及长期稳定性边界不变。

源码核查：ztest 用例线程优先级为 2，延时 worker 为 1；setup 与用例
运行上下文不同，setup 成功不代替用例抢占验证。没有证据支持修改优先级
或延长等待预算来掩盖本次失败。

## 第二轮诊断：保留失败判定

新增 KERNEL-POLL（预检和抢占测试各一条）：reason 为 worker、cycles 或
iterations；phase=0 表示 worker 尚未记录启动，1 表示已到达 sleep 前，
2 表示 sleep 已返回。woke 是观察到完成标记的采样值。
记录当前优先级、cycle_delta 和 tick_delta，D13x 另记录等待前后
mstatus/mcause。先采样、后打印、最后进行失败清理；无循环内串口打印。
这些是分时采样，不是原子的硬件快照；mcause 可能是历史 trap 值，
uptime 可包含计数器推算的 elapsed，tick_delta 不能单独证明中断次数。
该版本用于缩小根因范围，尚不宣称修复。等待预算和原五项测试保持不变。

第二轮产物：artifacts/z0-kernel-poll-delivery/D50T_Z0_kernel_poll_diag.img。
SHA-256: df2dc6f3a32bff22a91ea0ffa2fc62bf8128519c0c1825df998968b71ffd20b5。
目标构建 C:/aic-z0-kernel-window-v3：文件 34700 字节，RAM 46208/65536；
QEMU C:/aic-z0-kernel-qemu-v2：5/5 通过。三项篡改拒绝检查通过。
使用同样的手动烧录、COM11/115200、30 秒观察和恢复流程；回传完整日志，
特别保留两组 KERNEL-POLL/KERNEL-CSR。第一轮包保持不变，勿与第二轮混用。
打包器当前固定第二轮 ELF/BIN；首轮脚本可在提交 677e289 找到。
第二轮 hardware_validation=pending，第一轮明确为 FAIL。

## 第二轮实板结果：失败（诊断收敛，未修复）

用户回传日志对应 34700 字节 payload（与 zephyr.bin 一致），Zephyr build
839728050444。镜像身份由本轮操作上下文关联；串口未回报镜像 SHA-256，
不视为独立哈希证明。原始日志见
artifacts/z0-kernel-poll-board-result/board-log.txt，摘要见同目录
user-result.json。

- KERNEL-PREFLIGHT：begin irq_slots=144，PASS，uptime_delta_ms=42，
  cycle_delta=164863。POLL：reason=worker，woke=1，phase=2，priority=0，
  tick_delta=21，cycle_delta=83614。CSR：mstatus 前后均为 0x88（MIE 置位），
  mcause 由 0x0800000b 变为 0x88000007。
- test_module、test_owned_memory、test_thread_semaphore、test_timeout 通过，
  耗时分别为 0.001/0.011/0.021/0.026 秒。
- test_timer_preemption 在 main.c:153 因 woke=false 失败，耗时 1.035 秒。
  POLL：reason=cycles，woke=0，phase=1，priority=2，tick_delta=1000，
  cycle_delta=4000000（恰为 4 MHz 下 1000 ms 预算）。CSR 前后无变化，
  mstatus=0x88，mcause=0x0800000b。
- 套件 pass=4、fail=1、skip=0，最终 PROJECT EXECUTION FAILED。

分析结论（以本日志为界，不外推硬件参数）：

1. 阻塞等待路径的定时器可用：semaphore/timeout 睡眠均按时返回，mtime 在
   推进，超时到期能唤醒阻塞的等待者。
2. 自旋抢占路径失败：worker 已进入 k_sleep（phase=1）但 1 秒内未返回；
   tick_delta=1000 是 tickless 下由周期推算的 elapsed，不是中断计数证明；
   mcause 采样是 last-trap 提示（0xb 为 ecall 上下文切换痕迹），不是原子
   快照，不能单独证明中断有无。
3. 未判定的根因分支：自旋期间定时器 ISR 是否投递 vs ISR 投递后线程唤醒/
   抢占是否发生。本轮诊断无法区分二者；不延长等待预算、不修改优先级来
   掩盖失败。下一轮以 ISR 侧计数（k_timer 到期回调）与自旋等待分离两个
   分支，仍使用公开内核 API，不改上游驱动。

## 第三轮诊断：分离 ISR 投递与线程抢占（待实板）

新增 `test_timer_isr_delivery`（提交 e7fdbcc，原五项测试保持不动）：
自旋期间只挂载 5 ms 周期 k_timer，到期回调在时钟 ISR 上下文计数，
打印 `KERNEL-ISRPROBE schema=1 reason=... count=...`。count>=20 证明
自旋中 ISR 可投递（偏向调度分支），count=0 指向投递/arm 分支。
证据清单增至 6 用例（提交含 scripts/evidence.py 与主机测试同步）。

QEMU qemu_riscv32：Twister 1/1 场景、6/6 用例通过，无警告；报告位于
C:/tmp/aic-qemu-isr。ISRPROBE 行：
`reason=isr count=20 priority=2 tick_delta=21 cycle_delta=2090821`。
该结果验证诊断逻辑，不验证 E907 CLIC。
D13x 目标构建：C:/aic-z0-kernel-window-v4（干净树重建，ELF/BIN 哈希
与脏树构建一致，可复现），文件 35840 字节，RAM 47344/65536，范围
[0x40000000, 0x4000b8b0)，仍在原实验 64 KiB 窗口内。入口
__start=0x40000000；_irq_vector_table=576 字节，_sw_isr_table=1152
字节（144 槽）。打包器按第三轮 ELF/BIN 固定哈希验证（提交 2eb2c44），
篡改 BIN 负检查被拒绝（exit 1）。

第三轮产物：artifacts/z0-kernel-isr-delivery/D50T_Z0_kernel_isr_diag.img。
SHA-256: ec5b1b77cb436af41cd3ba1378cbd543c96b4f74409881993ff4f41165e39687。
使用同样的手动烧录、COM11/115200、30 秒观察和恢复流程；回传完整日志，
特别保留 KERNEL-ISRPROBE 行。判读规则见包内 history-and-details.md。
第三轮 hardware_validation=pending，第二轮明确为 FAIL。

## 第三轮实板结果：失败，分支 A 落定

用户回传日志对应 35840 字节 payload（与 zephyr.bin 一致），Zephyr build
839728050444，本轮 Reset flag 为 0x501 Watchdog-Reset Command-Reboot
（命令重启，无崩溃指征）。镜像身份由操作上下文关联；串口未回报镜像
SHA-256。原始日志见 artifacts/z0-kernel-isr-board-result/board-log.txt。

- Preflight 与四项阻塞测试通过，耗时与前两轮一致（0.001/0.011/0.021/
  0.026 秒）；mstatus=0x88，preflight mcause 仍终结于 timer（0x88000007）。
- test_timer_isr_delivery 在 main.c:186 失败：
  `reason=cycles count=0 tick_delta=1000 cycle_delta=4000005`。
  仅挂载 5 ms k_timer 的 1 秒自旋中，ISR 上下文到期计数保持为 0。
- test_timer_preemption 复现失败，签名与第二轮完全一致（phase=1，
  整预算 cycle_delta=4000000）。
- 套件 pass=4、fail=2、skip=0，共 6 项，耗时 2.119 秒。

分析结论：分支 A 成立——非让出式自旋期间超时 ISR（到期回调在此时钟
ISR 上下文执行）一次都未运行，而阻塞等待者仍能被按时唤醒。由此排除
“投递后线程唤醒/调度”分支和全局 MIE 问题；未继续分离的是比较器
“已挂载但未投递” vs “从未断言” vs “内核根本未挂载”。

## 第四轮诊断：比较器与 pending 采样（待实板）

在 test_timer_isr_delivery 内新增 KERNEL-TICKDBG 行，报告原始值，
不做硬件语义断言：k_timer_start 后的 armed_mtime/armed_cmp，
自旋退出时（k_timer_stop 之前）的 exit_mtime/exit_cmp/exit_mip/
exit_mie/exit_irqen。QEMU 下该结构填充为零，不影响 6/6 判定。
判读：exit_mtime>=exit_cmp 且 count=0 为“已挂载但未投递/未断言”；
exit_mtime<exit_cmp 为“内核未挂载”。mip/mie 按标准机时中断位对照，
CLIC 模式下的最终解释以硬件手册为准。

## 第四轮交付（待实板）

产物：artifacts/z0-kernel-tickdbg-delivery/D50T_Z0_kernel_tickdbg_diag.img。
SHA-256: b70fbd0442f845b7ff0b6259f7eb3b127c2818ea7dbd3757c1743942e54144a7。
QEMU 6/6（C:/tmp/aic-qemu-tickdbg）；D13x 目标构建
C:/aic-z0-kernel-window-v5（干净树），文件 36224 字节，RAM 47728/65536；
打包器按第四轮 ELF/BIN 固定哈希验证（提交 68d1ede），篡改负检查拒绝。
使用同样的手动烧录、COM11/115200、30 秒观察和恢复流程；回传完整日志，
特别保留 KERNEL-TICKDBG 行。第四轮 hardware_validation=pending。

## 第四轮实板结果：失败，挂载正确但比较器原地不动

用户回传日志对应 36224 字节 payload（与 zephyr.bin 一致），Zephyr build
839728050444。SPL 头部截断，身份以 payload 尺寸加操作上下文关联；串口未
回报镜像 SHA-256。原始日志见
artifacts/z0-kernel-tickdbg-board-result/board-log.txt，摘要见同目录
user-result.json。恢复待用户确认。

- Preflight 与四项阻塞测试通过，耗时与前轮一致；mstatus=0x88。
- test_timer_isr_delivery 在 main.c:236 失败：
  `reason=cycles count=0 tick_delta=1000 cycle_delta=4000006`，且
  `armed_mtime=1680301 armed_cmp=1688000 exit_mtime=5680289
  exit_cmp=1688000 exit_mip=00000000 exit_mie=00000000 exit_irqen=1`。
- test_timer_preemption 在 main.c:253 复现失败，签名与上轮一致。

分析结论（板上实测，不外推硬件语义）：

1. 内核挂载正确：armed_cmp 大于 armed_mtime，差值 7699 周期合理。
2. 计数器以配置的 4 MHz 速率推进，1 秒内超出比较器约 400 万周期；
   比较器数值原地不动（无 ISR 改写），零到期、mcause 不变故零 trap。
3. 同一固件、同一地址、同一使能下，线程一旦阻塞定时器 ISR 即到：
   差异是动态的“自旋 vs 阻塞”，不是静态配置。
4. CLIC 使能位读数为开（irqen=1），MIE 置位；mip/mie 读零在 CLIC
   模式下不作语义断言，仅作原始记录。

## 第五轮诊断：yield 行为位与 CLIC pending 直读（待实板）

- 新增 `test_timer_spin_yield`：同样挂 5 ms k_timer，自旋每 1000 次
  k_yield（进内核切换路径，永不阻塞），打印 KERNEL-SPINPROBE。
  若其通过而纯自旋失败，指向切换路径的重挂/解蔽；若同样失败，
  剩余差异为阻塞/wfi。无裸 wfi，故无挂死风险。
- KERNEL-TICKDBG 追加 exit_clic_ip/exit_clic_ie/exit_clic_mth：
  定时器 IRQ 的 CLIC pending/m使能字节与阈值字直读，版图与已交付
  驱动头一致。IP=1 且 count=0 为“CLIC 已见 pending 但未 trap”；
  IP=0 为“比较器输出未到达 CLIC”。
- 用例清单增至 7 项（evidence.py 与主机测试同步）；QEMU 下采样
  填零、不影响判定。

## 第五轮交付（待实板）

产物：artifacts/z0-kernel-r5-delivery/D50T_Z0_kernel_r5_diag.img。
SHA-256: f24e4fb117c2abbeeeaf121c7518b9dddadf18f8daaf4729da98fc1b9a67a5f9。
QEMU 7/7（C:/tmp/aic-qemu-r5）；D13x 目标构建
C:/aic-z0-kernel-window-v6（干净树），文件 36824 字节，RAM 48352/65536；
打包器按第五轮 ELF/BIN 固定哈希验证（提交 50174f9），篡改负检查拒绝。
使用同样的手动烧录、COM11/115200、30 秒观察和恢复流程；回传完整日志，
特别保留 KERNEL-SPINPROBE 行与扩展的 KERNEL-TICKDBG 行。
第五轮 hardware_validation=pending。

## 第五轮实板结果：失败，CLIC 已见 pending 但运行线程中零 trap

用户回传日志对应 36824 字节 payload（与 zephyr.bin 一致），Zephyr build
839728050444。原始日志见 artifacts/z0-kernel-r5-board-result/board-log.txt，
摘要见同目录 user-result.json（注：粘贴的 summary 行称 fail=2，但分项列出
3 个 FAIL，4 pass + 3 fail = 7 项计 57.14%，以分项为准）。恢复待确认。

- Preflight 与四项阻塞测试通过，耗时与前轮一致。
- test_timer_isr_delivery 在 main.c:250 失败：count=0，且
  `exit_clic_ip=1 exit_clic_ie=1 exit_clic_mth=00000000`，
  exit_cmp 原地不动（1688000），mcause 不变。
- test_timer_spin_yield 在 main.c:291 失败：同样 count=0。
- test_timer_preemption 在 main.c:308 复现失败，签名一致。

分析结论：CLIC 已观察到定时器 pending（IP=1），使能开、阈值 0、
MIE 置位，但运行线程期间零 trap；线程一旦阻塞即恢复。
另经代码核查（kernel/include/kswap.h do_swap 仅在新老线程不同时
切换），单 prio-2 线程的 k_yield 不产生实质上下文切换，故第五轮
yield 测试只验证了“进调度器代码”，未验证切换路径，不单独作为
切换无关的证据。

## 第六轮诊断：同优先级对等切换与阈值 CSR（待实板）

- 新增 `test_timer_spin_switch`：同优先级对等自旋线程，测试线程每
  1000 次 k_yield，强制走 ecall 真实切换（timeslice 重置与重挂载
  评估随之运行），双双永不阻塞，打印 KERNEL-SPINPROBE mode=switch。
  通过则指向切换路径，不通过则剩余差异为阻塞/wfi。
- KERNEL-TICKDBG 追加 exit_mcause 与 exit_mintthresh（CSR 0x347，
  编号见已交付驱动头 intc_clic.h）：若 CSR 阈值非零而 MMIO MTH 为
  零，则存在双阈值门控嫌疑。
- 用例清单增至 8 项（evidence.py 与主机测试同步）；QEMU 下采样
  填零、不影响判定。

## 第六轮交付（待实板）

产物：artifacts/z0-kernel-r6-delivery/D50T_Z0_kernel_r6_diag.img。
SHA-256: 20b5a4d41029263702eedb21ea27094161beaa552cea36ab84d6cf57f2b3661e。
QEMU 8/8（C:/tmp/aic-qemu-r6b）；D13x 目标构建
C:/aic-z0-kernel-window-v7（干净树），文件 37672 字节，RAM 50720/65536；
打包器按第六轮 ELF/BIN 固定哈希验证（提交 c6eac09），篡改负检查拒绝。
使用同样的手动烧录、COM11/115200、30 秒观察和恢复流程；回传完整日志，
特别保留 KERNEL-SPINPROBE mode=switch 行与扩展的 KERNEL-TICKDBG 行
（含 exit_mcause/exit_mintthresh）。
第六轮 hardware_validation=pending。

## 第六轮实板结果：探针 CSR 触发异常，双阈值假设被证伪

用户回传日志对应第六轮镜像（Zephyr build 839728050444）。
test_timer_isr_delivery 在打印任何诊断行之前触发 CPU 异常，
套件停机；后续用例均未运行。原始日志见
artifacts/z0-kernel-r6-board-result/board-log.txt，摘要见同目录
user-result.json。板子需要复位并烧回原版镜像。

- `mcause: 2, Illegal instruction`，`mtval: 347029f3`，mepc=0x400010dc，
  当前线程 test_timer_isr_delivery。a3/a5 分别为 mtime/mtimecmp 的
  MMIO 地址，确认异常发生在探针采样上下文。
- mtval 译码：CSRRS，rd=x19，rs1=x0，CSR=0x347，SYSTEM 操作码——
  对 CSR mintthresh 的纯读。固件中唯一的 0x347 访问即新增探针
  （驱动只用 MMIO MTH），故 fault 点就是该探针。

分析结论：该 E907 上 CSR mintthresh（0x347）不可读，纯读即
Illegal instruction。阈值路径只有 MMIO MTH（读数恒 0），双阈值
门控假设被证伪；同时印证了 legacy-MMIO CLIC 版图方向（该核不走
CSR 间接访问）。标准 CSR（mip/mie/mcause/mstatus）与 MMIO 读数
在前五轮均正常，仅 0x347 fault。

## 第七轮诊断：去掉 fault 探针，保留切换测试（待实板）

- 删除 mintthresh 裸 CSR 读及对应字段/打印；保留 mcause 与其余
  采样。用例清单保持 8 项不变。
- test_timer_spin_switch（同优先级对等切换）上轮未及运行，仍是
  待验证项：通过则指向切换路径，不通过则剩余差异为阻塞/wfi。
