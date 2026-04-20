"""AST-based extraction of device and controller metadata.

All parsing is done via ast.parse() — user Python files are NEVER
imported or executed.
"""

from __future__ import annotations

import ast
import re
import textwrap
from pathlib import Path

# ── Protocol mapping ──────────────────────────────────────────────

PROTOCOL_MAP: dict[str, str] = {
    "modbus_tcp": "modbus_tcp",
    "modbus_rtu": "modbus_rtu",
    "ble": "ble",
    "gpio": "gpio",
    "serial": "serial",
    "i2c": "i2c",
    "rtsp": "rtsp",
}

# ── Time-unit multipliers (name in source → milliseconds) ────────

TIME_UNITS: dict[str, int] = {
    "SECONDS": 1_000,
    "MINUTES": 60_000,
    "HOURS": 3_600_000,
    "MILLISECONDS": 1,
    # Short forms used in TimeInterval
    "s": 1_000,
    "min": 60_000,
    "h": 3_600_000,
    "ms": 1,
}

# ── Register address ranges → type ───────────────────────────────


def _register_type(address: int) -> str:
    if 1 <= address <= 9999:
        return "coil"
    if 10000 <= address <= 19999:
        return "discrete_input"
    if 30000 <= address <= 39999:
        return "input"
    if 40000 <= address <= 49999:
        return "holding"
    return "unknown"


def _register_writable(address: int, explicit: bool | None) -> bool:
    if explicit is not None:
        return explicit
    rtype = _register_type(address)
    return rtype in ("coil", "holding")


# ── Constant extraction helpers ──────────────────────────────────


def _const(node: ast.expr) -> object:
    """Return the Python literal value from an AST node, or None."""
    if isinstance(node, ast.Constant):
        return node.value
    if isinstance(node, ast.Name):
        # Resolve time-unit names to their string values
        if node.id in TIME_UNITS:
            return node.id
        return node.id
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.USub):
        inner = _const(node.operand)
        if isinstance(inner, (int, float)):
            return -inner
    return None


def _const_strict(node: ast.expr) -> object:
    """Like _const but only returns actual constant values."""
    if isinstance(node, ast.Constant):
        return node.value
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.USub):
        inner = _const_strict(node.operand)
        if isinstance(inner, (int, float)):
            return -inner
    return None


def _keywords_dict(call: ast.Call) -> dict[str, object]:
    """Extract keyword arguments from an ast.Call as {name: value}."""
    out: dict[str, object] = {}
    for kw in call.keywords:
        if kw.arg is not None:
            out[kw.arg] = _const(kw.value)
    return out


def _call_func_name(node: ast.Call) -> str | None:
    """Return the function name from an ast.Call, or None."""
    if isinstance(node.func, ast.Name):
        return node.func.id
    if isinstance(node.func, ast.Attribute):
        return node.func.attr
    return None


# ── Time interval parsing ────────────────────────────────────────


def _parse_time_call(node: ast.expr) -> int | None:
    """Parse every(5, SECONDS) → milliseconds, or None."""
    if not isinstance(node, ast.Call):
        return None
    fname = _call_func_name(node)
    if fname != "every":
        return None
    if len(node.args) < 1:
        return None

    value = _const(node.args[0])
    if not isinstance(value, (int, float)):
        return None

    unit_name = "SECONDS"  # default
    if len(node.args) >= 2:
        u = _const(node.args[1])
        if isinstance(u, str):
            unit_name = u

    multiplier = TIME_UNITS.get(unit_name, 1_000)
    return int(value * multiplier)


# ── Connection parsing ───────────────────────────────────────────


def _parse_connection(node: ast.expr) -> dict | None:
    """Parse modbus_tcp(host=..., port=...) → dict."""
    if not isinstance(node, ast.Call):
        return None

    fname = _call_func_name(node)
    if fname is None or fname not in PROTOCOL_MAP:
        return None

    protocol = PROTOCOL_MAP[fname]
    kwargs = _keywords_dict(node)

    # Also capture positional args for protocols that accept them
    conn: dict = {"protocol": protocol}
    conn.update(kwargs)
    return conn


