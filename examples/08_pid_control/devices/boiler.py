"""Boiler with Modbus RTU control interface."""
from scadable import Device, Register, modbus_rtu, every, SECONDS, MINUTES


class Boiler(Device):
    id = "boiler-1"
    name = "Main boiler"

    connection = modbus_rtu(port="/dev/ttyUSB0", baudrate=9600, slave=2)
    poll = every(1, SECONDS)
    historian = every(1, MINUTES)

    registers = [
        Register(30001, "water_temp",  unit="°C", scale=0.1),
        Register(30002, "flue_temp",   unit="°C", scale=0.1),
        Register(30003, "flame_status"),
        Register(40001, "burner_pwm",  unit="%", writable=True),
        Register(40002, "target_temp", unit="°C", writable=True),
    ]
