"""Project discovery — find scadable.toml, device files, controller files."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class ProjectFiles:
    """Paths discovered within a Scadable project."""

    root: Path
    manifest: Path | None = None
    device_files: list[Path] = field(default_factory=list)
    controller_files: list[Path] = field(default_factory=list)
    model_files: list[Path] = field(default_factory=list)
    name: str = ""
    version: str = "0.1.0"


def discover_project(root: Path) -> ProjectFiles:
    """Scan *root* for project files and return a ProjectFiles dataclass."""
    root = root.resolve()
    pf = ProjectFiles(root=root)

    # scadable.toml (optional)
    manifest = root / "scadable.toml"
    if manifest.exists():
        pf.manifest = manifest
        _parse_manifest(pf, manifest)

    # devices/*.py
    devices_dir = root / "devices"
    if devices_dir.is_dir():
        pf.device_files = sorted(f for f in devices_dir.glob("*.py") if not f.name.startswith("_"))

    # controllers/*.py
    controllers_dir = root / "controllers"
    if controllers_dir.is_dir():
        pf.controller_files = sorted(
            f for f in controllers_dir.glob("*.py") if not f.name.startswith("_")
        )

    # models/*.py (optional)
    models_dir = root / "models"
    if models_dir.is_dir():
        pf.model_files = sorted(f for f in models_dir.glob("*.py") if not f.name.startswith("_"))

    # Derive project name from directory if not set via manifest
    if not pf.name:
        pf.name = root.name

    return pf


def _parse_manifest(pf: ProjectFiles, path: Path) -> None:
    """Read project name/version from scadable.toml (minimal TOML parser)."""
    try:
        text = path.read_text()
    except OSError:
        return

    for line in text.splitlines():
        line = line.strip()
        if line.startswith("name"):
            pf.name = _toml_value(line)
        elif line.startswith("version"):
            pf.version = _toml_value(line)


def _toml_value(line: str) -> str:
    """Extract the string value from a 'key = "value"' TOML line."""
    _, _, raw = line.partition("=")
    raw = raw.strip().strip('"').strip("'")
    return raw
