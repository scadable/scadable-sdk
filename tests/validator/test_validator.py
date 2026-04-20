"""Validator: cross-references, missing fields, target capability matrix."""

from __future__ import annotations

from scadable.compiler.validator import validate


# ── duplicate addresses ──────────────────────────────────────────


def test_duplicate_addresses_in_one_device_errors():
    devs = [{
        "id": "d", "connection": {"protocol": "modbus_tcp", "host": "x"},
        "registers": [
            {"address": 40001, "name": "a"},
            {"address": 40001, "name": "b"},
        ],
    }]
    errors, _ = validate(devs, [], {})
    assert any("duplicate" in e.lower() and "40001" in e for e in errors)


def test_distinct_addresses_no_error():
    devs = [{
        "id": "d", "connection": {"protocol": "modbus_tcp", "host": "x"},
        "registers": [
            {"address": 40001, "name": "a"},
            {"address": 40002, "name": "b"},
        ],
    }]
    errors, _ = validate(devs, [], {})
    assert errors == []


# ── missing connection ───────────────────────────────────────────


def test_device_without_connection_errors():
    devs = [{"id": "d", "connection": None, "registers": []}]
    errors, _ = validate(devs, [], {})
    assert any("connection" in e for e in errors)


def test_modbus_tcp_no_host_warns():
    devs = [{
        "id": "d", "connection": {"protocol": "modbus_tcp"},
        "registers": [{"address": 40001, "name": "x"}],
    }]
    errors, warnings = validate(devs, [], {})
    assert errors == []
    assert any("host" in w for w in warnings)


def test_ble_no_mac_warns():
    devs = [{
        "id": "d", "connection": {"protocol": "ble"}, "registers": [],
    }]
    _, warnings = validate(devs, [], {})
    assert any("mac" in w.lower() for w in warnings)


def test_serial_no_port_warns():
    devs = [{
        "id": "d", "connection": {"protocol": "serial"}, "registers": [],
    }]
    _, warnings = validate(devs, [], {})
    assert any("port" in w for w in warnings)


def test_rtsp_no_url_warns():
    devs = [{
        "id": "d", "connection": {"protocol": "rtsp"}, "registers": [],
    }]
    _, warnings = validate(devs, [], {})
    assert any("url" in w.lower() for w in warnings)


# ── controller refs ──────────────────────────────────────────────


def test_controller_unknown_device_in_data_trigger_errors():
    ctrls = [{"id": "c", "triggers": [
        {"type": "data", "method": "m", "device": "ghost"},
    ]}]
    errors, _ = validate([], ctrls, {})
    assert any("ghost" in e for e in errors)


def test_controller_unknown_field_in_change_trigger_errors():
    ctrls = [{"id": "c", "triggers": [
        {"type": "change", "method": "m", "field": "ghost.x"},
    ]}]
    errors, _ = validate([], ctrls, {})
    assert any("ghost.x" in e for e in errors)


def test_controller_known_field_no_error():
    devs = [{
        "id": "d", "connection": {"protocol": "modbus_tcp", "host": "x"},
        "registers": [{"address": 40001, "name": "temp"}],
    }]
    ctrls = [{"id": "c", "triggers": [
        {"type": "change", "method": "m", "field": "d.temp"},
    ]}]
    errors, _ = validate(devs, ctrls, {})
    assert errors == []


# ── target capability matrix ─────────────────────────────────────


def test_unknown_target_errors():
    errors, _ = validate([], [], {}, target="windows")
    assert any("unknown target" in e.lower() for e in errors)


def test_modbus_tcp_on_esp32_rejected():
    devs = [{
        "id": "d", "connection": {"protocol": "modbus_tcp", "host": "x"},
        "registers": [{"address": 40001, "name": "x", "dtype": "uint16"}],
    }]
    errors, _ = validate(devs, [], {}, target="esp32")
    assert any("modbus_tcp" in e and "esp32" in e for e in errors)


def test_modbus_rtu_on_esp32_accepted():
    devs = [{
        "id": "d", "connection": {"protocol": "modbus_rtu", "port": "/dev/ttyS0"},
        "registers": [{"address": 40001, "name": "x", "dtype": "uint16"}],
    }]
    errors, _ = validate(devs, [], {}, target="esp32")
    assert errors == []


def test_float64_on_rtos_rejected():
    devs = [{
        "id": "d", "connection": {"protocol": "modbus_rtu", "port": "/dev/ttyS0"},
        "registers": [{"address": 40001, "name": "x", "dtype": "float64"}],
    }]
    errors, _ = validate(devs, [], {}, target="rtos")
    assert any("float64" in e and "rtos" in e for e in errors)


def test_uint16_on_rtos_accepted():
    devs = [{
        "id": "d", "connection": {"protocol": "modbus_rtu", "port": "/dev/ttyS0"},
        "registers": [{"address": 40001, "name": "x", "dtype": "uint16"}],
    }]
    errors, _ = validate(devs, [], {}, target="rtos")
    assert errors == []


def test_preview_target_emits_warning():
    """esp32 + rtos are in preview status — should warn."""
    devs = [{
        "id": "d", "connection": {"protocol": "modbus_rtu", "port": "/dev/ttyS0"},
        "registers": [{"address": 40001, "name": "x", "dtype": "uint16"}],
    }]
    _, warnings = validate(devs, [], {}, target="esp32")
    assert any("preview" in w.lower() for w in warnings)


def test_production_target_no_preview_warning():
    devs = [{
        "id": "d", "connection": {"protocol": "modbus_tcp", "host": "x"},
        "registers": [{"address": 40001, "name": "x", "dtype": "uint16"}],
    }]
    _, warnings = validate(devs, [], {}, target="linux")
    assert not any("preview" in w.lower() for w in warnings)


# ── multi-device cross-checks ────────────────────────────────────


def test_same_address_across_different_devices_ok():
    """Address collision is per-device, not global."""
    devs = [
        {"id": "d1", "connection": {"protocol": "modbus_tcp", "host": "x"},
         "registers": [{"address": 40001, "name": "x"}]},
        {"id": "d2", "connection": {"protocol": "modbus_tcp", "host": "y"},
         "registers": [{"address": 40001, "name": "x"}]},
    ]
    errors, _ = validate(devs, [], {})
    assert errors == []
