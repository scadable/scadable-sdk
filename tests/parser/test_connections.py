"""Parser: connection-block extraction across all 7 protocols."""

from __future__ import annotations

import textwrap
from pathlib import Path

from scadable.compiler.parser import parse_devices


def _parse(tmp_path: Path, body: str) -> dict:
    f = tmp_path / "d.py"
    f.write_text(textwrap.dedent(body).lstrip())
    devs, _, _ = parse_devices([f])
    return devs[0] if devs else {}


# ── modbus_tcp ───────────────────────────────────────────────────


def test_modbus_tcp_parses_host_port_slave(tmp_path):
    dev = _parse(tmp_path, """
        from scadable import Device, Register, modbus_tcp
        class D(Device):
            id = "d"
            connection = modbus_tcp(host="10.0.0.1", port=502, slave=3)
            registers = [Register(40001, "x")]
    """)
    assert dev["connection"]["protocol"] == "modbus_tcp"
    assert dev["connection"]["host"] == "10.0.0.1"
    assert dev["connection"]["port"] == 502
    assert dev["connection"]["slave"] == 3


def test_modbus_tcp_default_port(tmp_path):
    dev = _parse(tmp_path, """
        from scadable import Device, Register, modbus_tcp
        class D(Device):
            id = "d"
            connection = modbus_tcp(host="1.2.3.4")
            registers = [Register(40001, "x")]
    """)
    assert dev["connection"]["host"] == "1.2.3.4"


def test_modbus_tcp_env_var_host(tmp_path):
    dev = _parse(tmp_path, """
        from scadable import Device, Register, modbus_tcp
        class D(Device):
            id = "d"
            connection = modbus_tcp(host="${SENSOR_HOST}", port=502)
            registers = [Register(40001, "x")]
    """)
    assert dev["connection"]["host"] == "${SENSOR_HOST}"


# ── modbus_rtu ───────────────────────────────────────────────────


def test_modbus_rtu_parses_serial_params(tmp_path):
    dev = _parse(tmp_path, """
        from scadable import Device, Register, modbus_rtu
        class D(Device):
            id = "d"
            connection = modbus_rtu(port="/dev/ttyUSB0", baud=19200, slave=2)
            registers = [Register(40001, "x")]
    """)
    assert dev["connection"]["protocol"] == "modbus_rtu"
    assert dev["connection"]["port"] == "/dev/ttyUSB0"
    assert dev["connection"]["baud"] == 19200
    assert dev["connection"]["slave"] == 2


# ── ble ──────────────────────────────────────────────────────────


def test_ble_parses_mac(tmp_path):
    dev = _parse(tmp_path, """
        from scadable import Device, Characteristic, ble
        class D(Device):
            id = "d"
            connection = ble(mac="AA:BB:CC:DD:EE:FF")
            registers = [Characteristic("00002a37-0000-1000-8000-00805f9b34fb", "hr")]
    """)
    assert dev["connection"]["protocol"] == "ble"
    assert dev["connection"]["mac"] == "AA:BB:CC:DD:EE:FF"


# ── gpio ─────────────────────────────────────────────────────────


def test_gpio_no_params_required(tmp_path):
    dev = _parse(tmp_path, """
        from scadable import Device, Pin, gpio
        class D(Device):
            id = "d"
            connection = gpio()
            registers = [Pin(17, "led", mode="output")]
    """)
    assert dev["connection"]["protocol"] == "gpio"


# ── serial ───────────────────────────────────────────────────────


def test_serial_parses_port_baud(tmp_path):
    dev = _parse(tmp_path, """
        from scadable import Device, Field, serial
        class D(Device):
            id = "d"
            connection = serial(port="/dev/ttyS0", baud=115200)
            registers = [Field(0, 4, "header")]
    """)
    assert dev["connection"]["protocol"] == "serial"
    assert dev["connection"]["port"] == "/dev/ttyS0"
    assert dev["connection"]["baud"] == 115200


# ── i2c ──────────────────────────────────────────────────────────


def test_i2c_parses_address(tmp_path):
    dev = _parse(tmp_path, """
        from scadable import Device, Register, i2c
        class D(Device):
            id = "d"
            connection = i2c(bus=1, address=0x48)
            registers = [Register(40001, "x")]
    """)
    assert dev["connection"]["protocol"] == "i2c"


# ── rtsp ─────────────────────────────────────────────────────────


def test_rtsp_parses_url(tmp_path):
    dev = _parse(tmp_path, """
        from scadable import Device, Register, rtsp
        class D(Device):
            id = "d"
            connection = rtsp(url="rtsp://cam.local/stream")
            registers = [Register(40001, "x")]
    """)
    assert dev["connection"]["protocol"] == "rtsp"
    assert dev["connection"]["url"] == "rtsp://cam.local/stream"


# ── missing connection ───────────────────────────────────────────


def test_device_without_connection_still_parses(tmp_path):
    """Parser doesn't reject; validator flags missing connection later."""
    dev = _parse(tmp_path, """
        from scadable import Device, Register
        class D(Device):
            id = "d"
            registers = [Register(40001, "x")]
    """)
    assert dev["id"] == "d"
