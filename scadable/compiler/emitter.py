"""Output generation — manifest.json, driver YAMLs, bundle.tar.gz.

v0.2.0 emits YAML for driver configs (was TOML). gateway-linux's
DriverManager reads `config.yaml` (or `config.json`) per device dir;
TOML required a manual conversion step that nobody did. The schema
itself is unchanged — same field names, same nesting — only the
serialization format flipped.
"""

from __future__ import annotations

import json
import tarfile
from dataclasses import asdict
from pathlib import Path
from typing import Any

import yaml

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
    """Write a YAML driver config for each device and return the paths.

    File naming: `drivers/{device_id}.yaml`. The gateway expects this
    layout under `/etc/scadable/devices/{device_id}/config.yaml` on
    deploy.
    """
    drivers_dir = output_dir / "drivers"
    drivers_dir.mkdir(parents=True, exist_ok=True)

    paths: list[Path] = []
    for dev in devices:
        path = drivers_dir / f"{dev['id']}.yaml"
        path.write_text(yaml.safe_dump(_device_to_dict(dev), sort_keys=False, allow_unicode=True))
        paths.append(path)
    return paths


def _device_to_dict(dev: dict) -> dict[str, Any]:
    """Build the per-device YAML body. Pure data — yaml.safe_dump
    handles serialization. Keeps the same logical schema we used in
    TOML so existing readers can swap in without renaming fields.
    """
    conn = dev.get("connection") or {}

    device_section: dict[str, Any] = {
        "id": dev["id"],
        "protocol": conn.get("protocol", ""),
    }
    if dev.get("name"):
        device_section["name"] = dev["name"]
    for key in ("poll_ms", "heartbeat_ms", "health_timeout", "historian_ms"):
        if dev.get(key) is not None:
            device_section[key] = dev[key]

    connection_section = {k: v for k, v in conn.items() if k != "protocol"}

    registers_section: list[dict[str, Any]] = []
    for reg in dev.get("registers", []):
        item: dict[str, Any] = {}
        if reg.get("name"):
            item["name"] = reg["name"]
        for key in ("address", "uuid", "pin", "offset", "length"):
            if key in reg and reg[key] is not None:
                item[key] = reg[key]
        if reg.get("type"):
            item["type"] = reg["type"]
        if reg.get("dtype"):
            item["dtype"] = reg["dtype"]
        if reg.get("endianness") and reg["endianness"] != "big":
            item["endianness"] = reg["endianness"]
        if reg.get("on_error"):
            item["on_error"] = reg["on_error"]
        if reg.get("mode"):
            item["mode"] = reg["mode"]
        if reg.get("unit"):
            item["unit"] = reg["unit"]
        scale = reg.get("scale", 1.0)
        if scale != 1.0:
            item["scale"] = scale
        item["writable"] = bool(reg.get("writable", False))
        registers_section.append(item)

    body: dict[str, Any] = {"device": device_section}
    if connection_section:
        body["connection"] = connection_section
    if registers_section:
        body["registers"] = registers_section
    return body


def emit_bundle(output_dir: Path) -> Path:
    """Create bundle.tar.gz from the output directory contents."""
    bundle_path = output_dir / "bundle.tar.gz"
    with tarfile.open(bundle_path, "w:gz") as tar:
        for child in sorted(output_dir.iterdir()):
            if child.name == "bundle.tar.gz":
                continue
            tar.add(child, arcname=child.name)
    return bundle_path
