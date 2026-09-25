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
标准 clean-source release receipt。物理测试尚未进行。

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
