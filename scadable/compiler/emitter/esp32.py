"""ESP32 emitter — declarative-only MVP for v0.3.

Lowers the user's Python controllers into a `schedules[]` array the
firmware's `handlers/release.rs` understands. Only the
`@on.interval(N, UNIT)` + `self.publish(literal_topic, dict_literal)`
shape is supported today; anything else (state machines, drivers,
self.actuate, conditionals beyond `if`) raises Esp32UnsupportedError
with a precise message.

**Bundle format asymmetry.** Linux ships `bundle.tar.gz` (gzipped tar
of manifest + driver binaries + per-driver TOMLs). The cloud's MinIO
object key is hardcoded `projects/{p}/releases/{r}/bundle.tar.gz` and
service-edge proxies whatever bytes live at that path. ESP can't
support a tar+gz reader on Xtensa without dragging in flate2's
miniz_oxide backend + a tar crate, neither of which is vetted on the
xtensa-esp32-espidf target. So for v0.3.0 we cheat: this emitter
writes raw `manifest.json` bytes to a file *named* `bundle.tar.gz` so
the cloud's hardcoded object key still finds it. The chip's
`handlers/release.rs` doesn't try to untar — it just JSON-decodes
the body. Filename is a misleading lie; future v0.4.0 should either
add proper tar+gz support on the chip OR add a per-target object key
on the cloud side.
"""

from __future__ import annotations

import ast
import json
import shutil
from dataclasses import asdict
from pathlib import Path
from typing import TYPE_CHECKING, Any

from .base import Emitter

if TYPE_CHECKING:
    from .._drivers import StagedDriver
    from ..discover import ProjectFiles
    from ..memory import MemoryEstimate


class Esp32UnsupportedError(Exception):
    """Raised when a controller uses a feature ESP32 doesn't support yet.

    Always carries a precise location (file:line) and the offending
    expression so the user can fix it without grep-spelunking. Caller
    should turn this into a CompileResult error string.
    """


# Allowed shapes inside a `self.publish(topic, dict_literal[, quality=...])`
# dict literal value. Each entry maps to a ValueDescriptor variant on
# the chip side (handlers/schedules.rs::ValueDescriptor).
_PAYLOAD_VALUE_KINDS = {"constant", "counter", "timestamp_unix_ms", "random"}


class Esp32Emitter(Emitter):
    """Declarative-only emitter — produces schedules[]-only manifest."""

    def emit_driver_configs(self, devices: list[dict], output_dir: Path) -> list[Path]:
        # ESP doesn't run native driver subprocesses (the protocol path
        # is deferred). The validator gates protocols at compile time
        # against _capabilities.yaml's esp32 entry, so by the time we
        # get here `devices` should already be filtered to "supported".
        # Today: nothing supported, so this is a no-op.
        if devices:
            # Soft signal: if the user declared devices and validation
            # let them through, something's wrong with the capability
            # matrix. Don't fail the compile — the schedules executor
            # ignores devices anyway — but log it. Drop the warning
            # into output_dir as a marker file so the bundle inspector
            # can flag it.
            (output_dir / "esp32_unsupported_devices.txt").write_text(
                "ESP32 emitter received {} device(s) but declarative-only MVP "
                "ignores them. Driver protocols come in v0.4.\n".format(len(devices))
            )
        return []

    def emit_manifest(
        self,
        project: ProjectFiles,
        devices: list[dict],
        controllers: list[dict],
        memory: MemoryEstimate,
        target: str,
        output_dir: Path,
        drivers: list[StagedDriver] | None = None,
    ) -> Path:
        """Emit ESP-specific manifest with `schedules[]` lowered from
        the user's `@on.interval` methods.

        Builds the manifest by hand instead of calling super so the
        target-locked-to-esp32 invariant is explicit and the schedules
        array is folded in at a known position. The base shape (project,
        controllers, memory) is kept so dashboard inspectors that already
        understand the linux manifest don't choke on ESP bundles.
        """
        schedules, lifecycle, mqtt_subscriptions = _lower_controllers(
            controllers, project.controller_files
        )

        manifest: dict[str, Any] = {
            "project": {
                "name": project.name,
                "version": project.version,
            },
            "target": "esp32",
            "devices": [],  # MVP: no driver protocols on ESP
            "controllers": [
                {
                    "id": c["id"],
                    "class_name": c["class_name"],
                    "triggers": c.get("triggers", []),
                }
                for c in controllers
            ],
            "memory": asdict(memory),
            "drivers": [],  # No native binaries on ESP
            "referenced_env_vars": [],  # env_vars not supported on ESP yet
            "schedules": schedules,
            "lifecycle": lifecycle,
            "mqtt_subscriptions": mqtt_subscriptions,
        }
        path = output_dir / "manifest.json"
        path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n")
        return path

    def emit_bundle(self, output_dir: Path) -> Path:
        """Override base.emit_bundle (which produces a real tar.gz).

        Writes `manifest.json`'s raw bytes to a file named
        `bundle.tar.gz` so the cloud's hardcoded MinIO object key path
        still resolves. The chip's release.rs JSON-decodes the body
        directly — no untar happens. See module docstring for the
        rationale + cleanup path.
        """
        manifest = output_dir / "manifest.json"
        if not manifest.exists():
            raise RuntimeError(
                "esp32 emit_bundle: manifest.json missing — emit_manifest "
                "must run before emit_bundle"
            )
        bundle = output_dir / "bundle.tar.gz"
        # Direct copy of the manifest bytes. Filename is the lie; the
        # cloud serves whatever's at this path verbatim.
        shutil.copyfile(manifest, bundle)
        return bundle


