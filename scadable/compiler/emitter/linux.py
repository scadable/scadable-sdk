"""Linux emitter — production target for v0.2.0.

Outputs YAML driver configs that gateway-linux's DriverManager reads
on boot. Schema is identical to what every other emitter would produce
in its own format — same field names, same nesting, just YAML on the
wire. This keeps the abstract schema portable across targets.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from .base import Emitter


class LinuxEmitter(Emitter):
    """Emits YAML driver configs + manifest.json + bundle.tar.gz."""

    def emit_driver_configs(self, devices: list[dict], output_dir: Path) -> list[Path]:
        drivers_dir = output_dir / "drivers"
        drivers_dir.mkdir(parents=True, exist_ok=True)

        paths: list[Path] = []
        for dev in devices:
            path = drivers_dir / f"{dev['id']}.yaml"
            path.write_text(
                yaml.safe_dump(
                    _device_to_dict(dev),
                    sort_keys=False,
                    allow_unicode=True,
                )
            )
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
