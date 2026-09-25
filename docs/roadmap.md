# Roadmap

P0 establishes module discovery, fixed dependencies, provenance checks and actual
generic RV32 QEMU runtime validation. QEMU is not D13x validation.

Z0 targets SRAM boot, UART console, timer/IRQ, scheduling, hard-double ABI,
FPU context and bounded memory/cache checks. Hardware closure requires real logs.

After Z0 hardware closure, Z1 improves clock/reset/pinctrl/GPIO/UART and prepares
the smallest upstream candidate. Z2 adds CAN and protocol I/O. Z3 addresses
storage reliability. Z4/Z5 address display software and then acceleration.
D21x requires a separate C906/RV64 audit. None of these later stages is implemented.