# ---------------- trigger lowering ----------------------------------

# Triggers we currently lower into the manifest. Anything else with an
# @on.<name> decorator gets refused with a clear message naming the
# unsupported trigger so the user sees the real reason at compile time
# (vs. a downstream firmware-side surprise).
_SUPPORTED_TRIGGERS = {"interval", "startup", "shutdown", "message"}


def _lower_controllers(
    controllers: list[dict],
    controller_files: list[Path],
) -> tuple[list[dict], dict[str, list[dict]], list[dict]]:
    """Walk every controller's source file and lower its triggers.

    Returns `(schedules, lifecycle, mqtt_subscriptions)`:

    - `schedules[]` — `@on.interval` methods (existing behaviour).
    - `lifecycle = {"startup": [...], "shutdown": [...]}` — `@on.startup`
      / `@on.shutdown` methods. Each entry shape:
      `{controller, method, publishes: [{topic_suffix, payload}, ...]}`.
    - `mqtt_subscriptions[]` — `@on.message(topic="...")` methods, same
      `publishes[]` shape plus the `topic_suffix` the firmware should
      subscribe to.

    Raises Esp32UnsupportedError for anything outside the supported
    shape so the user gets a clear refusal at compile time.
    """
    schedules: list[dict] = []
    lifecycle: dict[str, list[dict]] = {"startup": [], "shutdown": []}
    mqtt_subscriptions: list[dict] = []

    # Re-parse the controller files so we can walk method bodies. The
    # parser already gave us `controllers` (with id, class_name, triggers)
    # but not the method-body AST nodes. Cheap — controller files are
    # typically a handful of small files.
    by_file: dict[Path, ast.Module] = {}
    for path in controller_files:
        src = path.read_text()
        by_file[path] = ast.parse(src, filename=str(path))

    for ctrl in controllers:
        source_path = Path(ctrl.get("source_file") or "")
        if source_path not in by_file:
            continue
        tree = by_file[source_path]
        for cls in ast.walk(tree):
            if not (isinstance(cls, ast.ClassDef) and cls.name == ctrl["class_name"]):
                continue
            for member in cls.body:
                if not isinstance(member, ast.FunctionDef):
                    continue
                trigger = _on_decorator_for(member)
                if trigger is None:
                    continue
                if trigger not in _SUPPORTED_TRIGGERS:
                    raise Esp32UnsupportedError(
                        f"{source_path}:{member.lineno}: "
                        f"@on.{trigger} not supported on ESP32 yet. "
                        f"(in {ctrl['class_name']}.{member.name})"
                    )

                if trigger == "interval":
                    interval_ms = _interval_from_decorators(member, source_path)
                    # _interval_from_decorators raises rather than
                    # returning None when @on.interval is malformed, so
                    # `interval_ms is None` here only happens if the
                    # detector logic ever drifts. Defensive: skip.
                    if interval_ms is None:
                        continue
                    topic_suffix, payload = _extract_publish_call(member, source_path)
                    schedules.append(
                        {
                            "id": f"{ctrl['class_name']}.{member.name}",
                            "interval_ms": interval_ms,
                            "topic_suffix": topic_suffix,
                            "payload": payload,
                        }
                    )
                    continue

                # startup / shutdown / message all share the same body
                # contract: a sequence of self.publish(literal, dict)
                # calls. The decorator metadata differs per kind.
                publishes = _extract_publish_calls(member, source_path)

                if trigger in ("startup", "shutdown"):
                    lifecycle[trigger].append(
                        {
                            "controller": ctrl["class_name"],
                            "method": member.name,
                            "publishes": publishes,
                        }
                    )
                    continue

                # @on.message(topic="cmd/restart")
                topic_suffix = _message_topic_from_decorator(member, source_path)
                mqtt_subscriptions.append(
                    {
                        "topic_suffix": topic_suffix,
                        "controller": ctrl["class_name"],
                        "method": member.name,
                        "publishes": publishes,
                    }
                )

    return schedules, lifecycle, mqtt_subscriptions


