# DSL reference

Every public symbol the customer touches when writing a Scadable
project, with its signature, parameters, and a short example.

Imports:

```python
from scadable import (
    Device, Controller, Topics,
    Register, Characteristic, Pin, Field,
    modbus_tcp, modbus_rtu, ble, gpio, serial, i2c, rtsp,
    every, SECONDS, MINUTES, HOURS, MILLISECONDS,
    on,
    PID, StateMachine, State,
    Model, ONNXModel,
    upload_route, notify,
    system,
)
```

---

## Devices

### `Device` (base class)

Subclass to declare a physical device. The metaclass intercepts
class-level register access so `LineSensor.temperature` returns the
scaled current value at runtime.

```python
class InletTemp(Device):
    id = "inlet-temp"                                  # required
    name = "Inlet temperature"                         # optional
    connection = modbus_tcp(host="...", port=502)      # required
    poll = every(5, SECONDS)                           # optional
    heartbeat = every(30, SECONDS)                     # optional
    health_timeout = 3                                 # missed heartbeats
    historian = every(5, MINUTES)                      # optional
    ota = ModbusOTA(...)                               # optional
    capabilities = ["reset", "calibrate"]              # optional
    registers = [
        Register(40001, "temperature"),
    ]
```

| Attribute        | Type                | Default | Notes                                |
|------------------|---------------------|---------|--------------------------------------|
| `id`             | `str`               | `""`    | Unique within the project. Required. |
| `name`           | `str`               | `""`    | Human-readable label.                |
| `connection`     | protocol helper     | `None`  | One of `modbus_tcp(...)` etc.        |
| `poll`           | `every(...)`        | `None`  | Polling cadence.                     |
| `heartbeat`      | `every(...)`        | `None`  | Health-check publish.                |
| `health_timeout` | `int`               | `3`     | Missed heartbeats → offline.         |
| `historian`      | `every(...)`        | `None`  | Cloud-historian rate.                |
| `ota`            | OTA helper          | `None`  | Out-of-band firmware updates.        |
| `capabilities`   | `list[str]`         | `[]`    | Actions the device supports.         |
| `registers`      | `list[Register/...]`| `[]`    | One entry per measurable field.      |

---

### Register descriptors

#### `Register(address, name, *, unit, scale, writable, dtype, endianness, on_error)`

Modbus register. Address determines read/write capability and register
type:
- `1–9999` = coils (RW boolean)
- `10000–19999` = discrete inputs (RO boolean)
- `30000–39999` = input registers (RO numeric)
- `40000–49999` = holding registers (RW numeric)

| Param         | Type    | Default    | Notes                                       |
|---------------|---------|------------|---------------------------------------------|
| `address`     | `int`   | required   | See ranges above.                           |
| `name`        | `str`   | required   | Becomes the field name on the device class. |
| `unit`        | `str`   | `""`       | UI display unit (`"°C"`, `"L/min"`).        |
| `scale`       | `float` | `1.0`      | `published = raw * scale`.                  |
| `writable`    | `bool`  | inferred   | Override the address-range default.         |
| `dtype`       | `str`   | `"uint16"` | `uint16/int16/uint32/int32/float32/float64/bool`. |
| `endianness`  | `str`   | `"big"`    | `"big"` or `"little"` for multi-word reads. |
| `on_error`    | `str`   | `"skip"`   | `"skip" \| "last_known" \| "fail"`.         |
| `store`       | `bool`  | `True`     | Persist to gateway local storage?           |

**Read-failure policy (`on_error`)**:
- `skip` — drop the sample silently, try next tick.
- `last_known` — emit the previous successful value tagged
  `quality="stale"`.
- `fail` — surface as an alert; skip the sample.

```python
Register(40001, "temp",  dtype="float32", scale=0.1, on_error="last_known")
Register(40003, "flow",  dtype="uint32",  endianness="little")
Register(00001, "relay", dtype="bool",    writable=True)
```

#### `Characteristic(uuid, name, *, unit, scale)`

BLE GATT characteristic. UUID can be 16-bit or 128-bit string form.

```python
Characteristic("00002a37-0000-1000-8000-00805f9b34fb", "heart-rate", unit="bpm")
```

#### `Pin(pin, name, *, mode, trigger, unit, scale)`

GPIO pin. `mode` is `input | output | pwm | adc`.

```python
Pin(17, "led",       mode="output")
Pin(22, "doorbell",  mode="input", trigger="falling")
```

#### `Field(offset, length, name, *, unit, scale)`

Custom serial-frame field — byte offset + length.

```python
Field(0, 4, "header")
Field(4, 2, "device_id")
```

---

## Connection helpers

| Helper                       | Required params                  |
|------------------------------|----------------------------------|
| `modbus_tcp(host, port=502, slave=1)`           | `host`                |
| `modbus_rtu(port, baud=9600, slave=1)`          | `port`                |
| `ble(mac)`                                      | `mac`                 |
| `gpio()`                                        | none                  |
| `serial(port, baud=9600)`                       | `port`                |
| `i2c(bus=1, address)`                           | `address`             |
| `rtsp(url)`                                     | `url`                 |

