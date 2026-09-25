# H0 独立入口跳转实验

## 范围与离线证据

前两轮原产品观察、传输和恢复已由用户完成。这轮仅验证原版 tinySPL
能否跳转到独立探针，并输出入口状态，不启动 Zephyr 或产品应用。

探针为原创 RV32 汇编，代码及数据共 440 字节，唯一 PT_LOAD 为
[0x40000000, 0x400001b8)，入口 0x40000000。此区间位于已测试的原产品
加载范围内；不使用尚未验证的 0x30080000 SRAM，不使用栈、gp 寻址、
C 运行库、计时器、FPU 或中断驱动。记录顺序固定为：

`sp, gp, ra, boot_device_a0, boot_args_a1, mstatus, mie, mtvec, mhcr`。

捕获之后清除 MIE，使用继承的 UART0 输出十六进制字段。检查 DLAB，
每字节最多轮询 65536 次。DLAB 异常或轮询失败时直接停止；MMIO 总线
停滞和异常并不能靠轮询上限解决。成功输出后也永久停止，不返回 loader。
串口最终标记代表到达输出路径，不能证明所有物理内存别名或总线主设备安全。

保留原版 target SPL，实际检验它已有的 dcache clean、icache invalidate、
local IRQ disable、entry(dev,args) 路径。它不包含上一轮 schema=2 插桩
和固定原产品 CRC 限制。新镜像使用另一套固定 profile：打包脚本钉住
原产品容器、探针 ELF/BIN 哈希，独立核对 FIT 的内容、load、entry 和 CRC。
原 SPL 使用其已有 FIT CRC 检查，并未增加新的运行时哈希认证。

构建脚本：`scripts/build_jump_probe.py`；打包：`scripts/package_jump_probe.py`。
离线构建产物：`artifacts/h0-standalone-jump-v1/`。无编译警告；ELF/BIN
关联和 FIT 往返校验通过；反汇编确认栈/gp 仅被读取为快照，停止路径不
调用其他运行库。没有执行实板或模拟器测试来证明这段指令的运行行为。

完整镜像仍为 2771456 字节。除 OS slot 和 OS length/CRC 外逐字节相同；
PBP、USB updater、target SPL、env、data、rodata 和分区布局保持原字节。
全镜像烧录仍可能重写内容相同的分区，不能把字节相同解释成不写 Flash。

## 手动测试

目录：`artifacts/h0-standalone-jump-delivery/`。

1. 用此前成功的 AiBurn 流程，先 Reset、再 Boot 进入下载模式。
2. 烧入 `D50T_H0_standalone_jump.img`。SHA-256：

```text
71b9f5f053308a7cdda4ae3e5c41fd31ca11c04dc80a1216b71a84fb6d9daf65
```

3. 用 COM11 / 115200 保存完整日志，烧录后仅按 Reset 启动。
   这轮是原版 tinySPL，不会出现 H0-SPL schema=2；预期在 FIT CRC
   验证与 Run APP 后看到以下帧（字段值是实际数值，不是占位文字）：

```text
H0-JUMP schema=1 fields=9
H0-J <8位十六进制值，连续9行>
H0-JUMP STOP hardware=pending
```

4. 停止后不返回控制台、不显示产品 UI，这是设计行为。按已验证的
   Reset/Boot 下载流程烧回同目录 `RESTORE_original_product.img`，确认
   原产品恢复正常。回传测试完整日志、AiBurn 结果和恢复结果。
5. 无输出、输出不完整、异常或反复重启时停止本轮并恢复；不要用旧
   SRAM probe、ramboot 或手工内存写入来替代这份固定实验镜像。

日志检查（在项目目录运行）：

```powershell
.venv/Scripts/python.exe scripts/check_jump_log.py '完整路径/jump.log'
```

检查帧完整性与入口 MIE 清零，失败返回非零。PASS 仍不是 Zephyr H1
验收或 M 模式独立测量；本轮 hardware_validation=pending、
loadable_image=false 表示尚未具备 Zephyr 加载验收结论。

## 用户实板结果（2026-09-26）

用户提供了完整入口帧，并在末行说明刷回原版镜像可恢复正常。粘贴原文保存为
`artifacts/h0-jump-user-evidence/user-pasted.txt`，SHA-256：
`79129e8aa3343c858f89749c8fc702d685e89a4c471dc026df94b2c02eeaf841`。
这是聊天粘贴证据，包含反斜杠和 HTML 转义，不是原始串口文件。

校验使用单独的 `extracted-frame.log`：保留全部九项字段，将末行明确的
用户恢复说明从 STOP 标记后分离；未修改字段值。严格校验器保持不变，结果
PASS，报告为同目录 `check.json`。提取帧 SHA-256：
`3e3c64e38a0af6389e13ffa1ddd5935f58c48a94f3d3be5fd93be8084e6e2014`。

| 字段 | 实测报告值 |
| --- | --- |
| sp | 0x40c41ce8 |
| gp | 0x40c3df70 |
| ra | 0x40c0caf4 |
| boot_device_a0 | 0x00000005 |
| boot_args_a1 | 0x40c3be28 |
| mstatus | 0x80006080 |
| mie | 0x00000000 |
| mtvec | 0x40c00383 |
| mhcr | 0x0000103f |

原版 tinySPL 报告读取 440 字节、CRC 成功、Run APP，随后收到完整探针帧。
这证明本轮用户报告的独立探针执行及入口观测链路成功，入口 MIE 位为零。
mhcr 仍为 0x103f，不能把缓存维护解释成“所有缓存已关闭”；mie=0 也不能
单独作为所有 CLIC 中断状态已清除的证明。没有解引用 boot_args 指针或
把 sp/gp/ra 数值推断为完整内存所有权。

复位日志为 0x101，并明确打印 Unknown reset reason: 2 - 1。保留该警告，
不将它自行解释为已验证冷启动、故障看门狗或新的硬件问题。

本轮跳转与恢复闭环，恢复依据为用户确认；无需为此重复烧录。Zephyr
尚未运行，0x30080000 SRAM 可用性、完整别名/总线主设备安全和内核启动
条件仍未关闭。历史交付 manifest 不改写为事后已验证。
