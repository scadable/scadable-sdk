# Generators Reference

The `scadable` CLI scaffolds project files so you don't write boilerplate. Each command generates a working template with `TODO` placeholders.

## `scadable init <target> <name>`

Create a new project.

| Target | What it sets up | Storage default |
|--------|----------------|----------------|
| `linux` | Raspberry Pi, industrial Linux | 256MB |
| `esp32` | ESP32 microcontroller | 2MB |
| `rtos` | Zephyr/FreeRTOS on Cortex-M | 64KB |

```bash
scadable init linux my-factory
scadable init esp32 sensor-node
scadable init rtos valve-controller
```

Generated files:

| File | Purpose |
|------|---------|
| `scadable.toml` | Project manifest (name, version, target) |
| `fleet.toml` | Gateway-to-device mapping |
| `storage.py` | Local storage config (sized for target) |
| `routes.py` | Cloud upload + notification config |
| `devices/` | Empty directory for device definitions |
| `controllers/` | Empty directory for controller logic |
| `models/` | Empty directory for ONNX models |

---

## `scadable add device <protocol> <name>`

Generate a device definition file in `devices/`.

### Protocols

| Protocol | Command | Connection type |
|----------|---------|----------------|
| Modbus TCP | `scadable add device modbus-tcp line-sensor` | Ethernet/WiFi |
| Modbus RTU | `scadable add device modbus-rtu power-meter` | RS-485 serial |
| BLE | `scadable add device ble env-sensor` | Bluetooth Low Energy |
| GPIO | `scadable add device gpio door-contact` | Direct pin I/O |
| Serial | `scadable add device serial custom-device` | RS-232/RS-485 |

### What gets generated

`scadable add device modbus-tcp line-sensor` creates `devices/line_sensor.py`:

```python
"""TODO: describe this device."""
from scadable import Device, Register, modbus_tcp, every, SECONDS, MINUTES


class LineSensor(Device):
    id = "line-sensor"                    # TODO: set unique device ID
    name = "Line Sensor"

    connection = modbus_tcp(
        host="${SENSOR_HOST}",            # TODO: set host address
        port=502,
        slave=1,                          # TODO: set Modbus slave ID
    )
    poll = every(5, SECONDS)              # TODO: set poll interval
    historian = every(5, MINUTES)         # TODO: adjust or remove

    registers = [
        Register(40001, "value_1", unit="", scale=1),   # TODO: define registers
    ]
```

Fill in the `TODO` items to match your hardware.

### Naming conventions

The CLI converts names automatically:

| Input | File | Class |
|-------|------|-------|
| `line-sensor` | `devices/line_sensor.py` | `LineSensor` |
| `temp_pressure` | `devices/temp_pressure.py` | `TempPressure` |
| `MyPLC` | `devices/myplc.py` | `Myplc` |

---

## `scadable add controller <name>`

Generate a controller file in `controllers/`.

```bash
scadable add controller temp-monitor
```

Creates `controllers/temp_monitor.py`:

```python
"""TODO: describe this controller."""
from scadable import Controller, on, SECONDS


class TempMonitor(Controller):

    @on.interval(5, SECONDS)              # TODO: set trigger
    def run(self):
        pass                              # TODO: implement logic
```

### What you typically add

1. Import the devices you want to read from
2. Choose a trigger (`@on.interval`, `@on.data`, `@on.threshold`, etc.)
3. Write the logic in the method body

```python
from scadable import Controller, on, SECONDS
from devices.line_sensor import LineSensor

class TempMonitor(Controller):

    @on.interval(5, SECONDS)
    def check(self):
        if LineSensor.temperature > 95:
            self.alert("critical", f"Temp: {LineSensor.temperature}°C")
        self.publish("readings", {"temp": LineSensor.temperature})
```

---

## `scadable add model <name>`

Generate an ONNX model definition in `models/`.

```bash
scadable add model anomaly-detector
```

Creates `models/anomaly_detector.py`:

```python
"""TODO: describe this model."""
from scadable import ONNXModel


class AnomalyDetector(ONNXModel):
    id = "anomaly-detector"
    name = "Anomaly Detector"
    version = "0.1.0"
    file = "models/anomaly-detector.onnx"  # TODO: add model file

    def preprocess(self, *args):
        """Transform raw sensor values into model input tensor."""
        return list(args)  # TODO: implement

    def inference(self, prediction):
        """Interpret model output into actionable result."""
        return {"score": prediction[0]}  # TODO: implement
```

### Required methods

| Method | What it does | Must implement? |
|--------|-------------|-----------------|
| `preprocess(*args)` | Raw values → model input tensor | Yes |
| `inference(prediction)` | Model output → usable dict | Yes |
| `run(*args)` | Chains preprocess → predict → inference | No (inherited) |

---

## `scadable verify`

Validate the project without compiling.

```bash
scadable verify                    # basic validation
scadable verify --target esp32     # + memory estimation
```

### What it checks

| Check | What it validates |
|-------|-------------------|
| Project structure | `scadable.toml`, directories exist |
| Python syntax | All `.py` files parse correctly |
| Device definitions | `id`, `connection`, `registers` present |
| Register addresses | Valid for the protocol (30xxx=input, 40xxx=holding) |
| Controller triggers | At least one `@on.*` decorated method |
| Memory estimate | Storage sizes fit the target platform |

### Example output

```
── Checking project structure ────────────
  ✓ scadable.toml found
  ✓ fleet.toml found
  ✓ devices/ directory found
  ✓ controllers/ directory found

── Validating devices ────────────────────
  ✓ devices/line_sensor.py: LineSensor (3 registers)

── Validating controllers ────────────────
  ✓ controllers/temp_monitor.py: TempMonitor

── Result ───────────────────────────────
  ✓ all checks passed
```