Strings can be env-var placeholders: `host="${PLC_HOST}"` —
preserved through the compile and resolved at deploy time.

---

## Controllers

### `Controller` (base class)

Subclass to define logic that runs on the gateway. Methods decorated
with `@on.*` become triggered handlers.

```python
class SafetyMonitor(Controller):
    @on.startup
    def init(self):
        self.publish("status", {"state": "armed"})

    @on.interval(2, SECONDS)
    def check(self):
        if InletTemp.temperature > 95:
            self.alert("critical", "overheating")

    @on.message("set-target")
    def update_target(self, message):
        # message is a dict from the inbound MQTT payload
        self.target = message["value"]
```

#### Methods available on `self`

| Method                                       | Purpose                       |
|----------------------------------------------|-------------------------------|
| `self.publish(topic, data, *, quality="good")` | Telemetry → MQTT → cloud   |
| `self.upload(route, blob, *, name, metadata)` | Cloud-storage upload         |
| `self.alert(severity, message)`              | Notification (email/Slack/...) |
| `self.actuate(target, value)`                | Write to a device register   |
| `self.capture(device)`                       | Trigger a capture action     |

**`quality`** on `publish` accepts `"good" | "stale" | "bad"` and rides
through to dashboards as a label.

---

## Triggers

### `@on.interval(value, unit)` — periodic

```python
@on.interval(5, SECONDS)
def tick(self): ...
```

### `@on.threshold(field, *, above=None, below=None)` — value crossing

```python
@on.threshold(InletTemp.temperature, above=80)
def hot(self): ...
```

### `@on.change(field)` — any change

```python
@on.change(Door.state)
def state_changed(self): ...
```

### `@on.message(topic)` — inbound MQTT

```python
@on.message("commands/set-target")
def update(self, message: dict): ...
```

### `@on.device(device, status)` — device status change

```python
@on.device(InletTemp, status=DISCONNECTED)
def offline(self): ...
```

Available status constants: `CONNECTED`, `DISCONNECTED`, `TIMEOUT`,
`DEGRADED`, `ERROR`, `UPDATING`.

### `@on.startup` / `@on.shutdown`

```python
@on.startup
def boot(self): ...

@on.shutdown
def cleanup(self): ...
```

---

## Topic constants

### `Topics` (base class)

Project-level constants. Subclass to define string topics that
publishers + subscribers reference by attribute. The compiler
validates every `Topics.X` reference resolves.

```python
# topics.py
from scadable import Topics

class Topics(Topics):
    SENSOR_DATA  = "sensor-data"
    SETPOINT_CMD = "set-temperature"
    ALERT_HIGH   = "alert/high-temp"
```

```python
# anywhere
from topics import Topics
self.publish(Topics.SENSOR_DATA, {...})

@on.message(Topics.SETPOINT_CMD)
def update(self, message): ...
```

---

## Time helpers

```python
every(5, SECONDS)          # 5 seconds
every(2, MINUTES)          # 2 minutes
every(1, HOURS)             # 1 hour
every(500, MILLISECONDS)   # 500 ms
```

`SECONDS`, `MINUTES`, `HOURS`, `MILLISECONDS` are integer constants
representing milliseconds — `SECONDS == 1000`, etc.

---

## Control primitives (declarative)

### `PID(input, output, setpoint, *, kp, ki, kd, output_min, output_max)`

```python
class BoilerController(Controller):
    pid = PID(
        input=TempProbe.outlet_temp,
        output=Boiler.burner_pwm,
        setpoint=72.0,
        kp=2.0, ki=0.5, kd=0.1,
        output_min=0, output_max=100,
    )
```

The PID block is declarative — the runtime computes the loop. Update
the setpoint dynamically with `self.pid.setpoint = new_target`.

### `StateMachine(initial, *, states)`

(Documented in [docs/getting-started.md](getting-started.md) — example
`09_state_machine`.)

---

## Models

### `ONNXModel("path/to/model.onnx")`

Wrap an ONNX file from your project's `models/` directory.

```python
detector = ONNXModel("models/anomaly.onnx")
result = detector.inference(features)
```

Subclass to add `preprocess()` if you need feature engineering.

---

## OTA helpers

| Helper                 | Notes                                              |
|------------------------|----------------------------------------------------|
| `ModbusOTA(...)`       | Firmware push via Modbus to a downstream PLC.      |
| `BLE_DFU(...)`         | Nordic BLE Device Firmware Update.                 |
| `SerialBootloader(...)`| Generic serial bootloader.                         |

---

## System

```python
from scadable import system

system.shutdown()        # gateway shutdown
system.reboot()          # gateway reboot
info = system.info()     # {"hostname": "...", "uptime": ...}
```

---

## Storage

```python
from scadable import data, files, state

data.write("temp", 42.0, ts=...)
state.set("last-target", 75)
files.put("snapshot.jpg", blob, ttl_days=30)
```

These are placeholders implemented by the gateway runtime.
