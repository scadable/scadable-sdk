"""ESP32 emitter — schedules[] lowering + supported/unsupported shapes.

Round-trip tests: write a small Python controller file, drive
compile_project() against it with target='esp32', read back the
manifest, assert it matches the chip-side handlers/schedules.rs
contract.
"""

from __future__ import annotations

import json
from pathlib import Path

from scadable.compiler import compile_project


def _write_project(tmp_path: Path, controller_src: str) -> Path:
    """Write a minimal scadable project with one controller file."""
    proj = tmp_path / "demo"
    proj.mkdir()
    # Project metadata picked up by discover_project — minimal shape.
    (proj / "scadable.toml").write_text('[project]\nname = "esp-heartbeat"\nversion = "1.0.0"\n')
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
    assert s["payload"] == {"value": {"kind": "random", "min": 20.0, "max": 30.0}}


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
    assert entry["publishes"][0]["payload"] == {"reason": {"kind": "constant", "value": "graceful"}}
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


def test_on_message_with_message_field_binding(tmp_path):
    """`message_field("path")` in an @on.message publish lowers to a
    MessageField ValueDescriptor that the chip resolves against the
    parsed inbound JSON payload at dispatch time."""
    src = """
from scadable import Controller, on

class Switch(Controller):
    @on.message(topic="cmd/setpoint")
    def on_setpoint(self):
        self.publish("events/setpoint_ack", {
            "received": message_field("value"),
            "unit": message_field("unit"),
        })
"""
    result = _compile_esp(tmp_path, src)
    assert result.errors == [], result.errors
    manifest = json.loads(result.manifest_path.read_text())
    subs = manifest["mqtt_subscriptions"]
    assert len(subs) == 1
    pub = subs[0]["publishes"][0]
    assert pub["topic_suffix"] == "events/setpoint_ack"
    assert pub["payload"] == {
        "received": {"kind": "message_field", "path": "value"},
        "unit": {"kind": "message_field", "path": "unit"},
    }


def test_message_field_requires_string_literal(tmp_path):
    """`message_field()` with a non-string or missing arg is rejected at
    compile time so the user gets a clean error rather than a chip-side
    parse failure later."""
    src = """
from scadable import Controller, on

class BadField(Controller):
    @on.message(topic="cmd/setpoint")
    def on_setpoint(self):
        self.publish("events/ack", {"x": message_field()})
"""
    result = _compile_esp(tmp_path, src)
    assert result.errors, "expected compile error for message_field() with no args"


# ---------------- v0.4 channel model — command= form + message.field --


def test_on_message_command_kwarg_lowers_to_cmd_topic(tmp_path):
    """v0.4: @on.message(command="X") is the canonical form. SDK derives
    topic_suffix=cmd/X, emits both the user-facing command name and the
    chip-facing topic in the manifest."""
    src = """
from scadable import Controller, on

class Switch(Controller):
    @on.message(command="set_temperature")
    def on_setpoint(self):
        self.publish("events/setpoint_ack", {"received": message.value})
"""
    result = _compile_esp(tmp_path, src)
    assert result.errors == [], result.errors
    manifest = json.loads(result.manifest_path.read_text())
    subs = manifest["mqtt_subscriptions"]
    assert len(subs) == 1
    sub = subs[0]
    assert sub["command"] == "set_temperature"
    assert sub["topic_suffix"] == "cmd/set_temperature"
    assert sub["controller"] == "Switch"
    assert sub["publishes"][0]["payload"]["received"] == {
        "kind": "message_field",
        "path": "value",
    }


def test_on_message_command_kwarg_with_requires_role(tmp_path):
    """requires_role is forwarded into the manifest so cloud-side auth
    can gate the command at the API layer."""
    src = """
from scadable import Controller, on

class HVAC(Controller):
    @on.message(command="set_temperature", requires_role="operator")
    def on_setpoint(self):
        self.publish("events/setpoint_ack", {"received": message.value})
"""
    result = _compile_esp(tmp_path, src)
    assert result.errors == [], result.errors
    sub = json.loads(result.manifest_path.read_text())["mqtt_subscriptions"][0]
    assert sub["command"] == "set_temperature"
    assert sub["topic_suffix"] == "cmd/set_temperature"
    assert sub["requires_role"] == "operator"


def test_on_message_command_with_slash_rejected(tmp_path):
    """command= shouldn't carry topic separators — the cmd/ prefix is
    auto-derived. Catching this at compile time avoids two-topic-for-one-
    command surprises."""
    src = """
from scadable import Controller, on

class BadCmd(Controller):
    @on.message(command="cmd/set_temperature")
    def on_setpoint(self):
        self.publish("events/ack", {"x": 1})
"""
    result = _compile_esp(tmp_path, src)
    assert result.errors, "expected compile error for slash in command name"


