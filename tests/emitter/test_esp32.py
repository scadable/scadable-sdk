"""ESP32 emitter — schedules[] lowering + supported/unsupported shapes.

Round-trip tests: write a small Python controller file, drive
compile_project() against it with target='esp32', read back the
manifest, assert it matches the chip-side handlers/schedules.rs
contract.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from scadable.compiler import compile_project
from scadable.compiler.emitter.esp32 import Esp32UnsupportedError


def _write_project(tmp_path: Path, controller_src: str) -> Path:
    """Write a minimal scadable project with one controller file."""
    proj = tmp_path / "demo"
    proj.mkdir()
    # Project metadata picked up by discover_project — minimal shape.
    (proj / "scadable.toml").write_text(
        '[project]\nname = "esp-heartbeat"\nversion = "1.0.0"\n'
    )
    controllers_dir = proj / "controllers"
    controllers_dir.mkdir()
    (controllers_dir / "__init__.py").write_text("")
    (controllers_dir / "main.py").write_text(controller_src)
    return proj


def _compile_esp(tmp_path: Path, controller_src: str):
    proj = _write_project(tmp_path, controller_src)
    return compile_project(proj, target="esp32", output_dir=proj / "out")


# ---------------- happy paths ---------------------------------------


def test_interval_publish_lowers_to_schedule(tmp_path):
    src = """
from scadable import Controller, on, SECONDS

class HeartbeatDemo(Controller):
    @on.interval(5, SECONDS)
    def emit(self):
        self.publish("data/temperature", {"value": random(20, 30)})
"""
    result = _compile_esp(tmp_path, src)
    assert result.errors == [], result.errors
    manifest = json.loads(result.manifest_path.read_text())
    assert manifest["target"] == "esp32"
    schedules = manifest["schedules"]
    assert len(schedules) == 1
    s = schedules[0]
    assert s["id"] == "HeartbeatDemo.emit"
    assert s["interval_ms"] == 5000
    assert s["topic_suffix"] == "data/temperature"
    assert s["payload"] == {
        "value": {"kind": "random", "min": 20.0, "max": 30.0}
    }


def test_milliseconds_unit_lowers_to_ms(tmp_path):
    src = """
from scadable import Controller, on, MILLISECONDS

class FastTick(Controller):
    @on.interval(500, MILLISECONDS)
    def tick(self):
        self.publish("data/tick", {"n": counter()})
"""
    result = _compile_esp(tmp_path, src)
    assert result.errors == [], result.errors
    s = json.loads(result.manifest_path.read_text())["schedules"][0]
    assert s["interval_ms"] == 500
    assert s["payload"]["n"] == {"kind": "counter"}


def test_constant_payload_kinds(tmp_path):
    src = """
from scadable import Controller, on, SECONDS

class ConstDemo(Controller):
    @on.interval(10, SECONDS)
    def emit(self):
        self.publish("data/sample", {"label": "hello", "n": 42, "active": True})
"""
    result = _compile_esp(tmp_path, src)
    assert result.errors == [], result.errors
    s = json.loads(result.manifest_path.read_text())["schedules"][0]
    assert s["payload"]["label"] == {"kind": "constant", "value": "hello"}
    assert s["payload"]["n"] == {"kind": "constant", "value": 42}
    assert s["payload"]["active"] == {"kind": "constant", "value": True}


def test_timestamp_payload_kind(tmp_path):
    src = """
from scadable import Controller, on, SECONDS

class TsDemo(Controller):
    @on.interval(60, SECONDS)
    def emit(self):
        self.publish("data/ts", {"t": timestamp_unix_ms()})
"""
    result = _compile_esp(tmp_path, src)
    assert result.errors == [], result.errors
    s = json.loads(result.manifest_path.read_text())["schedules"][0]
    assert s["payload"]["t"] == {"kind": "timestamp_unix_ms"}


def test_bundle_is_raw_manifest_not_targz(tmp_path):
    """ESP bundle.tar.gz contains raw manifest.json bytes — see emitter
    docstring for the rationale (Xtensa tar+gz dep cost). The chip's
    release.rs JSON-decodes the body directly."""
    src = """
from scadable import Controller, on, SECONDS

class B(Controller):
    @on.interval(1, SECONDS)
    def t(self):
        self.publish("x", {"v": 1})
"""
    result = _compile_esp(tmp_path, src)
    assert result.errors == [], result.errors
    body = result.bundle_path.read_bytes()
    parsed = json.loads(body)
    assert parsed["target"] == "esp32"
    assert parsed["schedules"][0]["topic_suffix"] == "x"


# ---------------- rejections ----------------------------------------


def test_self_actuate_rejected(tmp_path):
    src = """
