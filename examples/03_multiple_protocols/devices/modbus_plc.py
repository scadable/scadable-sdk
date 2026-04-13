"""Modbus TCP PLC — industrial programmable logic controller.

Demonstrates holding registers (read/write) and input registers
(read-only). Register address ranges determine access:
  30000-39999 = input registers (read-only)
  40000-49999 = holding registers (read/write)
"""
from scadable import Device, Register, modbus_tcp, every, SECONDS, MINUTES


class ModbusPLC(Device):
    id = "plc-line1"
    name = "Production line PLC"

    connection = modbus_tcp(host="${PLC_HOST}", port=502, slave=1)
    poll = every(1, SECONDS)
    historian = every(1, MINUTES)

    registers = [
        # Input registers (30xxx) — read-only sensor data
        Register(30001, "motor_speed",   unit="RPM"),
        Register(30002, "motor_current", unit="A",    scale=0.01),
        Register(30003, "conveyor_speed", unit="m/min", scale=0.1),

        # Holding registers (40xxx) — writable control values
        Register(40001, "speed_setpoint", unit="RPM", writable=True),
        Register(40002, "conveyor_enable", writable=True),
    ]