def test_on_message_legacy_topic_kwarg_still_works(tmp_path):
    """Backwards compat: @on.message(topic="cmd/X") continues to work for
    v0.3.x controllers. SDK derives the command name by stripping cmd/."""
    src = """
from scadable import Controller, on

class Legacy(Controller):
    @on.message(topic="cmd/restart")
    def on_restart(self):
        self.publish("status/ack", {"cmd": "restart"})
"""
    result = _compile_esp(tmp_path, src)
    assert result.errors == [], result.errors
    sub = json.loads(result.manifest_path.read_text())["mqtt_subscriptions"][0]
    assert sub["topic_suffix"] == "cmd/restart"
    assert sub["command"] == "restart"


def test_send_data_lowers_to_data_topic_with_channel(tmp_path):
    """v0.4: self.send_data("temp", {...}) → topic data/temp + channel=data.
    User picks a name; SDK derives the topic + tags the channel."""
    src = """
from scadable import Controller, on, SECONDS

class Telemetry(Controller):
    @on.interval(5, SECONDS)
    def emit(self):
        self.send_data("temperature", {"value": random(20, 30)})
"""
    result = _compile_esp(tmp_path, src)
    assert result.errors == [], result.errors
    s = json.loads(result.manifest_path.read_text())["schedules"][0]
    assert s["topic_suffix"] == "data/temperature"
    assert s["payload"]["value"] == {"kind": "random", "min": 20.0, "max": 30.0}


def test_send_event_lowers_to_event_topic_with_channel(tmp_path):
    src = """
from scadable import Controller, on

class Door(Controller):
    @on.startup
    def opened(self):
        self.send_event("door_opened", {"who": "RFID-42"})
"""
    result = _compile_esp(tmp_path, src)
    assert result.errors == [], result.errors
    entry = json.loads(result.manifest_path.read_text())["lifecycle"]["startup"][0]
    pub = entry["publishes"][0]
    assert pub["topic_suffix"] == "event/door_opened"
    assert pub["channel"] == "events"


def test_send_alert_lowers_to_alert_topic_with_channel(tmp_path):
    src = """
from scadable import Controller, on, SECONDS

class Battery(Controller):
    @on.interval(60, SECONDS)
    def check(self):
        self.send_alert("low_battery", {"voltage": 2.7})
"""
    result = _compile_esp(tmp_path, src)
    assert result.errors == [], result.errors
    s = json.loads(result.manifest_path.read_text())["schedules"][0]
    assert s["topic_suffix"] == "alert/low_battery"
    assert s["payload"]["voltage"] == {"kind": "constant", "value": 2.7}


def test_send_verb_rejects_slash_in_name(tmp_path):
    """User picks a name, not a topic — slashes would create unintended
    sub-topics. Caught at compile time so the manifest stays clean."""
    src = """
from scadable import Controller, on, SECONDS

class BadName(Controller):
    @on.interval(5, SECONDS)
    def emit(self):
        self.send_data("nested/path", {"v": 1})
"""
    result = _compile_esp(tmp_path, src)
    assert result.errors, "expected compile error for slash in send_data name"


def test_legacy_publish_still_works_no_channel_field(tmp_path):
    """Backwards compat: self.publish("topic", payload) is unchanged.
    No `channel` field — chip + cloud should treat absent channel as
    `data` for routing decisions, but the manifest preserves the user's
    intent (raw publish, no channel-tagging)."""
    src = """
from scadable import Controller, on, SECONDS

class Legacy(Controller):
    @on.interval(5, SECONDS)
    def emit(self):
        self.publish("data/raw", {"v": 1})
"""
    result = _compile_esp(tmp_path, src)
    assert result.errors == [], result.errors
    s = json.loads(result.manifest_path.read_text())["schedules"][0]
    assert s["topic_suffix"] == "data/raw"
    assert "channel" not in s  # legacy path doesn't tag channel


# ---------------- v0.4 conditionals — if/elif/else --------------------