from scadable import Controller, on, SECONDS

class BadActuator(Controller):
    @on.interval(5, SECONDS)
    def step(self):
        self.actuate("door.open", True)
"""
    result = _compile_esp(tmp_path, src)
    assert result.errors, "expected an error for self.actuate"
    assert "actuate" in result.errors[0]


def test_self_upload_rejected(tmp_path):
    src = """
from scadable import Controller, on, SECONDS

class BadUploader(Controller):
    @on.interval(5, SECONDS)
    def push(self):
        self.upload("snapshots", b"jpeg-bytes")
"""
    result = _compile_esp(tmp_path, src)
    assert result.errors
    assert "upload" in result.errors[0]


def test_multi_statement_body_rejected(tmp_path):
    src = """
from scadable import Controller, on, SECONDS

class TwoStatements(Controller):
    @on.interval(5, SECONDS)
    def fat(self):
        x = 5
        self.publish("data/x", {"x": x})
"""
    result = _compile_esp(tmp_path, src)
    assert result.errors
    assert "exactly one" in result.errors[0]


def test_non_interval_decorator_rejected(tmp_path):
    src = """
from scadable import Controller, on

class ThresholdDemo(Controller):
    @on.threshold("device.temp", above=80)
    def hot(self):
        self.publish("alerts/hot", {"reason": "overheat"})
"""
    result = _compile_esp(tmp_path, src)
    assert result.errors
    assert "@on.threshold" in result.errors[0] or "threshold" in result.errors[0]


def test_topic_starting_with_slash_rejected(tmp_path):
    src = """
from scadable import Controller, on, SECONDS

class BadTopic(Controller):
    @on.interval(5, SECONDS)
    def emit(self):
        self.publish("/data/temperature", {"v": 1})
"""
    result = _compile_esp(tmp_path, src)
    assert result.errors
    assert "topic" in result.errors[0]


def test_unsupported_payload_value_rejected(tmp_path):
    """A bare variable (not a literal / supported call / descriptor)
    can't be lowered to a ValueDescriptor."""
    src = """
from scadable import Controller, on, SECONDS

class WeirdPayload(Controller):
    @on.interval(5, SECONDS)
    def emit(self):
        self.publish("data/x", {"v": some_var_that_doesnt_exist})
"""
    result = _compile_esp(tmp_path, src)
    assert result.errors
    assert "payload value" in result.errors[0]


def test_interval_unit_must_be_known(tmp_path):
    src = """
from scadable import Controller, on

class WeirdUnit(Controller):
    @on.interval(5, "FORTNIGHTS")
    def emit(self):
        self.publish("data/x", {"v": 1})
"""
    result = _compile_esp(tmp_path, src)
    assert result.errors
    assert "FORTNIGHTS" in result.errors[0] or "unit" in result.errors[0]


# ---------------- W8: lifecycle + mqtt subscriptions ----------------


def test_on_startup_lowers_to_lifecycle_startup(tmp_path):
    """@on.startup methods land in manifest.lifecycle.startup[] with a
    publishes[] mirroring the schedule's payload descriptor shape."""
    src = """
from scadable import Controller, on

class BootDemo(Controller):
    @on.startup
    def init(self):
        self.publish("status/boot", {"v": 1})
"""
    result = _compile_esp(tmp_path, src)
    assert result.errors == [], result.errors
    manifest = json.loads(result.manifest_path.read_text())
    startup = manifest["lifecycle"]["startup"]
    assert len(startup) == 1
    entry = startup[0]
    assert entry["controller"] == "BootDemo"
    assert entry["method"] == "init"
    assert entry["publishes"] == [
        {
            "topic_suffix": "status/boot",
            "payload": {"v": {"kind": "constant", "value": 1}},
        }
    ]
    # No interval methods → no schedules; mqtt_subscriptions empty.
    assert manifest["schedules"] == []
    assert manifest["mqtt_subscriptions"] == []


def test_on_shutdown_lowers_to_lifecycle_shutdown(tmp_path):
    src = """
from scadable import Controller, on

class ShutdownDemo(Controller):
    @on.shutdown
    def teardown(self):
        self.publish("status/halt", {"reason": "graceful"})
"""
    result = _compile_esp(tmp_path, src)
    assert result.errors == [], result.errors
    manifest = json.loads(result.manifest_path.read_text())
    shutdown = manifest["lifecycle"]["shutdown"]
    assert len(shutdown) == 1
    entry = shutdown[0]
    assert entry["controller"] == "ShutdownDemo"
    assert entry["method"] == "teardown"
    assert entry["publishes"][0]["topic_suffix"] == "status/halt"
    assert entry["publishes"][0]["payload"] == {
        "reason": {"kind": "constant", "value": "graceful"}
    }
    assert manifest["lifecycle"]["startup"] == []