def _on_decorator_for(method: ast.FunctionDef) -> str | None:
    """Return the @on.<name> tag for this method, or None if none.

    A method decorated with @on.startup AND @on.interval would be a
    user error — but the parser already rejects that combo upstream, so
    here we just take the first @on decorator we see (matches the v0.3
    semantics of `_first_on_decorator_name`).
    """
    for dec in method.decorator_list:
        attr = _decorator_attr(dec)
        if attr is not None:
            return attr
    return None


def _message_topic_from_decorator(
    method: ast.FunctionDef, source_path: Path
) -> str:
    """Pull the topic= kwarg out of @on.message(topic="...").

    The DSL allows positional or kwarg form (see triggers.py: the
    decorator signature is `message(topic: str)`), but for ESP we
    require the explicit `topic=` kwarg so the lowering stays
    obviously-correct + matches the example in the user docs. A bare
    @on.message decorator (no args) is also rejected here.
    """
    for dec in method.decorator_list:
        if not isinstance(dec, ast.Call):
            continue
        if _decorator_attr(dec) != "message":
            continue
        for kw in dec.keywords:
            if kw.arg == "topic":
                return _string_literal(kw.value, source_path, "topic")
        # Tolerate a single positional topic literal so the SDK example
        # `@on.message("emergency_stop")` keeps working — but be loud
        # if neither form is present.
        if len(dec.args) == 1:
            return _string_literal(dec.args[0], source_path, "topic")
        raise Esp32UnsupportedError(
            f"{source_path}:{dec.lineno}: @on.message requires a topic= "
            f"keyword argument (got {len(dec.args)} positional args, "
            f"{len(dec.keywords)} kwargs)"
        )
    raise Esp32UnsupportedError(
        f"{source_path}:{method.lineno}: @on.message decorator missing on "
        f"{method.name} (internal error: lowering reached message branch)"
    )


def _decorator_attr(dec: ast.expr) -> str | None:
    """If `dec` is `@on.<name>` or `@on.<name>(...)`, return <name>."""
    if isinstance(dec, ast.Call):
        dec = dec.func
    if (
        isinstance(dec, ast.Attribute)
        and isinstance(dec.value, ast.Name)
        and dec.value.id == "on"
    ):
        return dec.attr
    return None


_TIME_UNIT_MS = {
    "SECONDS": 1_000,
    "MINUTES": 60_000,
    "HOURS": 3_600_000,
    "MILLISECONDS": 1,
    "s": 1_000,
    "min": 60_000,
    "h": 3_600_000,
    "ms": 1,
}


def _interval_from_decorators(
    method: ast.FunctionDef, source_path: Path
) -> int | None:
    """Return interval_ms if this method has @on.interval(value, UNIT)."""
    for dec in method.decorator_list:
        if not isinstance(dec, ast.Call):
            continue
        if _decorator_attr(dec) != "interval":
            continue
        if len(dec.args) < 1:
            raise Esp32UnsupportedError(
                f"{source_path}:{dec.lineno}: @on.interval requires (value, UNIT) args"
            )
        value = _const_strict(dec.args[0], source_path)
        unit = "SECONDS"
        if len(dec.args) >= 2:
            unit = _const_strict(dec.args[1], source_path)
            if not isinstance(unit, str):
                if isinstance(dec.args[1], ast.Name):
                    unit = dec.args[1].id
                else:
                    raise Esp32UnsupportedError(
                        f"{source_path}:{dec.args[1].lineno}: "
                        f"@on.interval unit must be a SECONDS/MINUTES/MS literal"
                    )
        if unit not in _TIME_UNIT_MS:
            raise Esp32UnsupportedError(
                f"{source_path}:{dec.lineno}: unknown interval unit {unit!r}"
            )
        if not isinstance(value, (int, float)):
            raise Esp32UnsupportedError(
                f"{source_path}:{dec.lineno}: @on.interval value must be a number literal"
            )
        return int(value * _TIME_UNIT_MS[unit])
    return None


