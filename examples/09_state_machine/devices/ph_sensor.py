"""pH sensor with calibration mode registers."""
from scadable import Device, Register, modbus_rtu, every, SECONDS


class PHSensor(Device):
    id = "ph-tank-1"
    name = "Tank pH sensor"

    connection = modbus_rtu(port="/dev/ttyUSB1", baudrate=19200, slave=3)
    poll = every(2, SECONDS)

    registers = [
        Register(30001, "ph_value",  unit="pH", scale=0.01),
        Register(30002, "ph_raw",    unit="mV", scale=0.1),
        Register(40001, "cal_mode",  writable=True),   # 0=normal, 1=zero, 2=span
        Register(40002, "cal_point", writable=True),   # calibration reference value
    ]
