"""Basic temperature sensor — simplest possible Scadable device.

One Modbus TCP device, one register. This is the "hello world"
of Scadable — the minimum needed to read a sensor and send data
to the cloud.
"""
from scadable import Device, Register, modbus_tcp, every, SECONDS


class TempSensor(Device):
    id = "temp-1"
    name = "Temperature sensor"

    connection = modbus_tcp(host="${SENSOR_HOST}", port=502, slave=1)
    poll = every(5, SECONDS)

    registers = [
        Register(40001, "temperature", unit="°C", scale=0.1),
    ]
