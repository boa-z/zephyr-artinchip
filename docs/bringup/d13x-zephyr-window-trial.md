# 原产品地址窗口内的 Zephyr 首次启动实验

## 实验边界

前置证据是原产品传输/恢复与 440 字节独立跳转探针执行/恢复。此次将
Zephyr handoff_probe 链接在已测试区域内，不沿用未验证的 0x30080000。
`samples/handoff_probe/product-window.overlay` 仅为显式启用的实验配置；
板级默认配置和标准 SRAM candidate 的门槛不变。

选择 [0x40000000, 0x40010000) 作为软件分配预算，不初始化 PSRAM，
不以此声明整片存储器容量。实际唯一 PT_LOAD 为
[0x40000000, 0x40006350)，其中文件字节 19228，总内存 25424 字节，
入口 aic_handoff_entry=0x40000dd8。BSS/noinit/栈均在该窗口内。
与已知原版 loader 静态区和默认堆无数值重叠；并非完整物理别名证明。

本轮会执行 Zephyr 的 soc_reset_hook、CLIC、timer、UART 和内核初始化。
这些路径尚无本板运行证据，不能用独立汇编探针成功替代本轮验证。
实验只观察能否到达 main 并输出快照，不验证定时精度、长期稳定性、
FPU 完整上下文或其他外设。未启用产品 UI、CAN、网络、文件系统等。

## 离线结果

构建目录 `C:/aic-h0-product-window-probe`，日志
`artifacts/h0-product-window-build.log`。显式传入 overlay 的绝对路径和
既有 Zephyr SDK；引用树保持源码只读，缓存位于独立目录。
首次调用因 PowerShell 参数拆分失败，引用完整 CMake 参数后成功。

`scripts/package_window_probe.py` 是独立、固定 ELF/BIN 哈希的实验打包器。
它校验入口符号、PT_LOAD 范围和 ELF/BIN/FIT 关联，不放宽标准 SRAM
packager。Zephyr objcopy 将节间隙填为 0xff，因此 BIN 关联按 ELF
已分配节重建；首次直接比较 PT_LOAD 字节失败的原因是间隙填充，不是
忽略差异。CRC、OS 槽范围与所有非 OS 字节均再次校验。

镜像内保留原版 target SPL、PBP、USB updater、env、data、rodata 和分区布局，
仅替换 OS slot 和 OS length/CRC 元数据。构建来自当前未提交的工作区，
交付中的源文件哈希、配置和 ELF/BIN 哈希用于关联本实验；不伪装成标准
clean-source candidate receipt 或可发布版本。

## 手动测试

目录：`artifacts/h0-zephyr-window-delivery/`。
文件：`D50T_Zephyr_product_window_probe.img`，2771456 字节。
SHA-256：

```text
88904be63de51af740bd10811c2af69169a1bc5986446dd4dd1ad302e9e0ac2f
```

1. 使用成功的 AiBurn 流程，先 Reset 再 Boot 进入下载模式，烧入此镜像。
2. COM11 / 115200 保存完整日志，烧录完成后仅按 Reset 启动。
3. 观察以下阶段，不要只截取最后一行：

```text
CRC32 verify OK.
... Run APP
H0-PROBE stage=snapshot-before-zephyr
... H0-PROBE stage=main early_uart_status=...
... 快照字段及 sysmap 输出 ...
H0-PROBE CAPTURED hardware-acceptance=pending
```

早期标记出现但 main 未出现，表示已进入探针，尚不能确认 Zephyr 初始化
完成；main 出现才是首次启动的重要证据。`FAIL mtime-incoherent` 表示
入口采样重试耗尽，内核尚未启动。发生异常、无输出或重复重启时保留日志
并恢复原版，不换用旧 SRAM 镜像进行替代试验。

4. 到达 main 后继续记录约 10 秒，用于发现立即发生的异常/重启；这不是
   独立定时精度验收。然后按此前流程烧回目录内原版恢复镜像并确认正常。
5. 回传整段日志、AiBurn 结果和恢复结果。仅凭开机没有 UI 不能判断失败，
   本镜像没有产品 UI。

目前 manual_experiment_ready=true；hardware_validation=pending，
loadable_image=false 仍表示标准 Zephyr 验收门槛未关闭。没有执行上板测试。

## 用户实板输出：已到达 main（2026-09-26）

用户回传了原版 SPL 的 19228 字节读取、CRC 成功和完整的
`H0-PROBE stage=main` / `CAPTURED` 帧。原始粘贴保存在
`artifacts/h0-zephyr-main-user-evidence/user-pasted.txt`，SHA-256：
`930278134488675954bd968169faa1df9bfa31487ec7143fea0112f7ff3dcc91`。
这是用户粘贴的硬件证据，不是 agent 直接采集的串口原始字节。
仅将转义下划线和 HTML 空格还原用于核对；review.json 记录全部字段。

已核对 17 个标量及 8 对 SYSMAP 值，marker=0x48305031。entry=0x40000dd8、
buffer=0x400050c0、bytes=132 与交付 ELF 符号和大小一致。确认实验配置下
已执行至 Zephyr 应用 main；不能把这些入口快照误当成 main 当时的 CSR。
日志 source=152aac9... 是构建时 HEAD，未包含未提交修改；实际关联使用
交付 ELF/BIN 哈希和 source-inventory.json。日志中的 external:candidate.json
是沿用的提示文字，实验包实际凭据为 verification.json / source-inventory.json。

入口补充读数：mip=0、mtvt=0x40c3b440、mexstatus=0x00030010、
mxstatus=0xc0408000、fcsr=0、mtime=0x00000000000f55d2。MIE 清零与
上一轮一致。FCSR 可读不等于浮点上下文切换通过；单个 MTIME 样本不能
验证频率或 tick 运行。TCM/默认 SRAM 区域仍未取证。

两项不能忽略的限制：

- 粘贴日志没有 `snapshot-before-zephyr` 字符串。early_uart_status=2 仅指
  写入 UART，不代表字符已物理送达；不因此否认已收到的 main 输出，也不
  猜测缺失原因。
- CLICINFO=0x00600090。按当前 Zephyr intc_clic.h 的 numint[12:0] 和
  intctlbits[24:21] 定义，以及 SDK core_rv32.h 的位 21 定义，分别为
  144 和 3。当前 CONFIG_NUM_IRQS=96；驱动初始化仅清理配置范围，控制位
  宽度会从硬件读出。下一步需核查中断槽覆盖和继承中断状态，不能把到达
  main 视为所有中断路径通过，也不在此直接把配置改成 144。

本轮 10 秒观察和恢复结果尚未提供；此前三个实验的恢复结论仍有效。
此处只将本轮状态更新为 MAIN_REACHED，不关闭完整内核、定时、FPU、
稳定性或默认 SRAM 验收。0x101 / Unknown reset reason 警告继续保留原文。