def test_if_else_in_on_message_lowers_to_branched_publishes(tmp_path):
    """The headline use-case: branch on inbound message field."""
    src = """
from scadable import Controller, on

class HVAC(Controller):
    @on.message(command="check_temp")
    def check(self):
        if message.value > 30:
            self.send_alert("too_hot", {"temp": message.value})
        else:
            self.send_data("temp_ok", {"temp": message.value})
"""
    result = _compile_esp(tmp_path, src)
    assert result.errors == [], result.errors
    sub = json.loads(result.manifest_path.read_text())["mqtt_subscriptions"][0]
    assert len(sub["publishes"]) == 1
    branch = sub["publishes"][0]
    assert branch["if"] == {
        "kind": "compare",
        "left": {"kind": "message_field", "path": "value"},
        "op": "gt",
        "right": {"kind": "constant", "value": 30},
    }
    assert branch["then"][0]["topic_suffix"] == "alert/too_hot"
    assert branch["then"][0]["channel"] == "alerts"
    assert branch["else"][0]["topic_suffix"] == "data/temp_ok"
    assert branch["else"][0]["channel"] == "data"


def test_if_without_else_lowers_with_empty_else(tmp_path):
    """`if x: ...` (no else) → empty else list. Chip treats empty else as no-op."""
    src = """
from scadable import Controller, on

class Watchdog(Controller):
    @on.message(command="check")
    def check(self):
        if message.value == 0:
            self.send_alert("zero", {"saw": "zero"})
"""
    result = _compile_esp(tmp_path, src)
    assert result.errors == [], result.errors
    branch = json.loads(result.manifest_path.read_text())["mqtt_subscriptions"][0]["publishes"][0]
    assert len(branch["then"]) == 1
    assert branch["else"] == []


def test_elif_lowers_to_nested_if(tmp_path):
    """Python parses `elif` as `else: [If(...)]`. SDK lowers naturally."""
    src = """
from scadable import Controller, on

class HVAC(Controller):
    @on.message(command="check")
    def check(self):
        if message.value > 80:
            self.send_alert("high", {"v": message.value})
        elif message.value > 60:
            self.send_alert("mid", {"v": message.value})
        else:
            self.send_data("low", {"v": message.value})
"""
    result = _compile_esp(tmp_path, src)
    assert result.errors == [], result.errors
    outer = json.loads(result.manifest_path.read_text())["mqtt_subscriptions"][0]["publishes"][0]
    # outer if: > 80 → alert/high
    assert outer["if"]["op"] == "gt"
    assert outer["if"]["right"] == {"kind": "constant", "value": 80}
    assert outer["then"][0]["topic_suffix"] == "alert/high"
    # else contains a nested if (the elif)
    assert len(outer["else"]) == 1
    inner = outer["else"][0]
    assert inner["if"]["right"] == {"kind": "constant", "value": 60}
    assert inner["then"][0]["topic_suffix"] == "alert/mid"
    assert inner["else"][0]["topic_suffix"] == "data/low"


def test_compare_ops_lower_correctly(tmp_path):
    """All six comparison ops map to their wire names."""
    src = """
from scadable import Controller, on

class Allops(Controller):
    @on.message(command="check")
    def check(self):
        if message.a == 1:
            self.send_event("eq", {})
        if message.a != 2:
            self.send_event("ne", {})
        if message.a < 3:
            self.send_event("lt", {})
        if message.a <= 4:
            self.send_event("lte", {})
        if message.a > 5:
            self.send_event("gt", {})
        if message.a >= 6:
            self.send_event("gte", {})
"""
    result = _compile_esp(tmp_path, src)
    assert result.errors == [], result.errors
    publishes = json.loads(result.manifest_path.read_text())["mqtt_subscriptions"][0]["publishes"]
    ops = [p["if"]["op"] for p in publishes]
    assert ops == ["eq", "ne", "lt", "lte", "gt", "gte"]


def test_and_or_not_lower_to_composites(tmp_path):
    src = """
from scadable import Controller, on

class Bools(Controller):
    @on.message(command="check")
    def check(self):
        if message.a > 1 and message.b < 5:
            self.send_event("and_branch", {})
        if message.a > 1 or message.b < 5:
            self.send_event("or_branch", {})
        if not message.flag:
            self.send_event("not_branch", {})
"""
    result = _compile_esp(tmp_path, src)
    assert result.errors == [], result.errors
    publishes = json.loads(result.manifest_path.read_text())["mqtt_subscriptions"][0]["publishes"]
    assert publishes[0]["if"]["kind"] == "and"
    assert len(publishes[0]["if"]["conditions"]) == 2
    assert publishes[1]["if"]["kind"] == "or"
    assert publishes[2]["if"]["kind"] == "not"


def test_truthy_bare_value_condition(tmp_path):
    """`if message.flag:` (no operator) → Truthy condition wrapping the value."""
    src = """
from scadable import Controller, on

class Truthy(Controller):
    @on.message(command="check")
    def check(self):
        if message.alarm:
            self.send_alert("fire", {"src": message.source})
"""
    result = _compile_esp(tmp_path, src)
    assert result.errors == [], result.errors
    branch = json.loads(result.manifest_path.read_text())["mqtt_subscriptions"][0]["publishes"][0]
    assert branch["if"] == {
        "kind": "truthy",
        "value": {"kind": "message_field", "path": "alarm"},
    }


