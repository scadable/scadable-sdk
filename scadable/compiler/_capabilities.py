"""Capability lookup — protocols/storage/controllers status from
``scadable/_capabilities.yaml``.

This is the single source of truth for which features are
``production`` vs ``preview`` vs ``unsupported`` on the gateway side.
The SDK reads the vendored copy at compile time and gates the user's
project against it:

  - ``unsupported`` → :class:`CapabilityError`, compile fails. The
    user's code uses a feature the gateway will never run.
  - ``preview``     → :class:`PreviewWarning` is appended to the
    compile result's warnings; compile still succeeds. The DSL is
    accepted but the runtime hasn't shipped yet.
  - ``production``  → silent. Customer can rely on it.

The YAML is bundled with the wheel as package data; we never reach
outside the install root at runtime. ``platform/capabilities.yaml``
is the upstream source of truth — keep the two byte-identical (a
test in ``tests/compiler/test_capabilities.py`` enforces this).
"""

from __future__ import annotations

import ast
from dataclasses import dataclass
from importlib import resources
from pathlib import Path
from typing import Literal

import yaml

Status = Literal["production", "preview", "unsupported"]


# ── Errors / warnings ────────────────────────────────────────────


class CapabilityError(RuntimeError):
    """Raised when a project uses a feature marked ``unsupported``.

    Carries the feature kind (protocol/storage/controller), the
    feature name, and the source file that referenced it (when known)
    so the user can jump straight to the line.
    """


@dataclass(frozen=True)
class PreviewWarning:
    """Compile-time warning that a feature is preview (DSL accepted,
    runtime not shipped). Emitted as a string into
    :class:`CompileResult.warnings` so the existing CLI formatter
    surfaces it the same way as every other warning.
    """

    kind: str          # "protocol" | "storage" | "controller"
    name: str          # e.g. "ble"
    source: str        # path/where it appeared, "" if unknown
    tracking: str      # e.g. "gateway-linux#1" or "not yet tracked"

    def format(self) -> str:
        loc = f" ({self.source})" if self.source else ""
        return (
            f"{self.kind} {self.name!r} is PREVIEW — the gateway runtime does not "
            f"ship a working implementation yet. Tracking: {self.tracking}.{loc} "
            f"Compile succeeded; deploys against this gateway will not run "
            f"this driver until preview status is lifted."
        )


# ── Loader ───────────────────────────────────────────────────────


@dataclass(frozen=True)
class Capabilities:
    """Parsed view of ``_capabilities.yaml``.

    All three maps are name → status. Read once at compile entry,
    passed by reference to the check functions below.
    """

    version: int
    protocols: dict[str, Status]
    storage: dict[str, Status]
    controllers: dict[str, Status]

    @classmethod
    def load(cls) -> Capabilities:
        # importlib.resources avoids __file__ shenanigans inside zip
        # installs; ``files()`` is the post-3.9 stable API.
        pkg = resources.files("scadable")
        with resources.as_file(pkg / "_capabilities.yaml") as path:
            return cls.load_from(path)

    @classmethod
    def load_from(cls, path: Path) -> Capabilities:
        body = yaml.safe_load(Path(path).read_text()) or {}
        return cls(
            version=int(body.get("version", 1)),
            protocols={k: _validate_status(v) for k, v in (body.get("protocols") or {}).items()},
            storage={k: _validate_status(v) for k, v in (body.get("storage") or {}).items()},
            controllers={k: _validate_status(v) for k, v in (body.get("controllers") or {}).items()},
        )


def _validate_status(value: object) -> Status:
    if value not in ("production", "preview", "unsupported"):
        raise CapabilityError(
            f"capabilities.yaml: invalid status {value!r} "
            f"(allowed: production, preview, unsupported)"
        )
    return value  # type: ignore[return-value]


# ── Tracking-issue map (preview only) ────────────────────────────
#
# When a protocol or storage backend is preview, the warning points
# at the gateway-linux issue tracking the work. Storage issues exist
# already (per scadable/storage.py); protocols don't have individual
# issues yet, so the warning says "not yet tracked".

_STORAGE_TRACKING: dict[str, str] = {
    "data": "gateway-linux#1",
    "state": "gateway-linux#2",
    "files": "gateway-linux#3",
}


def _tracking_for(kind: str, name: str) -> str:
    if kind == "storage":
        return _STORAGE_TRACKING.get(name, "not yet tracked")
    return "not yet tracked"


# ── Public check API used by compile_project ─────────────────────


