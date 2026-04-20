"""Emitter — pluggable per-target artifact generation.

Public API matches the v0.1 module-level functions for backward
compatibility (compiler/__init__.py still imports them by name):

    emit_manifest(...)
    emit_driver_configs(...)
    emit_bundle(...)

Internally, dispatch is delegated to a per-target Emitter class:

    LinuxEmitter   — production, ships in v0.2.0
    Esp32Emitter   — preview, raises TargetNotImplementedError
    RtosEmitter    — preview, raises TargetNotImplementedError

Adding ESP/RTOS support later is additive: implement the new
subclass's emit_drivers/emit_bundle methods and register them in
EMITTERS. No other compiler code changes.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from .base import Emitter
from .linux import LinuxEmitter
from .esp32 import Esp32Emitter
from .rtos import RtosEmitter

if TYPE_CHECKING:
    from ..discover import ProjectFiles
    from ..memory import MemoryEstimate


# Registry — one Emitter instance per target. Stateless; sharing is fine.
EMITTERS: dict[str, Emitter] = {
    "linux": LinuxEmitter(),
    "esp32": Esp32Emitter(),
    "rtos":  RtosEmitter(),
}


def _select(target: str) -> Emitter:
    if target not in EMITTERS:
        raise ValueError(
            f"unknown target {target!r}. Known: {', '.join(sorted(EMITTERS))}"
        )
    return EMITTERS[target]


# ── Public API (preserved from v0.1 for compiler/__init__.py) ──────


def emit_manifest(
    project: "ProjectFiles",
    devices: list[dict],
    controllers: list[dict],
    memory: "MemoryEstimate",
    target: str,
    output_dir: Path,
) -> Path:
    """Emit manifest.json — same JSON shape on every target."""
    return _select(target).emit_manifest(
        project, devices, controllers, memory, target, output_dir,
    )


def emit_driver_configs(devices: list[dict], output_dir: Path, target: str = "linux") -> list[Path]:
    """Emit per-device driver configs in the target's native format."""
    return _select(target).emit_driver_configs(devices, output_dir)


def emit_bundle(output_dir: Path, target: str = "linux") -> Path:
    """Emit bundle (per-target archive)."""
    return _select(target).emit_bundle(output_dir)


__all__ = [
    "Emitter",
    "LinuxEmitter", "Esp32Emitter", "RtosEmitter",
    "EMITTERS",
    "emit_manifest", "emit_driver_configs", "emit_bundle",
]