def test_chained_compare_rejected_with_clear_error(tmp_path):
    """`a < b < c` is too clever for the lowering today — rejected with
    a hint to split."""
    src = """
from scadable import Controller, on

class Chained(Controller):
    @on.message(command="check")
    def check(self):
        if 1 < message.value < 10:
            self.send_event("in_range", {})
"""
    result = _compile_esp(tmp_path, src)
    assert result.errors, "expected compile error for chained comparison"
    assert "chained" in result.errors[0].lower()


def test_assignment_in_body_still_rejected(tmp_path):
    """Defensive: existing rejection of variable assignment must keep
    working — the new if-handling path doesn't accidentally let
    `x = 5` through."""
    src = """
from scadable import Controller, on

class BadAssign(Controller):
    @on.message(command="check")
    def check(self):
        x = message.value
        self.send_data("temp", {"v": x})
"""
    result = _compile_esp(tmp_path, src)
    assert result.errors, "assignment should still be rejected"


def test_if_in_lifecycle_handler_works(tmp_path):
    """Conditional publishes also work in @on.startup / @on.shutdown
    (no inbound — Truthy/MessageField resolves to null on chip)."""
    src = """
from scadable import Controller, on

class Boot(Controller):
    @on.startup
    def init(self):
        if counter() == 0:
            self.send_event("first_boot", {"hello": "world"})
        else:
            self.send_event("rebooted", {})
"""
    result = _compile_esp(tmp_path, src)
    assert result.errors == [], result.errors
    actions = json.loads(result.manifest_path.read_text())["lifecycle"]["startup"][0]["publishes"]
    assert len(actions) == 1
    assert actions[0]["if"]["kind"] == "compare"


def test_message_attribute_access_lowers_like_message_field(tmp_path):
    """message.value is sugar for message_field("value"). Mixed use in
    the same payload should produce identical descriptors."""
    src = """
from scadable import Controller, on

class Echo(Controller):
    @on.message(command="echo")
    def on_echo(self):
        self.publish("events/echoed", {
            "via_attr": message.value,
            "via_func": message_field("value"),
            "literal": "constant",
        })
"""
    result = _compile_esp(tmp_path, src)
    assert result.errors == [], result.errors
    payload = json.loads(result.manifest_path.read_text())["mqtt_subscriptions"][0]["publishes"][0][
        "payload"
    ]
    assert payload["via_attr"] == {"kind": "message_field", "path": "value"}
    assert payload["via_func"] == {"kind": "message_field", "path": "value"}
    assert payload["literal"] == {"kind": "constant", "value": "constant"}


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


def test_on_startup_with_for_loop_still_rejected(tmp_path):
    """Loops still aren't supported — only if/elif/else conditionals.
    Bodies must be a flat sequence of self.publish/send_*  + ifs."""
    src = """
from scadable import Controller, on

class LoopyBoot(Controller):
    @on.startup
    def init(self):
        for _ in range(3):
            self.publish("status/boot", {"v": 1})
"""
    result = _compile_esp(tmp_path, src)
    assert result.errors, "expected an error for `for` inside @on.startup body"
    msg = result.errors[0]
    assert "For" in msg or "self.publish" in msg


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


# ---------------- self.state (NW-E) ---------------------------------


def test_state_set_in_on_startup_lowers_to_state_action(tmp_path):
    src = """
from scadable import Controller, on

class CounterBoot(Controller):
    @on.startup
    def init(self):
        self.state.set("count", 0)
"""
    result = _compile_esp(tmp_path, src)
    assert result.errors == [], result.errors
    manifest = json.loads(result.manifest_path.read_text())
    actions = manifest["lifecycle"]["startup"][0]["publishes"]
    assert actions == [{"op": "set", "key": "count", "value": {"kind": "constant", "value": 0}}]


def test_state_increment_default_delta_omits_value(tmp_path):
    src = """
from scadable import Controller, on

class Hits(Controller):
    @on.message(command="hit")
    def on_hit(self):
        self.state.increment("count")
"""
    result = _compile_esp(tmp_path, src)
    assert result.errors == [], result.errors
    manifest = json.loads(result.manifest_path.read_text())
    actions = manifest["mqtt_subscriptions"][0]["publishes"]
    assert actions == [{"op": "increment", "key": "count"}]