def check_protocols(
    capabilities: Capabilities,
    devices: list[dict],
) -> list[PreviewWarning]:
    """Inspect each device's connection.protocol against capabilities.

    Returns the preview warnings (empty list = nothing to warn about);
    raises :class:`CapabilityError` on the first ``unsupported`` hit
    so the compile fails fast and the user fixes one issue at a time.
    """
    warnings: list[PreviewWarning] = []
    for dev in devices:
        proto = (dev.get("connection") or {}).get("protocol")
        if not proto:
            continue
        # SDK uses both ``modbus_tcp`` (snake) and ``modbus-tcp`` (kebab)
        # in different code paths; capabilities.yaml is the snake-case
        # canonical form.
        canonical = proto.replace("-", "_")
        status = capabilities.protocols.get(canonical)
        if status is None:
            # Protocol the SDK exposes but capabilities.yaml doesn't
            # know about. Treat as preview so we don't silently let
            # a typo or unmapped protocol through; the drift-guard
            # test catches this in CI before it ships.
            warnings.append(
                PreviewWarning(
                    kind="protocol",
                    name=canonical,
                    source=dev.get("source_file", "") or "",
                    tracking="not yet tracked",
                )
            )
            continue
        if status == "unsupported":
            raise CapabilityError(
                f"protocol {canonical!r} is UNSUPPORTED — there is no driver "
                f"and no current plan to ship one. "
                f"Device {dev.get('id', '?')!r} declares this protocol in "
                f"{dev.get('source_file', '?')!r}. "
                f"Use modbus_tcp/modbus_rtu, or open an issue at "
                f"https://github.com/scadable/gateway-linux to request it."
            )
        if status == "preview":
            warnings.append(
                PreviewWarning(
                    kind="protocol",
                    name=canonical,
                    source=dev.get("source_file", "") or "",
                    tracking=_tracking_for("protocol", canonical),
                )
            )
    return warnings


def check_storage_imports(
    capabilities: Capabilities,
    project_root: Path,
) -> list[PreviewWarning]:
    """Static-scan project Python files for ``scadable.data/files/state``
    factory calls and warn (or fail) according to capabilities.

    This is intentionally a textual / AST scan — we never import the
    user's modules. Importing would either run their startup code
    or trip the runtime ``PreviewError`` raise inside
    ``scadable.storage`` and we'd never get a clean compile result.
    """
    import ast

    warnings: list[PreviewWarning] = []
    seen: set[tuple[str, str]] = set()  # (kind, source_path) dedup

    for py_file in _walk_user_python(project_root):
        try:
            tree = ast.parse(py_file.read_text(), filename=str(py_file))
        except (SyntaxError, OSError):
            # The discover/parse pass already records SyntaxError as
            # warnings; don't double-report.
            continue

        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            fname = _call_func_simple_name(node)
            if fname not in capabilities.storage:
                continue
            status = capabilities.storage[fname]
            key = (fname, str(py_file))
            if key in seen:
                continue
            seen.add(key)
            if status == "unsupported":
                raise CapabilityError(
                    f"storage {fname!r} is UNSUPPORTED — the gateway runtime "
                    f"does not ship a backend and there is no current plan to. "
                    f"Used in {py_file} (line {node.lineno})."
                )
            if status == "preview":
                warnings.append(
                    PreviewWarning(
                        kind="storage",
                        name=fname,
                        source=f"{py_file}:{node.lineno}",
                        tracking=_tracking_for("storage", fname),
                    )
                )
    return warnings


def check_controllers(
    capabilities: Capabilities,
    controllers: list[dict],
) -> list[PreviewWarning]:
    """Map a parsed controller's class to a controller-type key in
    capabilities.yaml. Today only ``pid`` and ``state_machine`` are
    declared (both production); this hook exists so adding a preview
    controller type later is a one-line capabilities.yaml change with
    no compiler edits.

    The match is loose by design: a class named ``MyPID`` or
    ``PidLoop`` matches ``pid``; ``MyStateMachine`` or ``Pump_SM``
    matches ``state_machine``. Anything that doesn't match a known
    type is left alone (assumed to be a generic Controller subclass).
    """
    warnings: list[PreviewWarning] = []
    for ctrl in controllers:
        cls = ctrl.get("class_name", "").lower()
        if not cls:
            continue
        # Heuristic match against capabilities.yaml keys.
        for key, status in capabilities.controllers.items():
            normalized = key.replace("_", "")
            if normalized not in cls.replace("_", ""):
                continue
            if status == "unsupported":
                raise CapabilityError(
                    f"controller type {key!r} is UNSUPPORTED. "
                    f"Class {ctrl.get('class_name', '?')!r} uses it in "
                    f"{ctrl.get('source_file', '?')!r}."
                )
            if status == "preview":
                warnings.append(
                    PreviewWarning(
                        kind="controller",
                        name=key,
                        source=str(ctrl.get("source_file", "")),
                        tracking=_tracking_for("controller", key),
                    )
                )
    return warnings


# ── Internals ────────────────────────────────────────────────────


def _call_func_simple_name(node: ast.Call) -> str:
    """For a Call node, return the simple function name regardless of
    how it was referenced: ``data(...)``, ``scadable.data(...)``,
    ``storage.data(...)`` all return ``"data"``.
    """
    func = node.func
    if isinstance(func, ast.Name):
        return func.id
    if isinstance(func, ast.Attribute):
        return func.attr
    return ""


def _walk_user_python(root: Path) -> list[Path]:
    """Project python files we should scan for storage usage. Skip
    common noise dirs so a vendored .venv or __pycache__ doesn't
    blow up the scan time on large projects.
    """
    out: list[Path] = []
    for p in root.rglob("*.py"):
        parts = set(p.parts)
        if "__pycache__" in parts or ".venv" in parts or "venv" in parts:
            continue
        if "site-packages" in parts:
            continue
        out.append(p)
    return out
