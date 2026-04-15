"""Cross-reference validation for compiled projects."""

from __future__ import annotations


def validate(
    devices: list[dict],
    controllers: list[dict],
    class_map: dict[str, str],
) -> tuple[list[str], list[str]]:
    """Validate cross-references between devices and controllers.

    Returns (errors, warnings).
    """
    errors: list[str] = []
    warnings: list[str] = []

    # Build a set of all device_id.register_name pairs
    field_index: set[str] = set()
    device_ids: set[str] = set()

    for dev in devices:
        did = dev["id"]
        device_ids.add(did)

        # Check for duplicate register addresses within a device
        seen_addresses: dict[int, str] = {}
        for reg in dev.get("registers", []):
            addr = reg.get("address")
            name = reg.get("name", "")
            if addr is not None:
                if addr in seen_addresses:
                    errors.append(
                        f"Device '{did}': duplicate register address {addr} "
                        f"('{seen_addresses[addr]}' and '{name}')"
                    )
                seen_addresses[addr] = name
            field_index.add(f"{did}.{name}")

        # Check connection params
        conn = dev.get("connection")
        if conn is None:
            errors.append(f"Device '{did}': no connection defined")
        else:
            _validate_connection(did, conn, errors, warnings)

    # Validate controller triggers
    for ctrl in controllers:
        for trigger in ctrl.get("triggers", []):
            _validate_trigger(ctrl["id"], trigger, device_ids, field_index,
                              errors, warnings)

    return errors, warnings


def _validate_connection(
    device_id: str,
    conn: dict,
    errors: list[str],
    warnings: list[str],
) -> None:
    """Validate connection parameters for a given protocol."""
    protocol = conn.get("protocol", "")

    if protocol == "modbus_tcp":
        host = conn.get("host", "")
        if not host:
            warnings.append(f"Device '{device_id}': modbus_tcp host is empty")
    elif protocol == "modbus_rtu":
        port = conn.get("port", "")
        if not port:
            warnings.append(f"Device '{device_id}': modbus_rtu port is empty")
    elif protocol == "ble":
        mac = conn.get("mac", "")
        if not mac:
            warnings.append(f"Device '{device_id}': BLE mac address is empty")
    elif protocol == "serial":
        port = conn.get("port", "")
        if not port:
            warnings.append(f"Device '{device_id}': serial port is empty")
    elif protocol == "rtsp":
        url = conn.get("url", "")
        if not url:
            warnings.append(f"Device '{device_id}': RTSP url is empty")


def _validate_trigger(
    controller_id: str,
    trigger: dict,
    device_ids: set[str],
    field_index: set[str],
    errors: list[str],
    warnings: list[str],
) -> None:
    """Validate a single controller trigger."""
    ttype = trigger.get("type", "")
    method = trigger.get("method", "")

    if ttype == "data":
        dev = trigger.get("device")
        if isinstance(dev, str) and dev not in device_ids:
            errors.append(
                f"Controller '{controller_id}': @on.data in {method} "
                f"references unknown device '{dev}'"
            )

    elif ttype in ("change", "threshold"):
        field = trigger.get("field")
        if isinstance(field, str) and field not in field_index:
            errors.append(
                f"Controller '{controller_id}': @on.{ttype} in {method} "
                f"references unknown field '{field}'"
            )

    elif ttype == "device":
        dev = trigger.get("device")
        if isinstance(dev, str) and dev not in device_ids:
            errors.append(
                f"Controller '{controller_id}': @on.device in {method} "
                f"references unknown device '{dev}'"
            )