def test_state_increment_explicit_delta_lowers_value(tmp_path):
    src = """
from scadable import Controller, on

class Hits(Controller):
    @on.message(command="hit")
    def on_hit(self):
        self.state.increment("count", 5)
"""
    result = _compile_esp(tmp_path, src)
    assert result.errors == [], result.errors
    manifest = json.loads(result.manifest_path.read_text())
    actions = manifest["mqtt_subscriptions"][0]["publishes"]
    assert actions == [
        {"op": "increment", "key": "count", "value": {"kind": "constant", "value": 5}}
    ]


def test_state_delete_lowers(tmp_path):
    src = """
from scadable import Controller, on

class Reset(Controller):
    @on.message(command="reset")
    def clear_one(self):
        self.state.delete("count")
"""
    result = _compile_esp(tmp_path, src)
    assert result.errors == [], result.errors
    manifest = json.loads(result.manifest_path.read_text())
    actions = manifest["mqtt_subscriptions"][0]["publishes"]
    assert actions == [{"op": "delete", "key": "count"}]


def test_state_clear_lowers(tmp_path):
    src = """
from scadable import Controller, on

class WipeAll(Controller):
    @on.message(command="wipe")
    def wipe(self):
        self.state.clear()
"""
    result = _compile_esp(tmp_path, src)
    assert result.errors == [], result.errors
    manifest = json.loads(result.manifest_path.read_text())
    actions = manifest["mqtt_subscriptions"][0]["publishes"]
    assert actions == [{"op": "clear", "key": ""}]


def test_state_attr_read_in_payload_lowers_to_state_descriptor(tmp_path):
    src = """
from scadable import Controller, on

class Echo(Controller):
    @on.message(command="ping")
    def reply(self):
        self.send_event("count", {"n": self.state.count})
"""
    result = _compile_esp(tmp_path, src)
    assert result.errors == [], result.errors
    manifest = json.loads(result.manifest_path.read_text())
    payload = manifest["mqtt_subscriptions"][0]["publishes"][0]["payload"]
    assert payload == {"n": {"kind": "state", "key": "count"}}


def test_state_get_method_form_lowers_to_state_descriptor(tmp_path):
    src = """
from scadable import Controller, on

class Echo(Controller):
    @on.message(command="ping")
    def reply(self):
        self.send_event("count", {"n": self.state.get("count")})
"""
    result = _compile_esp(tmp_path, src)
    assert result.errors == [], result.errors
    manifest = json.loads(result.manifest_path.read_text())
    payload = manifest["mqtt_subscriptions"][0]["publishes"][0]["payload"]
    assert payload == {"n": {"kind": "state", "key": "count"}}


def test_state_set_followed_by_publish_in_lifecycle(tmp_path):
    src = """
from scadable import Controller, on

class Init(Controller):
    @on.startup
    def boot(self):
        self.state.set("boot_count", 0)
        self.state.increment("boot_count")
        self.send_event("ready", {"boots": self.state.boot_count})
"""
    result = _compile_esp(tmp_path, src)
    assert result.errors == [], result.errors
    manifest = json.loads(result.manifest_path.read_text())
    actions = manifest["lifecycle"]["startup"][0]["publishes"]
    assert len(actions) == 3
    assert actions[0]["op"] == "set"
    assert actions[1]["op"] == "increment"
    # Third action is a publish — sanity-check the topic + payload binding.
    assert actions[2]["topic_suffix"] == "event/ready"
    assert actions[2]["payload"] == {"boots": {"kind": "state", "key": "boot_count"}}


def test_state_unknown_op_rejected_with_clear_error(tmp_path):
    src = """
from scadable import Controller, on

class Bad(Controller):
    @on.startup
    def boot(self):
        self.state.frobnicate("count")
"""
    result = _compile_esp(tmp_path, src)
    assert result.errors, "expected an error for unknown self.state op"
    assert "frobnicate" in result.errors[0]


def test_state_set_requires_two_args(tmp_path):
    src = """
from scadable import Controller, on

class Bad(Controller):
    @on.startup
    def boot(self):
        self.state.set("count")
"""
    result = _compile_esp(tmp_path, src)
    assert result.errors, "expected an error for self.state.set with only 1 arg"
    assert "2 arguments" in result.errors[0]


def test_state_clear_takes_no_args(tmp_path):
    src = """
from scadable import Controller, on

class Bad(Controller):
    @on.startup
    def boot(self):
        self.state.clear("count")
"""
    result = _compile_esp(tmp_path, src)
    assert result.errors, "expected an error for self.state.clear with args"
    assert "no arguments" in result.errors[0]
