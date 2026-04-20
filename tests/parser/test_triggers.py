"""Parser: @on.* trigger decorator extraction on controllers."""

from __future__ import annotations

import textwrap
from pathlib import Path

from scadable.compiler.parser import parse_controllers, parse_devices


def _parse(tmp_path: Path, ctrl_body: str, dev_body: str | None = None) -> list[dict]:
    cfile = tmp_path / "c.py"
    cfile.write_text(textwrap.dedent(ctrl_body).lstrip())
    class_map: dict[str, str] = {}
    if dev_body:
        dfile = tmp_path / "d.py"
        dfile.write_text(textwrap.dedent(dev_body).lstrip())
        _, class_map, _ = parse_devices([dfile])
    ctrls, _ = parse_controllers([cfile], class_map)
    return ctrls[0]["triggers"] if ctrls else []


def test_on_interval_seconds(tmp_path):
    triggers = _parse(
        tmp_path,
        """
        from scadable import Controller, on, SECONDS
        class C(Controller):
            @on.interval(5, SECONDS)
            def tick(self):
                pass
    """,
    )
    assert triggers[0]["type"] == "interval"
    assert triggers[0]["interval_ms"] == 5000


def test_on_interval_minutes(tmp_path):
    triggers = _parse(
        tmp_path,
        """
        from scadable import Controller, on, MINUTES
        class C(Controller):
            @on.interval(2, MINUTES)
            def tick(self):
                pass
    """,
    )
    assert triggers[0]["interval_ms"] == 120_000


def test_on_interval_hours(tmp_path):
    triggers = _parse(
        tmp_path,
        """
        from scadable import Controller, on, HOURS
        class C(Controller):
            @on.interval(1, HOURS)
            def tick(self):
                pass
    """,
    )
    assert triggers[0]["interval_ms"] == 3_600_000


def test_on_interval_milliseconds(tmp_path):
    triggers = _parse(
        tmp_path,
        """
        from scadable import Controller, on, MILLISECONDS
        class C(Controller):
            @on.interval(500, MILLISECONDS)
            def tick(self):
                pass
    """,
    )
    assert triggers[0]["interval_ms"] == 500


def test_on_message_topic(tmp_path):
    triggers = _parse(
        tmp_path,
        """
        from scadable import Controller, on
        class C(Controller):
            @on.message("set_temperature")
            def handle(self, message):
                pass
    """,
    )
    assert triggers[0]["type"] == "message"
    assert triggers[0]["topic"] == "set_temperature"


def test_on_startup(tmp_path):
    triggers = _parse(
        tmp_path,
        """
        from scadable import Controller, on
        class C(Controller):
            @on.startup
            def init(self):
                pass
    """,
    )
    assert triggers[0]["type"] == "startup"


def test_on_shutdown(tmp_path):
    triggers = _parse(
        tmp_path,
        """
        from scadable import Controller, on
        class C(Controller):
            @on.shutdown
            def cleanup(self):
                pass
    """,
    )
    assert triggers[0]["type"] == "shutdown"


def test_multiple_triggers_per_controller(tmp_path):
    triggers = _parse(
        tmp_path,
        """
        from scadable import Controller, on, SECONDS
        class C(Controller):
            @on.interval(1, SECONDS)
            def t1(self): pass
            @on.interval(5, SECONDS)
            def t2(self): pass
            @on.startup
            def t3(self): pass
    """,
    )
    assert len(triggers) == 3
    types = [t["type"] for t in triggers]
    assert "interval" in types and "startup" in types


def test_method_name_carried_through(tmp_path):
    triggers = _parse(
        tmp_path,
        """
        from scadable import Controller, on, SECONDS
        class C(Controller):
            @on.interval(1, SECONDS)
            def my_specific_method(self):
                pass
    """,
    )
    assert triggers[0]["method"] == "my_specific_method"


def test_controller_without_triggers(tmp_path):
    triggers = _parse(
        tmp_path,
        """
        from scadable import Controller
        class C(Controller):
            pass
    """,
    )
    assert triggers == []


def test_on_threshold_field(tmp_path):
    triggers = _parse(
        tmp_path,
        """
        from scadable import Controller, on
        from devices.s import S
        class C(Controller):
            @on.threshold(S.temperature, above=80)
            def hot(self):
                pass
    """,
        """
        from scadable import Device, Register, modbus_tcp
        class S(Device):
            id = "s"
            connection = modbus_tcp(host="x")
            registers = [Register(40001, "temperature")]
    """,
    )
    assert triggers[0]["type"] == "threshold"


def test_on_change_field(tmp_path):
    triggers = _parse(
        tmp_path,
        """
        from scadable import Controller, on
        from devices.s import S
        class C(Controller):
            @on.change(S.temperature)
            def changed(self):
                pass
    """,
        """
        from scadable import Device, Register, modbus_tcp
        class S(Device):
            id = "s"
            connection = modbus_tcp(host="x")
            registers = [Register(40001, "temperature")]
    """,
    )
    assert triggers[0]["type"] == "change"