def _const_strict(node: ast.expr, source_path: Path) -> Any:
    """Like _const but bare names are returned as their id (e.g. SECONDS)."""
    if isinstance(node, ast.Constant):
        return node.value
    if isinstance(node, ast.Name):
        return node.id
    raise Esp32UnsupportedError(
        f"{source_path}:{node.lineno}: expected literal value, got {type(node).__name__}"
    )


def _extract_publish_call(
    method: ast.FunctionDef, source_path: Path
) -> tuple[str, dict]:
    """The method body must be exactly one
    `self.publish(topic_literal, payload_dict[, quality=...])`.

    Anything else (multiple statements, conditionals, .actuate, etc.)
    is refused. Return (topic_suffix, payload_descriptor_dict).
    """
    body = list(method.body)
    # Permit a leading docstring then exactly one Expr(Call) statement.
    if (
        body
        and isinstance(body[0], ast.Expr)
        and isinstance(body[0].value, ast.Constant)
        and isinstance(body[0].value.value, str)
    ):
        body = body[1:]
    if len(body) != 1:
        raise Esp32UnsupportedError(
            f"{source_path}:{method.lineno}: ESP32 controller methods must contain "
            f"exactly one self.publish(...) call (got {len(body)} statements)"
        )
    stmt = body[0]
    if not (isinstance(stmt, ast.Expr) and isinstance(stmt.value, ast.Call)):
        raise Esp32UnsupportedError(
            f"{source_path}:{method.lineno}: only a self.publish(...) expression is supported"
        )
    call = stmt.value
    if not (
        isinstance(call.func, ast.Attribute)
        and isinstance(call.func.value, ast.Name)
        and call.func.value.id == "self"
    ):
        raise Esp32UnsupportedError(
            f"{source_path}:{call.lineno}: only `self.<method>(...)` calls are supported"
        )
    method_name = call.func.attr
    if method_name != "publish":
        raise Esp32UnsupportedError(
            f"{source_path}:{call.lineno}: self.{method_name}(...) not supported on ESP32 — "
            f"only self.publish() is. (allowlist may grow in v0.4)"
        )
    if len(call.args) < 2:
        raise Esp32UnsupportedError(
            f"{source_path}:{call.lineno}: self.publish requires (topic, payload_dict)"
        )
    topic_node, payload_node = call.args[0], call.args[1]
    topic_suffix = _string_literal(topic_node, source_path, "topic")
    if topic_suffix.startswith("/"):
        raise Esp32UnsupportedError(
            f"{source_path}:{topic_node.lineno}: publish topic must not start with '/' "
            f"— it gets prepended with `{{project}}/{{gateway}}/`"
        )
    payload = _payload_dict(payload_node, source_path)
    return topic_suffix, payload


def _extract_publish_calls(
    method: ast.FunctionDef, source_path: Path
) -> list[dict]:
    """Lower a method body that's allowed to contain N self.publish() calls
    in sequence (used by lifecycle + mqtt_subscriptions handlers).

    Same restrictions as `_extract_publish_call` apply per-statement —
    every body statement must be a `self.publish(literal_topic,
    dict_literal[, quality=...])` Expr — but we accept >1 of them so a
    boot/shutdown handler can publish several status updates in order.

    A leading docstring is tolerated. Anything else (assignments,
    conditionals, loops, self.actuate, self.upload, function calls
    other than self.publish) raises Esp32UnsupportedError naming the
    offending construct so the user can fix it without grep-spelunking.

    Returns a list of `{topic_suffix, payload}` dicts in source order.
    """
    body = list(method.body)
    if (
        body
        and isinstance(body[0], ast.Expr)
        and isinstance(body[0].value, ast.Constant)
        and isinstance(body[0].value.value, str)
    ):
        body = body[1:]

    if not body:
        # An empty body (just a docstring or pass) is fine — emits no
        # publishes. Useful for users who want a side-effect-free
        # placeholder while wiring the trigger up.
        return []

    publishes: list[dict] = []
    for stmt in body:
        if not isinstance(stmt, ast.Expr):
            raise Esp32UnsupportedError(
                f"{source_path}:{stmt.lineno}: only self.publish(...) "
                f"statements are allowed here (got {type(stmt).__name__})"
            )
        if not isinstance(stmt.value, ast.Call):
            raise Esp32UnsupportedError(
                f"{source_path}:{stmt.lineno}: only self.publish(...) "
                f"calls are allowed here"
            )
        call = stmt.value
        if not (
            isinstance(call.func, ast.Attribute)
            and isinstance(call.func.value, ast.Name)
            and call.func.value.id == "self"
        ):
            raise Esp32UnsupportedError(
                f"{source_path}:{call.lineno}: only `self.<method>(...)` "
                f"calls are supported"
            )
        method_name = call.func.attr
        if method_name != "publish":
            raise Esp32UnsupportedError(
                f"{source_path}:{call.lineno}: self.{method_name}(...) "
                f"not supported on ESP32 — only self.publish() is."
            )
        if len(call.args) < 2:
            raise Esp32UnsupportedError(
                f"{source_path}:{call.lineno}: self.publish requires "
                f"(topic, payload_dict)"
            )
        topic_node, payload_node = call.args[0], call.args[1]
        topic_suffix = _string_literal(topic_node, source_path, "topic")
        if topic_suffix.startswith("/"):
            raise Esp32UnsupportedError(
                f"{source_path}:{topic_node.lineno}: publish topic must "
                f"not start with '/' — it gets prepended with "
                f"`{{project}}/{{gateway}}/`"
            )
        payload = _payload_dict(payload_node, source_path)
        publishes.append({"topic_suffix": topic_suffix, "payload": payload})

    return publishes


