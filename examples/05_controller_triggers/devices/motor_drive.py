"""Motor VFD drive for trigger examples."""
from scadable import Device, Register, modbus_tcp, every, SECONDS, MINUTES


class MotorDrive(Device):
    id = "motor-1"
    name = "Main drive VFD"
    connection = modbus_tcp(host="${VFD_HOST}", port=502, slave=2)
    poll = every(1, SECONDS)
    historian = every(1, MINUTES)

    registers = [
        Register(30001, "speed",        unit="RPM"),
        Register(30002, "current",      unit="A",    scale=0.01),
        Register(30003, "vibration",    unit="mm/s", scale=0.001),
        Register(30004, "bearing_temp", unit="°C",   scale=0.1),
        Register(40001, "enable",       writable=True),
        Register(40002, "setpoint",     unit="RPM",  writable=True),
    ]
