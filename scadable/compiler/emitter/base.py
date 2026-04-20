"""Emitter base class — the contract every per-target emitter must satisfy."""

from __future__ import annotations

import json
import tarfile
from abc import ABC, abstractmethod
from dataclasses import asdict
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..discover import ProjectFiles
    from ..memory import MemoryEstimate


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
    ) -> Path:
        """Write manifest.json — identical schema across all targets."""
        manifest = {
            "project": {
                "name": project.name,
                "version": project.version,
            },
            "target": target,
            "devices": [_clean_device(d) for d in devices],
            "controllers": [_clean_controller(c) for c in controllers],
            "memory": asdict(memory),
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
