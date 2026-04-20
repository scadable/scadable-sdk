"""Parser: Register descriptor extraction including dtype + on_error."""

from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

from scadable.compiler.parser import parse_devices


def _parse_one(tmp_path: Path, body: str) -> dict:
    f = tmp_path / "d.py"
    f.write_text(textwrap.dedent(body).lstrip())
    devs, _, _ = parse_devices([f])
    return devs[0]


# ── address → register type mapping ──────────────────────────────


@pytest.mark.parametrize("address,expected_type", [
    (1, "coil"),
    (9999, "coil"),
    (10000, "discrete_input"),
    (19999, "discrete_input"),
    (30000, "input"),
    (39999, "input"),
    (40001, "holding"),
    (49999, "holding"),
])
def test_register_address_maps_to_type(tmp_path, address, expected_type):
    dev = _parse_one(tmp_path, f"""
        from scadable import Device, Register, modbus_tcp
        class D(Device):
            id = "d"
            connection = modbus_tcp(host="x")
            registers = [Register({address}, "x")]
    """)
    assert dev["registers"][0]["type"] == expected_type


# ── dtype ────────────────────────────────────────────────────────


@pytest.mark.parametrize("dtype", [
    "uint16", "int16", "uint32", "int32", "float32", "float64", "bool",
])
def test_register_dtype_extracted(tmp_path, dtype):
    dev = _parse_one(tmp_path, f"""
        from scadable import Device, Register, modbus_tcp
        class D(Device):
            id = "d"
            connection = modbus_tcp(host="x")
            registers = [Register(40001, "x", dtype="{dtype}")]
    """)
    assert dev["registers"][0]["dtype"] == dtype


def test_register_dtype_defaults_to_uint16(tmp_path):
    dev = _parse_one(tmp_path, """
        from scadable import Device, Register, modbus_tcp
        class D(Device):
            id = "d"
            connection = modbus_tcp(host="x")
            registers = [Register(40001, "x")]
    """)
    assert dev["registers"][0]["dtype"] == "uint16"


# ── on_error ─────────────────────────────────────────────────────


@pytest.mark.parametrize("policy", ["skip", "last_known", "fail"])
def test_register_on_error_extracted(tmp_path, policy):
    dev = _parse_one(tmp_path, f"""
        from scadable import Device, Register, modbus_tcp
        class D(Device):
            id = "d"
            connection = modbus_tcp(host="x")
            registers = [Register(40001, "x", on_error="{policy}")]
    """)
    assert dev["registers"][0]["on_error"] == policy


def test_register_on_error_defaults_to_skip(tmp_path):
    dev = _parse_one(tmp_path, """
        from scadable import Device, Register, modbus_tcp
        class D(Device):
            id = "d"
            connection = modbus_tcp(host="x")
            registers = [Register(40001, "x")]
    """)
    assert dev["registers"][0]["on_error"] == "skip"


# ── endianness ───────────────────────────────────────────────────


def test_register_endianness_default_big(tmp_path):
    dev = _parse_one(tmp_path, """
        from scadable import Device, Register, modbus_tcp
        class D(Device):
            id = "d"
            connection = modbus_tcp(host="x")
            registers = [Register(40001, "x")]
    """)
    assert dev["registers"][0]["endianness"] == "big"


def test_register_endianness_little(tmp_path):
    dev = _parse_one(tmp_path, """
        from scadable import Device, Register, modbus_tcp
        class D(Device):
            id = "d"
            connection = modbus_tcp(host="x")
            registers = [Register(40001, "x", endianness="little")]
    """)
    assert dev["registers"][0]["endianness"] == "little"


# ── unit / scale ─────────────────────────────────────────────────


def test_register_unit_preserved(tmp_path):
    dev = _parse_one(tmp_path, """
        from scadable import Device, Register, modbus_tcp
        class D(Device):
            id = "d"
            connection = modbus_tcp(host="x")
            registers = [Register(40001, "t", unit="°C")]
    """)
    assert dev["registers"][0]["unit"] == "°C"


def test_register_scale_preserved(tmp_path):
    dev = _parse_one(tmp_path, """
        from scadable import Device, Register, modbus_tcp
        class D(Device):
            id = "d"
            connection = modbus_tcp(host="x")
            registers = [Register(40001, "t", scale=0.1)]
    """)
    assert dev["registers"][0]["scale"] == 0.1


# ── writable inference ──────────────────────────────────────────


def test_holding_register_writable_by_default(tmp_path):
    dev = _parse_one(tmp_path, """
        from scadable import Device, Register, modbus_tcp
        class D(Device):
            id = "d"
            connection = modbus_tcp(host="x")
            registers = [Register(40001, "x")]
    """)
    assert dev["registers"][0]["writable"] is True


def test_input_register_not_writable(tmp_path):
    dev = _parse_one(tmp_path, """
        from scadable import Device, Register, modbus_tcp
        class D(Device):
            id = "d"
            connection = modbus_tcp(host="x")
            registers = [Register(30001, "x")]
    """)
    assert dev["registers"][0]["writable"] is False


def test_explicit_writable_false_overrides(tmp_path):
    dev = _parse_one(tmp_path, """
        from scadable import Device, Register, modbus_tcp
        class D(Device):
            id = "d"
            connection = modbus_tcp(host="x")
            registers = [Register(40001, "x", writable=False)]
    """)
    assert dev["registers"][0]["writable"] is False


# ── multiple registers per device ───────────────────────────────


def test_multiple_registers(tmp_path):
    dev = _parse_one(tmp_path, """
        from scadable import Device, Register, modbus_tcp
        class D(Device):
            id = "d"
            connection = modbus_tcp(host="x")
            registers = [
                Register(40001, "a"),
                Register(40002, "b"),
                Register(40003, "c"),
            ]
    """)
    assert len(dev["registers"]) == 3
    assert [r["name"] for r in dev["registers"]] == ["a", "b", "c"]


# ── combined: dtype + on_error + endianness ─────────────────────


def test_register_all_v2_options_together(tmp_path):
    dev = _parse_one(tmp_path, """
        from scadable import Device, Register, modbus_tcp
        class D(Device):
            id = "d"
            connection = modbus_tcp(host="x")
            registers = [
                Register(40001, "t", dtype="float32", endianness="little",
                         on_error="last_known", unit="C", scale=0.5),
            ]
    """)
    r = dev["registers"][0]
    assert r["dtype"] == "float32"
    assert r["endianness"] == "little"
    assert r["on_error"] == "last_known"
    assert r["unit"] == "C"
    assert r["scale"] == 0.5
