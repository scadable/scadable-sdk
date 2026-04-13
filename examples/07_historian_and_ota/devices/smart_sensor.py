"""Smart sensor with cloud historian and OTA firmware updates.

Demonstrates:
  historian — cloud-side time-series storage at a configurable rate
  ota       — remote firmware update capability for the connected device

The historian tells the cloud historian (TimescaleDB) to sample this
device's data at the specified interval. The gateway always sends at
the poll rate; the historian down-samples.

The OTA block defines how the platform can remotely update the
connected device's firmware (not the gateway — the DEVICE itself).
"""
from scadable import Device, Register, modbus_tcp, every, SECONDS, MINUTES
from scadable.ota import ModbusOTA


class SmartSensor(Device):
    id = "smart-sensor-1"
    name = "Smart pressure transmitter"

    connection = modbus_tcp(host="${SENSOR_HOST}", port=502, slave=1)
    poll = every(5, SECONDS)
    historian = every(5, MINUTES)  # cloud stores all registers at this rate

    # Device firmware update via Modbus registers
    ota = ModbusOTA(
        version  = 30100,          # read current firmware version
        firmware = (50001, 1000),   # write firmware chunks to this register range
        trigger  = 50010,          # write 1 to start firmware flash
    )

    registers = [
        Register(40001, "temperature", unit="°C", scale=0.1),
        Register(40002, "pressure",    unit="bar", scale=0.01),
        Register(40003, "battery",     unit="%"),
        Register(40004, "signal_strength", unit="dBm", store=False),  # noisy, exclude from historian
    ]
