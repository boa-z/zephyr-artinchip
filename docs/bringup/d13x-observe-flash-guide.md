# D50T 第一轮 H0 烧录取证操作单

这轮可以由操作者执行受控的 H0 观察实验。它不是 Zephyr 启动验收，也没有
预先宣称实板成功。用户已要求推进到实际烧录测试；本操作单不授权 agent 自动烧录。

交付目录：
`C:/Users/JCSH/Documents/Project/zephyr-artinchip/artifacts/h0-observe-delivery`

| 文件 | 用途 | SHA-256 |
| --- | --- | --- |
| `D50T_H0_observe_only.img` | 本次烧录镜像 | `0ab10b5c239c859757846ae65db39aa1fff96812d06fc7919be23fe7d491659f` |
| `RESTORE_original_product.img` | 恢复原产品 | `b0062dacbd68e8ef6f6de0c99c7cdc6620e602c5e00e913b454af6e93037aaf1` |

这两份文件都是 2,771,456 字节。先确认 SHA256SUMS.txt 中的值与文件一致。
可在 PowerShell 中运行：

```powershell
Get-FileHash 'C:/Users/JCSH/Documents/Project/zephyr-artinchip/artifacts/h0-observe-delivery/D50T_H0_observe_only.img' -Algorithm SHA256
Get-FileHash 'C:/Users/JCSH/Documents/Project/zephyr-artinchip/artifacts/h0-observe-delivery/RESTORE_original_product.img' -Algorithm SHA256
```

## 镜像做什么

只替换 NAND 目标 SPL。原下载 updater、PSRAM 初始化组件、PBP 前缀、原 OS、
env/env_r、rodata/data 内容保持一致。AiBurn 整包操作仍可能擦写这些内容一致的
分区；这不等于只写 SPL。开发板数据无需保留这一偏好已经记录。

启动后，诊断 SPL 在 FIT 加载函数入口读取已知寄存器、输出 54 条状态记录，
主动返回错误，停在 loader 控制台。**原产品界面不启动是预期行为。**
反汇编已确认该入口不会读取 OS FIT 或跳转载荷。

它仍依赖原有 PBP/PSRAM/loader 初始化路径。新增 MMIO 读取和打印尚未实板验证；
若出现挂起或异常，应按下面流程恢复，不能据此断言硬件损坏或继续尝试 Zephyr。

## 操作步骤

1. 打开 `C:/Program Files/AiBurn` 中之前成功烧录所用的 AiBurn。
   使用同一块板、同一 USB 连接、原来的介质/设备配置。不要套用未验证的新配置。
   本文没有读取当前 AiBurn 窗口，不臆造按钮名称。
2. 建议先用 `RESTORE_original_product.img` 重复一次已验证的整包烧录流程，
   确认工具与设备仍正常。按你已经验证的方法进入下载模式：先 Reset、后 Boot。
   按键释放时机沿用你的成功操作，不根据本文猜测新时序。
3. 正常复位，确认原产品仍启动。串口使用 **COM11、115200**；其他参数沿用
   之前能正确输出日志的配置。保存这份日志为 `01-original-before.log`。
4. 再进入下载模式，在 AiBurn 选择 `D50T_H0_observe_only.img`，执行相同整包流程。
   确认工具报告完成；保存烧录日志或结果。若工具拒绝镜像、报告校验失败或中途
   失败，停止测试，保留错误信息并使用恢复镜像，不改包或跳过校验。
5. 在串口工具中开启新的原始文本日志，正常复位：**单独按 Reset，不按 Boot**。
   等待输出结束，保存为 `02-h0-observe.log`。这次不要输入 `ram_boot`、
   `nand_boot`、写内存或其他执行命令。
6. 不论观察成功还是失败，都重新进入下载模式，使用
   `RESTORE_original_product.img` 执行相同整包流程。
   正常复位，保存 `03-original-restored.log`，确认恢复原产品启动。

串口如被其他程序占用，关闭占用程序后再开始日志采集。AiBurn 本轮沿用原有 USB
烧录方式，不切换到尚未验证的串口烧录路径。供电/断电方式沿用你此前成功流程。

## 观察成功的标志

日志中应出现下面的结构，寄存器值不应照抄示例填入：

```text
H0-SPL begin schema=1 instrumentation=active acceptance=pending
H0-SPL entry=00000000 count=54 dropped=0
H0-E 0 ...
... 共 54 条，序号 0 到 53 ...
H0-SPL end evidence=CAPTURED hardware=pending
H0-OBSERVE-ONLY: OS not read; no payload jump; return to console
```

最后应留在 loader 控制台，不出现新 Zephyr 启动通过标志。
记录不全、`dropped` 非零、异常转储、持续重启或没有串口输出，都属于本轮未通过，
不要靠多次重复烧写或随意更换地址排查。

恢复日志应再次出现 Sep24 `16:30:14` tinySPL、Sep25 `14:16:45` 产品应用，
以及正常的产品启动输出。若无法重新进入下载模式或恢复烧录失败，停止进一步操作，
保留工具报错和最后日志。恢复路径成功与否必须以本次实际记录为准。

可在项目目录离线检查观察日志：

```powershell
.venv/Scripts/python.exe scripts/check_observation_log.py '完整路径/02-h0-observe.log'
```

这个检查只验证文本结构、记录顺序和完整性，并列出非零 DMA enable 读数；不会
把日志解析成功标记为 Zephyr 可加载或内存安全已通过。原始日志请保留，不要粘贴进
会改写字符的富文本编辑器后再另存。

## 实验后需要回传

回传上述三份原始日志，以及 AiBurn 的测试/恢复烧录结果。
我们据此核对两次映射/DMA 快照、停止行为和恢复能力，再设计下一阶段的传输取证。
这轮不运行 probe/kernel/FPU；动态传输阶段尚未取证，不能跳过它直接宣称 H1 通过。

交付状态为 `manual_observation_trial_ready=true`。已有 `loadable_image=false`
继续表示 Zephyr H1 镜像尚未放行；`hardware_validation=pending` 和
`recovery_verified=false` 将保持到实际日志审核后再更新。
