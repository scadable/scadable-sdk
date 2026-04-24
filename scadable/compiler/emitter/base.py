"""Emitter base class — the contract every per-target emitter must satisfy."""

from __future__ import annotations

import json
import re
import tarfile
from abc import ABC, abstractmethod
from collections.abc import Iterable
from dataclasses import asdict
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .._drivers import StagedDriver
    from ..discover import ProjectFiles
    from ..memory import MemoryEstimate

# Recognised env-var placeholder syntax. Matches GitHub Actions /
# shell `${VAR_NAME}` (uppercase + digits + underscore, must start
# with a letter). Anything that doesn't match this pattern is left
# alone as a literal string by the gateway's expander too — the two
# scanners must agree on the regex or the dashboard will surface
# vars that never get expanded (or vice versa).
_ENV_VAR_PATTERN = re.compile(r"\$\{([A-Z][A-Z0-9_]*)\}")


class Emitter(ABC):
    """Abstract base. Subclasses implement target-specific output.

    `emit_manifest` is concrete here because the manifest schema is
    target-agnostic (same JSON shape on every target). Subclasses
    only need to implement `emit_driver_configs` and `emit_bundle`,
    which are the parts that differ per target.
    """

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
        """Write manifest.json — identical schema across all targets.

        `drivers` is the list of driver binaries the compiler fetched
        from the CDN and staged into the bundle. Empty list (or None)
        means no drivers were bundled, which is also the pre-W3
        behavior — existing projects compile unchanged.

        `referenced_env_vars` is the unique set of `${VAR}` placeholder
        names appearing in any device dict's string values. The cloud
        release pipeline reads this and auto-creates "unset" rows on
        every gateway subscribed to this project (GitHub Actions style)
        so the dashboard surfaces the slot before the gateway boots.
        """
        manifest = {
            "project": {
                "name": project.name,
                "version": project.version,
            },
            "target": target,
            "devices": [_clean_device(d) for d in devices],
            "controllers": [_clean_controller(c) for c in controllers],
            "memory": asdict(memory),
            "drivers": [
                {
                    "name": d.name,
                    "version": d.version,
                    "arch": d.arch,
                    "sha256": d.sha256,
                    "path": d.relative_path,
                }
                for d in (drivers or [])
            ],
            "referenced_env_vars": find_env_var_refs(devices),
        }
        path = output_dir / "manifest.json"
        path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n")
        return path

    def emit_bundle(self, output_dir: Path) -> Path:
        """Default bundle = tar.gz of everything in output_dir.

        Linux uses this directly. Smaller targets (ESP, RTOS) may
        want a flat binary blob — they override.
        """
        bundle_path = output_dir / "bundle.tar.gz"
        with tarfile.open(bundle_path, "w:gz") as tar:
            for child in sorted(output_dir.iterdir()):
                if child.name == "bundle.tar.gz":
                    continue
                tar.add(child, arcname=child.name)
        return bundle_path

    @abstractmethod
    def emit_driver_configs(self, devices: list[dict], output_dir: Path) -> list[Path]:
        """Write per-device driver configs in the target's native format."""
        ...


def find_env_var_refs(devices: list[dict]) -> list[str]:
    """Walk every string value in every device dict and return the
    sorted-unique set of `${VAR}` placeholder names found inside.

    The gateway's expander uses an identical regex (see
    `gateway-linux/src/handlers/env_vars.rs`); both must agree or
    the dashboard surfaces vars that never get expanded.
    """
    seen: set[str] = set()
    for dev in devices:
        _collect_refs(dev, seen)
    return sorted(seen)


def _collect_refs(value: object, seen: set[str]) -> None:
    if isinstance(value, str):
        for match in _ENV_VAR_PATTERN.finditer(value):
            seen.add(match.group(1))
    elif isinstance(value, dict):
        for v in value.values():
            _collect_refs(v, seen)
    elif isinstance(value, (list, tuple)) or (
        isinstance(value, Iterable) and not isinstance(value, (bytes, bytearray))
    ):
        for v in value:
            _collect_refs(v, seen)


def _clean_device(dev: dict) -> dict:
    """Strip internal-only keys from a device dict before serialization."""
    out = {k: v for k, v in dev.items() if k not in ("class_name", "source_file")}
    return {k: v for k, v in out.items() if v is not None}


def _clean_controller(ctrl: dict) -> dict:
    """Project a controller dict down to the manifest-visible fields."""
    return {
        "id": ctrl["id"],
        "class_name": ctrl["class_name"],
        "triggers": ctrl.get("triggers", []),
    }
