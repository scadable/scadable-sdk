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
        schedules = _lower_controllers_to_schedules(controllers, project.controller_files)

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


# ---------------- @on.interval lowering -----------------------------


def _lower_controllers_to_schedules(
    controllers: list[dict],
    controller_files: list[Path],
) -> list[dict]:
    """Walk every controller's source file, find each @on.interval method,
    extract the (one) self.publish(...) call inside, lower it to a
    schedule dict matching handlers/schedules.rs::Schedule.

    Raises Esp32UnsupportedError for anything outside the supported
    shape so the user gets a clear refusal at compile time.
    """
    schedules: list[dict] = []
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
                interval_ms = _interval_from_decorators(member, source_path)
                if interval_ms is None:
                    if _has_any_on_decorator(member) and not _is_interval_decorator(
                        member
                    ):
                        raise Esp32UnsupportedError(
                            f"{source_path}:{member.lineno}: "
                            f"@on.{_first_on_decorator_name(member)} not supported on ESP32 "
                            f"— only @on.interval is. (in {ctrl['class_name']}.{member.name})"
                        )
                    continue
                topic_suffix, payload = _extract_publish_call(member, source_path)
                schedule_id = f"{ctrl['class_name']}.{member.name}"
                schedules.append(
                    {
                        "id": schedule_id,
                        "interval_ms": interval_ms,
                        "topic_suffix": topic_suffix,
                        "payload": payload,
                    }
                )
    return schedules


def _has_any_on_decorator(method: ast.FunctionDef) -> bool:
    for dec in method.decorator_list:
        if _decorator_attr(dec) is not None:
            return True
    return False


def _is_interval_decorator(method: ast.FunctionDef) -> bool:
    for dec in method.decorator_list:
        if _decorator_attr(dec) == "interval":
            return True
    return False


def _first_on_decorator_name(method: ast.FunctionDef) -> str:
    for dec in method.decorator_list:
        attr = _decorator_attr(dec)
        if attr is not None:
            return attr
    return "?"


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