def test_on_message_lowers_to_subscription(tmp_path):
    src = """
from scadable import Controller, on

class CmdDemo(Controller):
    @on.message(topic="cmd/restart")
    def on_restart(self):
        self.publish("status/ack", {"cmd": "restart"})
"""
    result = _compile_esp(tmp_path, src)
    assert result.errors == [], result.errors
    manifest = json.loads(result.manifest_path.read_text())
    subs = manifest["mqtt_subscriptions"]
    assert len(subs) == 1
    sub = subs[0]
    assert sub["topic_suffix"] == "cmd/restart"
    assert sub["controller"] == "CmdDemo"
    assert sub["method"] == "on_restart"
    assert sub["publishes"] == [
        {
            "topic_suffix": "status/ack",
            "payload": {"cmd": {"kind": "constant", "value": "restart"}},
        }
    ]


def test_startup_with_multiple_publishes(tmp_path):
    """Multiple self.publish calls in sequence are allowed in lifecycle
    handlers — the firmware fires them in source order."""
    src = """
from scadable import Controller, on

class BootChatty(Controller):
    @on.startup
    def init(self):
        self.publish("status/boot", {"phase": "starting"})
        self.publish("status/version", {"v": 1})
        self.publish("status/ready", {"phase": "ready"})
"""
    result = _compile_esp(tmp_path, src)
    assert result.errors == [], result.errors
    manifest = json.loads(result.manifest_path.read_text())
    publishes = manifest["lifecycle"]["startup"][0]["publishes"]
    assert len(publishes) == 3
    assert [p["topic_suffix"] for p in publishes] == [
        "status/boot",
        "status/version",
        "status/ready",
    ]
    assert publishes[0]["payload"]["phase"] == {"kind": "constant", "value": "starting"}


def test_lifecycle_methods_alongside_interval(tmp_path):
    """A controller can mix @on.interval (→ schedules[]) with
    @on.startup (→ lifecycle.startup[]); both lower correctly."""
    src = """
from scadable import Controller, on, SECONDS

class Mixed(Controller):
    @on.startup
    def init(self):
        self.publish("status/boot", {"v": 1})

    @on.interval(5, SECONDS)
    def tick(self):
        self.publish("data/tick", {"n": counter()})
"""
    result = _compile_esp(tmp_path, src)
    assert result.errors == [], result.errors
    manifest = json.loads(result.manifest_path.read_text())

    schedules = manifest["schedules"]
    assert len(schedules) == 1
    assert schedules[0]["id"] == "Mixed.tick"
    assert schedules[0]["interval_ms"] == 5000

    startup = manifest["lifecycle"]["startup"]
    assert len(startup) == 1
    assert startup[0]["method"] == "init"
    assert startup[0]["publishes"][0]["topic_suffix"] == "status/boot"


# ---------------- W8: rejections ------------------------------------


def test_on_startup_with_actuate_raises(tmp_path):
    src = """
from scadable import Controller, on

class BadBoot(Controller):
    @on.startup
    def init(self):
        self.actuate("relay.on", True)
"""
    result = _compile_esp(tmp_path, src)
    assert result.errors, "expected an error for self.actuate in @on.startup"
    assert "actuate" in result.errors[0]


def test_on_startup_with_conditional_raises(tmp_path):
    """Bodies must be a flat sequence of self.publish calls — `if`/`for`
    aren't lowerable."""
    src = """
from scadable import Controller, on

class BranchyBoot(Controller):
    @on.startup
    def init(self):
        if True:
            self.publish("status/boot", {"v": 1})
"""
    result = _compile_esp(tmp_path, src)
    assert result.errors, "expected an error for `if` inside @on.startup body"
    msg = result.errors[0]
    # Either name the construct (If) or the rule it violated — both
    # acceptable as long as the user sees the specific node type.
    assert "If" in msg or "self.publish" in msg


def test_on_message_without_topic_kwarg_raises(tmp_path):
    """@on.message() with no topic at all → clear refusal naming the
    missing kwarg."""
    src = """
from scadable import Controller, on

class NoTopic(Controller):
    @on.message()
    def on_anything(self):
        self.publish("status/ack", {"v": 1})
"""
    result = _compile_esp(tmp_path, src)
    assert result.errors, "expected an error for @on.message() with no topic"
    assert "topic" in result.errors[0]
