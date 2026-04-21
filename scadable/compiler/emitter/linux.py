"""Linux emitter — production target for v0.2.0.

Outputs:
  1. `drivers/{id}.yaml` — LEGACY per-device YAML configs. v0.1 shape,
     still produced for backward compatibility until the field is
     decommissioned in v0.3.
  2. `devices/{driver}.toml` — contract-crate format read by the new
     subprocess drivers (driver-modbus etc.). One file per driver,
     every device using that driver listed inside. This is what the
     gateway's pull/apply hands the driver on startup.
  3. `manifest.json` — shared schema (see base.py), with `drivers`
     added listing each bundled driver + version + sha256.
  4. `bundle.tar.gz` — tarball of everything above plus the fetched
     driver binaries under `drivers/{arch}/`.

The YAML and TOML paths coexist during the migration. The Rust-side
gateway (W4) reads ONLY the new TOML; the YAML sits in the bundle
unused until we drop it.
"""

from __future__ import annotations

from collections import defaultdict
from pathlib import Path
from typing import Any

import toml
import yaml

from .._drivers import PROTOCOL_TO_DRIVER
from .base import Emitter

# ── dtype / transport mapping tables ──────────────────────────────
#
# The SDK's device DSL uses names (uint16, float32, big) that map to
# shorter ones in the driver contract (u16, f32, big). These tables
# are the single source of truth for the mapping; add new entries in
# one place when a protocol gains a dtype.

_SDK_TO_CONTRACT_DTYPE: dict[str, str] = {
    "uint8": "u8",
    "int8": "i8",
    "uint16": "u16",
    "int16": "i16",
    "uint32": "u32",
    "int32": "i32",
    "uint64": "u64",
    "int64": "i64",
    "float32": "f32",
    "float64": "f64",
    "bool": "bool",
}

_SDK_TO_CONTRACT_ENDIANNESS: dict[str, str] = {
    "big": "big",
    "little": "little",
    "mixed": "mixed",
}

# modbus_tcp → transport=tcp (the driver handles both TCP and RTU
# behind one binary, distinguished by the transport field).
_PROTOCOL_TO_TRANSPORT: dict[str, str] = {
    "modbus_tcp": "tcp",
    "modbus_rtu": "rtu",
    "ble": "gatt",
    "gpio": "gpio",
    "i2c": "i2c",
    "spi": "spi",
    "can": "can",
    "rtsp": "rtsp",
    "serial": "serial",
}


class LinuxEmitter(Emitter):
    """Emits per-device YAML + per-driver TOML + manifest + bundle."""

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

    def emit_device_configs_contract(self, devices: list[dict], output_dir: Path) -> list[Path]:
        """Group devices by driver and emit one TOML file per driver,
        matching the `scadable-driver-contract::DeviceConfig` schema
        the Rust driver binaries deserialize on startup.

        Layout: output_dir/devices/{driver}.toml, one [[device]] entry
        per device and a nested [[device.register]] per register.

        Protocols with no known driver mapping (legacy SDK DSL that
        hasn't been wired yet) are silently skipped — the compile
        still succeeds but no driver is spawned for them, matching
        today's "no driver binaries exist" behavior.
        """
        grouped: dict[str, list[dict]] = defaultdict(list)
        for dev in devices:
            protocol = (dev.get("connection") or {}).get("protocol")
            driver = PROTOCOL_TO_DRIVER.get(protocol or "")
            if not driver:
                continue
            grouped[driver].append(_device_to_contract_dict(dev))

        devices_dir = output_dir / "devices"
        devices_dir.mkdir(parents=True, exist_ok=True)

        written: list[Path] = []
        for driver, entries in sorted(grouped.items()):
            body = {"device": entries}
            path = devices_dir / f"{driver}.toml"
            # toml.dumps preserves insertion order of dict keys and
            # emits [[device]] / [[device.register]] arrays of tables
            # exactly as the contract crate expects.
            path.write_text(toml.dumps(body))
            written.append(path)
        return written


# ── legacy YAML builder (unchanged) ───────────────────────────────


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


# ── new contract-shape builder ────────────────────────────────────


def _device_to_contract_dict(dev: dict) -> dict[str, Any]:
    """Shape one SDK device record as a contract-crate `Device`:
    transport-tagged, flat top-level fields for wire settings
    (host/port/serial_port/...), nested [[register]] list.
    """
    conn = dev.get("connection") or {}
    protocol = conn.get("protocol", "")
    transport = _PROTOCOL_TO_TRANSPORT.get(protocol, protocol)

    entry: dict[str, Any] = {
        "id": dev["id"],
        "transport": transport,
    }
    # poll_ms is required in the contract — default to 1000 if the
    # user didn't override (matches SDK's own default). Driver treats
    # any value < 50ms as 50ms anyway.
    entry["poll_ms"] = int(dev.get("poll_ms") or 1000)

    # unit_id lifts out of the connection dict into the typed slot
    # so the Rust side can parse it as u16 directly.
    if conn.get("unit_id") is not None:
        entry["unit_id"] = int(conn["unit_id"])

    # Everything else in `connection` (host, port, serial_port, baud,
    # parity, etc.) flattens into the device entry's extra fields,
    # which serde picks up via `#[serde(flatten)]` on `Device.extra`.
    for key, value in conn.items():
        if key in ("protocol", "unit_id"):
            continue
        entry[key] = value

    registers: list[dict[str, Any]] = []
    for reg in dev.get("registers", []):
        r: dict[str, Any] = {
            "name": reg.get("name") or str(reg.get("address", "")),
            "address": int(reg.get("address") or 0),
        }
        # SDK `type` → contract `fc`. Default "holding" matches the
        # contract crate's default_fc.
        reg_type = reg.get("type") or "holding"
        if reg_type != "holding":
            r["fc"] = reg_type

        sdk_dtype = reg.get("dtype")
        if sdk_dtype:
            mapped = _SDK_TO_CONTRACT_DTYPE.get(sdk_dtype, sdk_dtype)
            r["dtype"] = mapped

        endianness = reg.get("endianness") or "big"
        if endianness != "big":
            r["byte_order"] = _SDK_TO_CONTRACT_ENDIANNESS.get(endianness, endianness)

        # Transport-specific extras (uuid, pin, offset, length, scale,
        # unit, on_error, mode, writable) flow through unchanged so
        # drivers that use them can pick them up. The contract crate's
        # RegisterSpec `extra` absorbs unknown fields.
        for key in ("uuid", "pin", "offset", "length", "mode", "unit", "on_error"):
            if reg.get(key) is not None:
                r[key] = reg[key]
        scale = reg.get("scale", 1.0)
        if scale != 1.0:
            r["scale"] = scale
        if reg.get("writable"):
            r["writable"] = True

        registers.append(r)

    if registers:
        entry["register"] = registers
    return entry