# ── Register parsing ─────────────────────────────────────────────


def _parse_register_call(node: ast.Call) -> dict | None:
    """Parse Register(40001, "temperature", unit="C", scale=0.1) → dict."""
    fname = _call_func_name(node)
    if fname is None:
        return None

    kwargs = _keywords_dict(node)

    if fname == "Register":
        if len(node.args) < 2:
            return None
        address = _const(node.args[0])
        name = _const(node.args[1])
        if not isinstance(address, int) or not isinstance(name, str):
            return None

        explicit_writable = kwargs.get("writable")
        if explicit_writable is not None:
            explicit_writable = bool(explicit_writable)

        return {
            "kind": "register",
            "address": address,
            "name": name,
            "type": _register_type(address),
            "dtype": kwargs.get("dtype", "uint16"),
            "endianness": kwargs.get("endianness", "big"),
            "on_error": kwargs.get("on_error", "skip"),
            "unit": kwargs.get("unit", ""),
            "scale": kwargs.get("scale", 1.0),
            "writable": _register_writable(address, explicit_writable),
            "store": kwargs.get("store", True),
        }

    if fname == "Characteristic":
        if len(node.args) < 2:
            return None
        uuid = _const(node.args[0])
        name = _const(node.args[1])
        if not isinstance(uuid, str) or not isinstance(name, str):
            return None
        return {
            "kind": "characteristic",
            "uuid": uuid,
            "name": name,
            "unit": kwargs.get("unit", ""),
            "scale": kwargs.get("scale", 1.0),
            "writable": False,
            "store": kwargs.get("store", True),
        }

    if fname == "Pin":
        if len(node.args) < 2:
            return None
        pin = _const(node.args[0])
        name = _const(node.args[1])
        if not isinstance(pin, int) or not isinstance(name, str):
            return None
        mode = kwargs.get("mode", "input")
        return {
            "kind": "pin",
            "pin": pin,
            "name": name,
            "mode": mode,
            "trigger": kwargs.get("trigger"),
            "unit": kwargs.get("unit", ""),
            "scale": kwargs.get("scale", 1.0),
            "writable": mode == "output",
            "store": kwargs.get("store", True),
        }

    if fname == "Field":
        if len(node.args) < 2:
            return None
        offset = _const(node.args[0])
        length = _const(node.args[1])
        name = ""
        if len(node.args) >= 3:
            name = _const(node.args[2]) or ""
        if not isinstance(offset, int) or not isinstance(length, int):
            return None
        if not isinstance(name, str):
            name = kwargs.get("name", "")
        return {
            "kind": "field",
            "offset": offset,
            "length": length,
            "name": name if name else kwargs.get("name", ""),
            "unit": kwargs.get("unit", ""),
            "scale": kwargs.get("scale", 1.0),
            "writable": False,
            "store": kwargs.get("store", True),
        }

    return None


def _parse_registers_list(node: ast.List) -> list[dict]:
    """Parse a list of Register/Characteristic/Pin/Field calls."""
    regs: list[dict] = []
    for elt in node.elts:
        if isinstance(elt, ast.Call):
            parsed = _parse_register_call(elt)
            if parsed:
                regs.append(parsed)
    return regs


# ── Device class parsing ─────────────────────────────────────────


def _parse_device_class(cls: ast.ClassDef, source_path: Path) -> dict | None:
    """Extract device metadata from an AST class definition."""
    # Check that class inherits from Device
    is_device = any((isinstance(b, ast.Name) and b.id == "Device") for b in cls.bases)
    if not is_device:
        return None

    device: dict = {
        "class_name": cls.name,
        "source_file": str(source_path),
        "id": "",
        "name": "",
        "connection": None,
        "poll_ms": None,
        "heartbeat_ms": None,
        "health_timeout": None,
        "historian_ms": None,
        "registers": [],
    }

    for node in cls.body:
        if not isinstance(node, ast.Assign):
            continue
        for target in node.targets:
            if not isinstance(target, ast.Name):
                continue
            attr = target.id
            val = node.value

            if attr == "id":
                v = _const_strict(val)
                if isinstance(v, str):
                    device["id"] = v

            elif attr == "name":
                v = _const_strict(val)
                if isinstance(v, str):
                    device["name"] = v

            elif attr == "connection":
                device["connection"] = _parse_connection(val)

            elif attr == "poll":
                device["poll_ms"] = _parse_time_call(val)

            elif attr == "heartbeat":
                device["heartbeat_ms"] = _parse_time_call(val)

            elif attr == "health_timeout":
                v = _const_strict(val)
                if isinstance(v, int):
                    device["health_timeout"] = v

            elif attr == "historian":
                device["historian_ms"] = _parse_time_call(val)

            elif attr == "registers":
                if isinstance(val, ast.List):
                    device["registers"] = _parse_registers_list(val)

    # Skip classes without an id
    if not device["id"]:
        return None

    return device


