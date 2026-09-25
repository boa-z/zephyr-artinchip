# H0 原产品传输取证测试

前置记录：上一轮观察日志校验通过，用户已确认恢复原产品运行正常。
这轮使用原产品 payload，只验证读取过程；不是 Zephyr H1 启动验收。

## 镜像与范围

目录：`artifacts/h0-transfer-guard-candidate/`。
测试镜像：`D50T_H0_transfer_stop.img`，2771456 字节，SHA-256：

```text
5b15f5acb0b8652543dc68a930363eaaec9729bf52ac6243a3886fe8cc56a5ea
```

该固定版本只允许 SPI NAND FIT 头部 40 字节、元数据 732 字节读取至
loader 默认堆；payload 固定为地址 0x40000000、长度 1397820、偏移
0x800、预期 CRC32 0xf183bd17。拒绝其他读取配置，boot_app 禁止跳转。
只关闭了诊断目标 SPL 的内存读写命令以满足原槽位容量；串口控制台和
原始 USB updater 保留。PBP、原产品 OS、其他组件及分区布局保持原字节。

离线校验覆盖包装校验和、组件 CRC、非目标区域一致性和 ELF/BIN 关联。
DMA 描述符源于 loader 静态池；持久 NAND 缓冲区源于默认堆。源代码归属
与数值地址不重叠不等于实测所有指针、物理别名或所有总线主设备安全。
本轮保留这些限制，不将其转换为 Zephyr 可加载结论。

## 手动操作

1. 使用此前成功的 AiBurn 流程：先 Reset，再 Boot 进入下载模式。
2. 烧入上述测试镜像。保留 AiBurn 结果。
3. COM11 / 115200 保存完整串口原始日志。烧录完成后仅按 Reset 启动。
4. 预期出现 `schema=2`、CRC32 成功、`dropped=0`，最终停在控制台：

```text
H0-SPL begin schema=2 instrumentation=active acceptance=pending
...
H0-SPL end evidence=CAPTURED hardware=pending
H0-TRANSFER-ONLY: FIT attempt ended; no payload jump; return to console
```

记录数不再固定为 54。返回控制台、不出现产品 UI 是本轮预期行为。
末尾停止标记本身不代表读取成功，必须检查完整日志。

5. 完成后按相同下载流程烧回目录内 `RESTORE_original_product.img`，
   仅按 Reset 验证原产品恢复。不要使用控制台内存写入或 ramboot 命令。
6. 回传完整测试日志、AiBurn 结果及恢复结果。失败、异常、无输出或
   持续重启时停止本轮，使用已经验证过的原产品恢复路径，并保留日志。

离线检查命令（在项目目录）：

```powershell
.venv/Scripts/python.exe scripts/check_transfer_log.py '完整路径/transfer.log'
```

CLI 默认绑定上述原产品记录字段。失败返回非零；PASS 只表示日志结构和
报告字段符合预期，不是镜像读回或 Zephyr 实板验收。
`loadable_image=false` 仍指 Zephyr H1 门槛；本包的范围仅为手动 H0 实验。
