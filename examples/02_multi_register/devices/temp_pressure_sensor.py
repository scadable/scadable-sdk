"""Modbus TCP temperature and pressure sensor.

Multiple registers with different units, scales, and access modes.
The historian stores all registers every 5 minutes (cloud-side).
"""
from scadable import Device, Register, modbus_tcp, every, SECONDS, MINUTES


class TempPressureSensor(Device):
    id = "line1-temp-pressure"
    name = "Main line sensor"

    connection = modbus_tcp(host="${SENSOR_HOST}", port=502, slave=1)
    poll = every(5, SECONDS)
    historian = every(5, MINUTES)

    registers = [
        Register(40001, "temperature", unit="°C", scale=0.1),
        Register(40002, "pressure",    unit="bar", scale=0.01),
        Register(40003, "flow_rate",   unit="L/min", scale=0.1, writable=True),
        Register(40004, "debug_flag",  store=False),  # excluded from historian
    ]