def parse_devices(
    files: list[Path],
) -> tuple[list[dict], dict[str, str], list[str]]:
    """Parse all device files and return (devices, class_name_to_id_map, warnings).

    SyntaxError on a device file no longer silently skips — the file
    name + the first error line is captured as a warning, returned to
    the caller, and surfaced on the CLI. Silent skips were the #1
    "why isn't my device showing up" support question.
    """
    devices: list[dict] = []
    class_map: dict[str, str] = {}  # ClassName → device_id
    warnings: list[str] = []

    for fpath in files:
        try:
            tree = ast.parse(fpath.read_text(), filename=str(fpath))
        except SyntaxError as e:
            warnings.append(
                f"skipped device file {fpath} — SyntaxError on line {e.lineno}: {e.msg}"
            )
            continue

        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef):
                dev = _parse_device_class(node, fpath)
                if dev:
                    devices.append(dev)
                    class_map[dev["class_name"]] = dev["id"]

    return devices, class_map, warnings


# ── Controller / trigger parsing ─────────────────────────────────


def _to_snake_case(name: str) -> str:
    """Convert CamelCase to snake_case."""
    s = re.sub(r"([A-Z]+)([A-Z][a-z])", r"\1_\2", name)
    s = re.sub(r"([a-z\d])([A-Z])", r"\1_\2", s)
    return s.lower()


def _resolve_device_ref(node: ast.expr, class_map: dict[str, str]) -> str | None:
    """Resolve a device class reference (Name) to its device id."""
    if isinstance(node, ast.Name) and node.id in class_map:
        return class_map[node.id]
    return None


def _resolve_field_ref(
    node: ast.expr,
    class_map: dict[str, str],
) -> tuple[str | None, str | None]:
    """Resolve Device.field_name → (device_id, field_name)."""
    if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name):
        class_name = node.value.id
        field_name = node.attr
        device_id = class_map.get(class_name)
        return device_id, field_name
    return None, None


