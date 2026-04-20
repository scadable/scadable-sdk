# Protocols

What's runtime-supported in v0.2.0 vs. what the DSL accepts for
forward compatibility.

## v0.2.0 status

| Protocol     | DSL accepts | Runtime (gateway-linux) | Notes                                |
|--------------|-------------|-------------------------|--------------------------------------|
| `modbus_tcp` | ✅          | ✅ production           | TCP/IP master, register ranges 1–49999 |
| `modbus_rtu` | ✅          | ✅ production           | RS-485 serial, same register model     |
| `ble`        | ✅          | 🚧 v0.3                 | GATT characteristics                   |
| `gpio`       | ✅          | 🚧 v0.3                 | Direct pin I/O                         |
| `serial`     | ✅          | 🚧 v0.3                 | Raw RS-232/RS-485 framing             |
| `i2c`        | ✅          | 🚧 v0.3                 | I2C bus master                        |
| `rtsp`       | ✅          | 🚧 v0.3                 | RTSP video stream pull                |

**Modbus is the only protocol with full end-to-end runtime support
in v0.2.0.** Other protocols can be authored, validated, and
compiled, but their drivers don't yet ship with `gateway-linux`.

## Why Modbus first

Modbus covers ~80% of real industrial deployments we've seen. It's
also the simplest protocol to get right: a flat register map,
deterministic addressing, no eventing. Locking it in end-to-end
gave us a stable foundation to add the rest against.

## Modbus reference

See [docs/modbus-tcp.md](modbus-tcp.md) for the full Modbus guide:
register address ranges, scaling, dtypes, multi-word reads,
endianness, OTA registers, and Modbus RTU (serial) specifics.

## Authoring with not-yet-supported protocols

You can write a BLE/GPIO/serial/i2c/rtsp device today and the SDK
will accept it:

```python
from scadable import Device, Characteristic, ble, every, MINUTES

class EnvSensor(Device):
    id = "env-1"
    connection = ble(mac="${ENV_SENSOR_MAC}")
    poll = every(30, MINUTES)
    registers = [
        Characteristic("0x2A6E", "temperature", unit="°C", scale=0.01),
    ]
```

`scadable verify` and `scadable compile` succeed. The compiled YAML
contains the BLE config. The current `gateway-linux` build won't
have a BLE driver to read it, so the device shows as "no driver" at
runtime until v0.3 ships.

If that's blocking for you, put the file behind an env-var check or
delete it for now and add it back when the runtime catches up.

## Per-target protocol support

The validator enforces per-target protocol availability. See
[docs/targets.md](targets.md) for the full matrix. Highlights:

- **ESP32** rejects `modbus_tcp` and `rtsp` (no real TCP/IP stack).
- **RTOS** rejects everything except `modbus_rtu`, `gpio`, `can`.

Compiling for a target with an unsupported protocol fails fast at
validate time:

```text
error: Device 'env-1': protocol 'ble' is not supported on target 'rtos'
       (allowed: ['can', 'gpio', 'modbus_rtu'])
```
