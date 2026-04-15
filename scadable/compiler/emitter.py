"""Output generation — manifest.json, driver TOMLs, bundle.tar.gz."""

from __future__ import annotations

import json
import tarfile
from dataclasses import asdict
from pathlib import Path

from .discover import ProjectFiles
from .memory import MemoryEstimate


def emit_manifest(
    project: ProjectFiles,
    devices: list[dict],
    controllers: list[dict],
    memory: MemoryEstimate,
    target: str,
    output_dir: Path,
) -> Path:
    """Write manifest.json to output_dir and return its path."""
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


def _clean_device(dev: dict) -> dict:
    """Prepare a device dict for JSON serialisation (remove internal keys)."""
    out = {k: v for k, v in dev.items() if k != "class_name" and k != "source_file"}
    # Remove None values
    return {k: v for k, v in out.items() if v is not None}


def _clean_controller(ctrl: dict) -> dict:
    """Prepare a controller dict for JSON serialisation."""
    return {
        "id": ctrl["id"],
        "class_name": ctrl["class_name"],
        "triggers": ctrl.get("triggers", []),
    }


def emit_driver_configs(devices: list[dict], output_dir: Path) -> list[Path]:
    """Write a TOML driver config for each device and return the paths."""
    drivers_dir = output_dir / "drivers"
    drivers_dir.mkdir(parents=True, exist_ok=True)

    paths: list[Path] = []
    for dev in devices:
        path = drivers_dir / f"{dev['id']}.toml"
        path.write_text(_device_to_toml(dev))
        paths.append(path)
    return paths


def _device_to_toml(dev: dict) -> str:
    """Convert a parsed device dict to TOML text."""
    lines: list[str] = []

    # [device] section
    lines.append("[device]")
    lines.append(f'id = "{dev["id"]}"')
    if dev.get("name"):
        lines.append(f'name = "{dev["name"]}"')
    conn = dev.get("connection") or {}
    lines.append(f'protocol = "{conn.get("protocol", "")}"')
    if dev.get("poll_ms") is not None:
        lines.append(f'poll_ms = {dev["poll_ms"]}')
    if dev.get("heartbeat_ms") is not None:
        lines.append(f'heartbeat_ms = {dev["heartbeat_ms"]}')
    if dev.get("health_timeout") is not None:
        lines.append(f'health_timeout = {dev["health_timeout"]}')
    if dev.get("historian_ms") is not None:
        lines.append(f'historian_ms = {dev["historian_ms"]}')

    # [connection] section
    lines.append("")
    lines.append("[connection]")
    for k, v in conn.items():
        if k == "protocol":
            continue
        lines.append(f"{k} = {_toml_value(v)}")

    # [[registers]] sections
    for reg in dev.get("registers", []):
        lines.append("")
        lines.append("[[registers]]")
        if reg.get("name"):
            lines.append(f'name = "{reg["name"]}"')
        if "address" in reg:
            lines.append(f'address = {reg["address"]}')
        if "uuid" in reg:
            lines.append(f'uuid = "{reg["uuid"]}"')
        if "pin" in reg:
            lines.append(f'pin = {reg["pin"]}')
        if "offset" in reg:
            lines.append(f'offset = {reg["offset"]}')
        if "length" in reg:
            lines.append(f'length = {reg["length"]}')
        if reg.get("type"):
            lines.append(f'type = "{reg["type"]}"')
        if reg.get("mode"):
            lines.append(f'mode = "{reg["mode"]}"')
        if reg.get("unit"):
            lines.append(f'unit = "{reg["unit"]}"')
        scale = reg.get("scale", 1.0)
        if scale != 1.0:
            lines.append(f"scale = {scale}")
        lines.append(f"writable = {str(reg.get('writable', False)).lower()}")

    lines.append("")  # trailing newline
    return "\n".join(lines)


def _toml_value(v: object) -> str:
    """Format a Python value as a TOML literal."""
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, int):
        return str(v)
    if isinstance(v, float):
        return str(v)
    if isinstance(v, str):
        return f'"{v}"'
    return f'"{v}"'


def emit_bundle(output_dir: Path) -> Path:
    """Create bundle.tar.gz from the output directory contents."""
    bundle_path = output_dir / "bundle.tar.gz"
    with tarfile.open(bundle_path, "w:gz") as tar:
        for child in sorted(output_dir.iterdir()):
            if child.name == "bundle.tar.gz":
                continue
            tar.add(child, arcname=child.name)
    return bundle_path