def _parse_decorator(
    decorator: ast.expr,
    method_name: str,
    class_map: dict[str, str],
    source_lines: list[str],
    method_node: ast.FunctionDef,
) -> dict | None:
    """Parse a single @on.xxx decorator into a trigger dict."""

    # @on.startup / @on.shutdown (bare attribute, no call)
    if isinstance(decorator, ast.Attribute):
        if isinstance(decorator.value, ast.Name) and decorator.value.id == "on":
            attr = decorator.attr
            if attr in ("startup", "shutdown"):
                return {
                    "type": attr,
                    "method": method_name,
                    "source": _extract_method_source(source_lines, method_node),
                }
        return None

    if not isinstance(decorator, ast.Call):
        return None

    func = decorator.func
    if not (
        isinstance(func, ast.Attribute)
        and isinstance(func.value, ast.Name)
        and func.value.id == "on"
    ):
        return None

    trigger_type = func.attr
    kwargs = _keywords_dict(decorator)
    source = _extract_method_source(source_lines, method_node)

    if trigger_type == "interval":
        if len(decorator.args) < 1:
            return None
        value = _const(decorator.args[0])
        if not isinstance(value, (int, float)):
            return None
        unit_name = "SECONDS"
        if len(decorator.args) >= 2:
            u = _const(decorator.args[1])
            if isinstance(u, str):
                unit_name = u
        multiplier = TIME_UNITS.get(unit_name, 1_000)
        return {
            "type": "interval",
            "method": method_name,
            "interval_ms": int(value * multiplier),
            "source": source,
        }

    if trigger_type == "data":
        if len(decorator.args) < 1:
            return None
        device_id = _resolve_device_ref(decorator.args[0], class_map)
        return {
            "type": "data",
            "method": method_name,
            "device": device_id or _const(decorator.args[0]),
            "source": source,
        }

    if trigger_type == "change":
        if len(decorator.args) < 1:
            return None
        dev_id, field_name = _resolve_field_ref(decorator.args[0], class_map)
        field_ref = f"{dev_id}.{field_name}" if dev_id and field_name else None
        return {
            "type": "change",
            "method": method_name,
            "field": field_ref,
            "delta": kwargs.get("delta", 0),
            "source": source,
        }

    if trigger_type == "threshold":
        if len(decorator.args) < 1:
            return None
        dev_id, field_name = _resolve_field_ref(decorator.args[0], class_map)
        field_ref = f"{dev_id}.{field_name}" if dev_id and field_name else None
        trigger: dict = {
            "type": "threshold",
            "method": method_name,
            "field": field_ref,
            "source": source,
        }
        if "above" in kwargs:
            trigger["above"] = kwargs["above"]
        if "below" in kwargs:
            trigger["below"] = kwargs["below"]
        return trigger

    if trigger_type == "message":
        if len(decorator.args) < 1:
            return None
        topic = _const(decorator.args[0])
        return {
            "type": "message",
            "method": method_name,
            "topic": topic,
            "source": source,
        }

    if trigger_type == "device":
        if len(decorator.args) < 1:
            return None
        device_id = _resolve_device_ref(decorator.args[0], class_map)
        status = None
        if len(decorator.args) >= 2:
            status = _const(decorator.args[1])
        return {
            "type": "device",
            "method": method_name,
            "device": device_id or _const(decorator.args[0]),
            "status": status,
            "source": source,
        }

    if trigger_type in ("startup", "shutdown"):
        return {
            "type": trigger_type,
            "method": method_name,
            "source": source,
        }

    return None


def _extract_method_source(source_lines: list[str], node: ast.FunctionDef) -> str:
    """Extract the method body source code (excluding decorators)."""
    start = node.lineno - 1  # 0-indexed
    end = node.end_lineno if node.end_lineno else start + 1
    lines = source_lines[start:end]
    return textwrap.dedent("\n".join(lines))


def _parse_controller_class(
    cls: ast.ClassDef,
    source_lines: list[str],
    source_path: Path,
    class_map: dict[str, str],
) -> dict | None:
    """Extract controller metadata from an AST class definition."""
    is_controller = any((isinstance(b, ast.Name) and b.id == "Controller") for b in cls.bases)
    if not is_controller:
        return None

    controller_id = _to_snake_case(cls.name)
    triggers: list[dict] = []

    for node in ast.walk(cls):
        if not isinstance(node, ast.FunctionDef):
            continue
        for dec in node.decorator_list:
            parsed = _parse_decorator(dec, node.name, class_map, source_lines, node)
            if parsed:
                triggers.append(parsed)

    return {
        "class_name": cls.name,
        "id": controller_id,
        "source_file": str(source_path),
        "triggers": triggers,
    }


def parse_controllers(
    files: list[Path],
    class_map: dict[str, str],
) -> tuple[list[dict], list[str]]:
    """Parse all controller files. Returns (controllers, warnings).

    SyntaxError on a controller file no longer silently skips — see
    parse_devices() for the rationale.
    """
    controllers: list[dict] = []
    warnings: list[str] = []

    for fpath in files:
        try:
            text = fpath.read_text()
            tree = ast.parse(text, filename=str(fpath))
        except SyntaxError as e:
            warnings.append(
                f"skipped controller file {fpath} — SyntaxError on line {e.lineno}: {e.msg}"
            )
            continue

        source_lines = text.splitlines()

        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef):
                ctrl = _parse_controller_class(node, source_lines, fpath, class_map)
                if ctrl:
                    controllers.append(ctrl)

    return controllers, warnings