def _string_literal(node: ast.expr, source_path: Path, what: str) -> str:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    raise Esp32UnsupportedError(
        f"{source_path}:{node.lineno}: {what} must be a string literal"
    )


def _payload_dict(node: ast.expr, source_path: Path) -> dict:
    """The payload dict literal: `{"name": <expr>, ...}` where each
    value is one of the supported descriptor shapes.
    """
    if not isinstance(node, ast.Dict):
        raise Esp32UnsupportedError(
            f"{source_path}:{node.lineno}: publish payload must be a {{}}-literal dict"
        )
    out: dict = {}
    for k_node, v_node in zip(node.keys, node.values, strict=True):
        if k_node is None:
            raise Esp32UnsupportedError(
                f"{source_path}:{node.lineno}: dict-spread `**...` not supported in payload"
            )
        key = _string_literal(k_node, source_path, "payload key")
        out[key] = _value_descriptor(v_node, source_path)
    return out


def _value_descriptor(node: ast.expr, source_path: Path) -> dict:
    """Lower a payload-value AST expression to a ValueDescriptor dict.

    Recognised shapes:
      - bare literal (str/int/float/bool/None) → {"kind": "constant", "value": <lit>}
      - `random(min, max)` (special name) → {"kind": "random", "min": ..., "max": ...}
      - `counter()` → {"kind": "counter"}
      - `timestamp_unix_ms()` → {"kind": "timestamp_unix_ms"}
      - explicit dict `{"kind": "...", ...}` → passed through after validation

    Anything else (variables, complex expressions, function calls with
    state) raises Esp32UnsupportedError.
    """
    if isinstance(node, ast.Constant):
        return {"kind": "constant", "value": node.value}

    if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
        fn = node.func.id
        if fn == "counter" and not node.args and not node.keywords:
            return {"kind": "counter"}
        if fn == "timestamp_unix_ms" and not node.args and not node.keywords:
            return {"kind": "timestamp_unix_ms"}
        if fn == "random" and len(node.args) == 2 and not node.keywords:
            mn = _const_strict(node.args[0], source_path)
            mx = _const_strict(node.args[1], source_path)
            if not isinstance(mn, (int, float)) or not isinstance(mx, (int, float)):
                raise Esp32UnsupportedError(
                    f"{source_path}:{node.lineno}: random(min, max) requires numeric literals"
                )
            return {"kind": "random", "min": float(mn), "max": float(mx)}

    if isinstance(node, ast.Dict):
        d: dict = {}
        for k_node, v_node in zip(node.keys, node.values, strict=True):
            if not isinstance(k_node, ast.Constant) or not isinstance(k_node.value, str):
                raise Esp32UnsupportedError(
                    f"{source_path}:{node.lineno}: descriptor dict keys must be string literals"
                )
            v = _const_strict(v_node, source_path)
            d[k_node.value] = v
        kind = d.get("kind")
        if kind not in _PAYLOAD_VALUE_KINDS:
            raise Esp32UnsupportedError(
                f"{source_path}:{node.lineno}: unknown payload value kind {kind!r}"
            )
        return d

    raise Esp32UnsupportedError(
        f"{source_path}:{node.lineno}: payload value must be a literal, "
        f"random/counter/timestamp_unix_ms() call, or {{kind:..., ...}} descriptor"
    )
