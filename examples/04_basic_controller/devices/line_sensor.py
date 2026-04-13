"""Production line sensor — reused across controller examples."""
from scadable import Device, Register, modbus_tcp, every, SECONDS, MINUTES


class LineSensor(Device):
    id = "line1-sensor"
    name = "Production line sensor"

    connection = modbus_tcp(host="${SENSOR_HOST}", port=502, slave=1)
    poll = every(5, SECONDS)
    historian = every(5, MINUTES)

    registers = [
        Register(40001, "temperature", unit="°C", scale=0.1),
        Register(40002, "pressure",    unit="bar", scale=0.01),
        Register(40003, "flow_rate",   unit="L/min", scale=0.1, writable=True),
    ]
