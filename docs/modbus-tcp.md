# Modbus TCP Guide

Modbus is the most common industrial protocol. A Modbus device is a bank of numbered registers — you read from them or write to them. That's it.

## Quick start

```bash
scadable add device modbus-tcp my-sensor
```

Then edit `devices/my_sensor.py`:

```python
from scadable import Device, Register, modbus_tcp, every, SECONDS, MINUTES

class MySensor(Device):
    id = "my-sensor"
    name = "My Sensor"

    connection = modbus_tcp(host="192.168.1.50", port=502, slave=1)
    poll = every(5, SECONDS)
    historian = every(5, MINUTES)

    registers = [
        Register(40001, "temperature", unit="°C", scale=0.1),
        Register(40002, "pressure",    unit="bar", scale=0.01),
        Register(40003, "setpoint",    unit="°C",  writable=True),
    ]
```

## Connection parameters

```python
connection = modbus_tcp(
    host="192.168.1.50",    # IP address or hostname
    port=502,               # Modbus TCP port (502 is standard)
    slave=1,                # Modbus slave/unit ID (1-247)
)
```

Use `${VARIABLE}` for values that change per gateway:

```python
connection = modbus_tcp(host="${SENSOR_HOST}", port=502, slave=1)
```

The variable is set in `fleet.toml`:

```toml
[gateway.env]
SENSOR_HOST = "192.168.1.50"
```

## Register addresses

The register number tells you what type it is:

| Address range | Type | Access | Use case |
|---------------|------|--------|----------|
| **30001–39999** | Input Registers | Read-only | Sensor measurements |
| **40001–49999** | Holding Registers | Read/Write | Configuration, setpoints |
| **00001–09999** | Coils | Read/Write | On/off switches |
| **10001–19999** | Discrete Inputs | Read-only | On/off status |

The SDK auto-detects access mode from the address:

```python
registers = [
    Register(30001, "temperature"),   # 3xxxx → read-only automatically
    Register(40001, "setpoint"),      # 4xxxx → writable automatically
]
```

Override with `writable=True` or `writable=False` if your device doesn't follow the convention.

## Scaling

Raw Modbus values are 16-bit integers. The `scale` parameter converts to real units:

```python
# Raw value 225 → 225 × 0.1 = 22.5°C
Register(40001, "temperature", unit="°C", scale=0.1)

# Raw value 1013 → 1013 × 0.01 = 10.13 bar
Register(40002, "pressure", unit="bar", scale=0.01)

# Raw value 1500 → 1500 × 1 = 1500 RPM (no scaling)
Register(30001, "speed", unit="RPM", scale=1)

# Raw value 5000 → 5000 × 0.001 = 5.0 mm/s
Register(30003, "vibration", unit="mm/s", scale=0.001)
```

Check your sensor's datasheet for the correct scale factor.

## Reading in controllers

Import the device and access registers by name:

```python
from devices.my_sensor import MySensor

class Monitor(Controller):

    @on.interval(5, SECONDS)
    def check(self):
        temp = MySensor.temperature    # reads register 40001, applies scale
        pressure = MySensor.pressure   # reads register 40002, applies scale

        self.publish("data", {
            "temperature": temp,
            "pressure": pressure,
        })
```

## Writing to registers

Only holding registers (40xxx) and coils (0xxxx) are writable:

```python
# In a controller
MySensor.setpoint = 75.0     # writes to register 40003

# The SDK applies inverse scaling automatically:
# 75.0 / 0.1 = 750 → writes 750 to the raw register
```

Attempting to write to a read-only register raises an error:

```python
MySensor.temperature = 50    # ERROR: Register 30001 is read-only
```

## Historian

Store register values in the cloud historian (TimescaleDB):

```python
historian = every(5, MINUTES)   # store ALL registers every 5 minutes
```

Exclude noisy registers:

```python
registers = [
    Register(40001, "temperature", unit="°C", scale=0.1),
    Register(40002, "debug_flag", store=False),   # not stored in historian
]
```

## OTA firmware updates

If your Modbus device supports firmware updates via registers:

```python
from scadable.ota import ModbusOTA

class SmartSensor(Device):
    # ... connection, registers ...

    ota = ModbusOTA(
        version  = 30100,           # register that holds current firmware version
        firmware = (50001, 1000),   # register range for writing firmware chunks
        trigger  = 50010,           # write 1 to this register to start flash
    )
```

The platform handles chunking, progress tracking, and rollback. The dashboard shows an "Update Firmware" button for devices with OTA configured.

## Multiple devices on one network

Multiple Modbus devices on the same network use different slave IDs:

```python
class Sensor1(Device):
    id = "sensor-1"
    connection = modbus_tcp(host="192.168.1.50", port=502, slave=1)
    # ...

class Sensor2(Device):
    id = "sensor-2"
    connection = modbus_tcp(host="192.168.1.50", port=502, slave=2)
    # ...

class VFD(Device):
    id = "vfd-motor"
    connection = modbus_tcp(host="192.168.1.50", port=502, slave=3)
    # ...
```

## Modbus RTU (serial)

For RS-485 serial connections, use `modbus_rtu` instead:

```bash
scadable add device modbus-rtu power-meter
```

```python
from scadable import Device, Register, modbus_rtu, every, SECONDS

class PowerMeter(Device):
    id = "power-meter"
    connection = modbus_rtu(
        port="/dev/ttyUSB0",
        baudrate=9600,
        slave=1,
        parity="N",
        stopbits=1,
    )
    poll = every(5, SECONDS)

    registers = [
        Register(30001, "voltage",  unit="V",  scale=0.1),
        Register(30002, "current",  unit="A",  scale=0.01),
        Register(30003, "power",    unit="kW", scale=0.001),
    ]
```

Same register addressing, same scaling, same controller access — just a different transport.

## Common mistakes

| Mistake | Fix |
|---------|-----|
| Wrong register address (off by 1) | Modbus docs use 0-based (40000), Scadable uses 1-based (40001). Check your sensor's datasheet. |
| Wrong scale factor | Raw value × scale should give the correct engineering unit. Test with `scadable verify`. |
| Writing to a read-only register | Only 40xxx (holding) and 0xxxx (coils) are writable. |
| Wrong slave ID | Each device on the bus has a unique ID (1-247). Check the device's DIP switches or config menu. |
| Connection timeout | Verify the IP is reachable: `ping 192.168.1.50`. Check firewall rules. |
