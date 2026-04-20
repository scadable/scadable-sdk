"""Parser: edge cases — empty file, syntax error, missing base class, etc."""

from __future__ import annotations

from pathlib import Path

from scadable.compiler.parser import parse_devices, parse_controllers


def _write(path: Path, body: str) -> Path:
    path.write_text(body)
    return path


def test_empty_file_returns_no_devices(tmp_path):
    f = _write(tmp_path / "empty.py", "")
    devs, _, warnings = parse_devices([f])
    assert devs == []
    assert warnings == []


def test_syntax_error_surfaces_warning_not_silent(tmp_path):
    """Regression guard for the v0.1 silent-skip bug."""
    f = _write(tmp_path / "broken.py", "this is not python {{{")
    devs, _, warnings = parse_devices([f])
    assert devs == []
    assert len(warnings) == 1
    assert "broken.py" in warnings[0]
    assert "SyntaxError" in warnings[0]


def test_class_without_device_base_skipped(tmp_path):
    f = _write(tmp_path / "x.py", "class NotADevice:\n    id = 'x'\n")
    devs, _, _ = parse_devices([f])
    assert devs == []


def test_multiple_devices_in_one_file(tmp_path):
    f = _write(tmp_path / "many.py", """
from scadable import Device, Register, modbus_tcp

class A(Device):
    id = "a"
    connection = modbus_tcp(host="x")
    registers = [Register(40001, "x")]

class B(Device):
    id = "b"
    connection = modbus_tcp(host="y")
    registers = [Register(40002, "y")]
""")
    devs, class_map, _ = parse_devices([f])
    assert len(devs) == 2
    assert {d["id"] for d in devs} == {"a", "b"}
    assert "A" in class_map and "B" in class_map


def test_controller_syntax_error_surfaces_warning(tmp_path):
    f = _write(tmp_path / "ctrl_broken.py", "def )))(")
    ctrls, warnings = parse_controllers([f], {})
    assert ctrls == []
    assert len(warnings) == 1
    assert "SyntaxError" in warnings[0]


def test_class_without_id_attribute(tmp_path):
    """Device with no `id` attribute is skipped silently — id is required."""
    f = _write(tmp_path / "noid.py", """
from scadable import Device, Register, modbus_tcp

class D(Device):
    connection = modbus_tcp(host="x")
    registers = [Register(40001, "x")]
""")
    devs, _, _ = parse_devices([f])
    # No id → no device emitted (or device with empty id; both acceptable)
    assert all(d.get("id") for d in devs) or devs == []


def test_imports_dont_become_devices(tmp_path):
    f = _write(tmp_path / "imp.py", """
from scadable import Device, Register, modbus_tcp
from some.other.module import SomeClass

class Real(Device):
    id = "real"
    connection = modbus_tcp(host="x")
    registers = [Register(40001, "x")]
""")
    devs, _, _ = parse_devices([f])
    assert len(devs) == 1
    assert devs[0]["id"] == "real"


def test_warnings_accumulate_across_files(tmp_path):
    bad1 = _write(tmp_path / "bad1.py", "}}}")
    bad2 = _write(tmp_path / "bad2.py", "{{{")
    _, _, warnings = parse_devices([bad1, bad2])
    assert len(warnings) == 2
