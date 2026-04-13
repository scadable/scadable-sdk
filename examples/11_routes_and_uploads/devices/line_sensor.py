"""Line sensor for routes example."""
from scadable import Device, Register, modbus_tcp, every, SECONDS


class LineSensor(Device):
    id = "line1-sensor"
    connection = modbus_tcp(host="${SENSOR_HOST}", port=502, slave=1)
    poll = every(5, SECONDS)
    registers = [
        Register(40001, "temperature", unit="°C", scale=0.1),
    ]
