# Targets

Scadable SDK compiles to per-target artifacts. v0.2.0 ships a
production Linux emitter; ESP32 + RTOS are reserved as preview.

## Capability matrix

| Capability               | linux                                              | esp32                                | rtos                  |
|--------------------------|----------------------------------------------------|--------------------------------------|-----------------------|
| **Status**               | production                                         | preview (v0.3)                       | preview (v0.4)        |
| **Memory budget**        | unbounded                                          | 520 KB                               | 256 KB                |
| **Protocols**            | modbus_tcp, modbus_rtu, ble, gpio, serial, i2c, rtsp | modbus_rtu, i2c, spi, gpio          | modbus_rtu, gpio, can |
| **Data types**           | uint16, int16, uint32, int32, float32, float64, bool | uint16, int16, uint32, int32, float32, bool | uint16, int16, bool |
| **Controller execution** | Python interpreter subprocess                      | MicroPython OR codegen (TBD)         | C/Rust codegen        |
| **OTA model**            | A/B atomic binary swap                             | Partition swap                       | Bootloader-managed    |

## What "preview" means

The SDK accepts `target="esp32"` or `target="rtos"` for forward
compatibility. The validator already runs the per-target capability
checks: it'll catch you if you write `dtype="float64"` on RTOS or
use `modbus_tcp` on ESP32.

What it can't do yet: **emit the actual artifact**. Compiling for a
preview target raises `TargetNotImplementedError` with a planned
version:

```text
ESP32 emitter is not implemented in v0.2.0 — scheduled for v0.3.
The DSL accepts target='esp32' for forward-compat (validator will
still flag protocol/dtype mismatches), but compile output is not
yet emitted. Track the milestone at
https://github.com/scadable/scadable-sdk/milestones.
```

This means: you can author your project today, run `scadable verify
--target esp32` to confirm it'll fit, and queue it up for when the
runtime ships.

## Why these capability differences

**Memory.** ESP32 has ~520 KB of usable RAM; RTOS targets often
have 256 KB or less. `float64` doubles register storage and most
PID/control math doesn't need it. RTOS also generally lacks an FPU —
all-float code is slow.

**Protocols.** ESP32 has WiFi but no TCP/IP stack mature enough to
host a Modbus TCP master at scale; RTOS targets are even thinner.
Both speak Modbus RTU and direct IO (GPIO/I2C/SPI/CAN) natively.

**Controller execution.** Linux can spawn a Python interpreter
subprocess to run user code with full Python semantics. ESP32 and RTOS
need either an embedded Python (MicroPython) or codegen to native
(C/Rust). The DSL is shaped for codegen-friendliness — declarative
triggers, no dynamic dispatch — so this isn't blocked architecturally,
just not shipped.

## Why this matrix is the source of truth

`scadable/_targets.py` is the single file the validator and emitters
both read. When ESP32 ships in v0.3:
- The capability matrix gets updated in one place.
- The Esp32Emitter stub gets a real implementation.
- Existing customer projects that targeted `esp32` for testing now
  produce real output.

No other code changes. That's the whole point of the layout.

## Selecting a target

CLI:

```bash
scadable compile --target linux       # default
scadable compile --target esp32       # raises TargetNotImplementedError
scadable verify --target rtos         # validates capability without emitting
```

Python API:

```python
from scadable.compiler import compile_project
result = compile_project(Path("./myproj"), target="linux")
```

## Adding a target later

See [CONTRIBUTING.md → Adding a new target](../CONTRIBUTING.md#adding-a-new-target).
