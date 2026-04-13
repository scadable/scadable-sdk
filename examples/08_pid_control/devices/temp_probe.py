"""External temperature probe for feedback."""
from scadable import Device, Register, modbus_tcp, every, SECONDS


class TempProbe(Device):
    id = "probe-outlet"
    name = "Outlet temperature probe"

    connection = modbus_tcp(host="${PROBE_HOST}", port=502, slave=1)
    poll = every(1, SECONDS)

    registers = [
        Register(30001, "outlet_temp", unit="°C", scale=0.1),
    ]
