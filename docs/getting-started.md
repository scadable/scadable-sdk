# Getting Started with Scadable SDK

## Installation

```bash
pip install scadable-sdk
```

This gives you the `scadable` CLI and the Python package for writing device logic.

## Create a Project

```bash
scadable init linux my-factory
cd my-factory
```

This creates:

```
my-factory/
├── devices/          # Device definitions go here
├── controllers/      # Controller logic goes here
├── models/           # ONNX model definitions go here
├── storage.py        # Local storage configuration
├── routes.py         # Cloud upload + notification routes
├── fleet.toml        # Gateway → device mapping
└── scadable.toml     # Project manifest
```

Targets: `linux` (Raspberry Pi, industrial boxes), `esp32`, `rtos`.

## Add a Device

```bash
scadable add device modbus-tcp line-sensor
```

This generates `devices/line_sensor.py` with a template. Edit it to match your hardware:

```python
from scadable import Device, Register, modbus_tcp, every, SECONDS, MINUTES

class LineSensor(Device):
    id = "line-sensor"
    name = "Line sensor"

    connection = modbus_tcp(host="192.168.1.50", port=502, slave=1)
    poll = every(5, SECONDS)
    historian = every(5, MINUTES)

    registers = [
        Register(40001, "temperature", unit="°C", scale=0.1),
        Register(40002, "pressure",    unit="bar", scale=0.01),
    ]
```

## Add a Controller

```bash
scadable add controller temp-monitor
```

Edit `controllers/temp_monitor.py`:

```python
from scadable import Controller, on, SECONDS
from devices.line_sensor import LineSensor

class TempMonitor(Controller):

    @on.interval(5, SECONDS)
    def check(self):
        if LineSensor.temperature > 95:
            self.alert("critical", f"Temp: {LineSensor.temperature}°C")

        self.publish("sensor-data", {
            "temperature": LineSensor.temperature,
            "pressure": LineSensor.pressure,
        })
```

## Validate

```bash
scadable verify
```

Checks syntax, structure, register validity, and controller references. Add `--target esp32` for memory estimation.

## Next Steps

- [Generators Reference](generators.md) — all `scadable add` commands
- [Modbus TCP Guide](modbus-tcp.md) — registers, addressing, scaling
- [Controller Triggers](triggers.md) — all `@on.*` decorators
- [Storage](storage.md) — local data, files, and state
- [ML Inference](ml-inference.md) — ONNX models at the edge
- See `examples/` for 14 progressive examples
