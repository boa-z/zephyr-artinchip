# D13x H0: offline RAM boot review and next observations

Status: H0 BLOCKED; H1 NOT_RUN; hardware_validation=pending;
loadable_image=false; recovery_verified=false. This document is an H0 observation
plan, not an H1 delivery or permission to operate hardware.

## Installed tool review

`scripts/audit_ramboot_tool.py` reads the executable as bytes only. Run:

```powershell
.venv/Scripts/python.exe scripts/audit_ramboot_tool.py 'C:/Program Files/AiBurn/upgcmd.exe'
```

Exit 2 means the reviewed identity matched but loading remains BLOCKED. Exit 1
means unknown or unreadable input. The report is a lookup of a manual review,
not automatic proof of arbitrary executable behavior. No vendor binary is
distributed. The SHA-256 is
`e58c96d7b34a1150115013519646af2d4518f8b63e9232559de959072097d48f`.

Offline x86 disassembly establishes the following call chain (PE virtual
addresses, not board addresses): function at `0x405ed0`, format reference at
`0x406223` to `0x605007` (`ram_boot 0x%lx %s %d`), call at `0x40628c` to
`0x4073b0`, call at `0x4073d2` to `0x4072b0`. The latter stores protocol header
word `0x00050101` at `0x4072e5`, selecting command 05, RUN_SHELL. The SDK
`basic_cmd.c` run-shell receiver provides the reference interpretation.
To inspect locally without launching the vendor tool:

```powershell
objdump -d --start-address=0x405ed0 --stop-address=0x4062d0 'C:/Program Files/AiBurn/upgcmd.exe'
objdump -d --start-address=0x4072b0 --stop-address=0x4073e0 'C:/Program Files/AiBurn/upgcmd.exe'
```

The matching loader's `do_ram_boot` at `0x40c0d394` has only the AIC-header
branch; its source FIT branch is not compiled in (see loader memory audit).
Consequently, this host command does not supply the missing RAM FIT executor.
NAND OS FIT loading is a different path. A raw candidate ITB must not be offered
as a validated `upgcmd ramboot` input. Connection/updater preparation has not
been fully audited; the word "ramboot" is not proof of zero persistent writes.
Direct UPG EXEC is also not an equivalent replacement for `boot_app` handoff.

## Next human-assisted observation session

First identify the actual serial port and framing used with 115200, and whether
a supported debugger can halt/read the D133ECS. Do not guess a debug interface,
probe model, CSR number or staging address. If no debugger is available, stop
after collecting the existing product boot log; a different observation method
must be designed before any candidate is loaded.

For the initial session, retain an unedited serial log of the known-good product
boot, including loader/application build banners and any config-partition
message. This binds observed software to the current reference, but banners
alone do not prove flash byte identity. Record board wiring and debugger details
for the subsequent observation procedure. No new firmware is required for this
initial observation.

The subsequent debugger procedure must be adapted to that actual setup and
capture evidence at the loader's relevant stages, not just at an idle console:

| Stage | Evidence needed | Why it matters |
| --- | --- | --- |
| Before payload writes | Actual SRAM/TCM mapping and aliases, live loader ranges, staging allocation and bounds | Prevent overwriting loader state while loading |
| During FIT transfer | Destination ranges, allocator/bounce-buffer lifetimes and DMA ownership | A final snapshot cannot rule out transient overlap |
| Immediately before `boot_app` payload jump | CPU/cache/IRQ state, active bus masters, stack bounds/high-water evidence, boot arguments | Establish the state inherited by Zephyr |

Every observation must identify loader image/hash, capture stage/PC, tool and
method, raw output, address units and timestamp. An RT-Thread application
snapshot is not evidence of loader handoff state. A halted core does not by
itself prove peripheral DMA has stopped. Unknown fields remain unknown.
No fixed staging address is proposed by this document.

Recovery remains a separate gate. The operator has confirmed AiBurn at
`C:/Program Files/AiBurn`, disposable board data and Reset **then** Boot.
Release timing remains unspecified. The known-good whole image SHA-256 is
`b0062dacbd68e8ef6f6de0c99c7cdc6620e602c5e00e913b454af6e93037aaf1`.
Previous successful programming is recorded, but recovery from a nonbooting
diagnostic application has not been observed. Plan that rehearsal after the
write path and recovery procedure are reviewed; do not deliberately break the
application during the first observation session.

Only after memory ownership, loading path and recovery are closed can H1
delivery and separately authorized physical execution begin. The existing
handoff probe, bringup, kernel and FPU artifacts remain static candidates.
