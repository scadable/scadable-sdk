"""Portability: target capability matrix invariants.

These guardrails make sure adding ESP32 / RTOS emitters later is
additive, not a rewrite. Anything that hard-codes a Linux-ism
(file paths, threads, processes) here would silently break the
portability story.
"""

from __future__ import annotations

import pytest

from scadable._targets import (
    TARGETS,
    TargetNotImplementedError,
    get_target,
    is_supported_dtype,
    is_supported_protocol,
)

# ── target registry shape ────────────────────────────────────────


def test_three_targets_registered():
    assert set(TARGETS) == {"linux", "esp32", "rtos"}


def test_each_target_has_required_keys():
    for name, spec in TARGETS.items():
        for k in ("memory_kb", "protocols", "dtypes", "controller_execution", "status"):
            assert k in spec, f"target {name} missing key {k}"


def test_status_values_are_known():
    for name, spec in TARGETS.items():
        assert spec["status"] in (
            "production",
            "connection_only",
            "preview",
            "not-implemented",
        ), f"target {name} has unknown status {spec['status']}"


# ── linux is the production target ───────────────────────────────


def test_linux_status_is_production():
    assert TARGETS["linux"]["status"] == "production"


def test_linux_supports_every_protocol_we_emit():
    for proto in ("modbus_tcp", "modbus_rtu", "ble", "gpio", "serial", "i2c", "rtsp"):
        assert is_supported_protocol("linux", proto)


def test_linux_supports_every_dtype():
    for dt in ("uint16", "int16", "uint32", "int32", "float32", "float64", "bool"):
        assert is_supported_dtype("linux", dt)


def test_linux_unbounded_memory():
    assert TARGETS["linux"]["memory_kb"] is None


# ── esp32 + rtos are preview ─────────────────────────────────────


def test_esp32_status_is_connection_only():
    # gateway-esp MVP ships a runtime that connects + streams logs but the
    # SDK project-bundle compile path is still pending. See _targets.py.
    assert TARGETS["esp32"]["status"] == "connection_only"


def test_rtos_status_is_preview():
    assert TARGETS["rtos"]["status"] == "preview"


def test_esp32_rejects_modbus_tcp():
    """ESP32 can't host a Modbus TCP master at scale."""
    assert not is_supported_protocol("esp32", "modbus_tcp")


def test_esp32_rejects_rtsp():
    """RTSP video over WiFi-only ESP32 is impractical."""
    assert not is_supported_protocol("esp32", "rtsp")


def test_rtos_rejects_float64():
    """No double-precision floats on tight RTOS budgets."""
    assert not is_supported_dtype("rtos", "float64")


def test_rtos_supports_uint16():
    assert is_supported_dtype("rtos", "uint16")


# ── error surfacing ──────────────────────────────────────────────


def test_get_target_unknown_raises_value_error():
    with pytest.raises(ValueError) as exc:
        get_target("plan9")
    assert "plan9" in str(exc.value)
    # Error message should list known targets so the user knows what's valid
    assert "linux" in str(exc.value)


def test_target_not_implemented_error_subclass_of_notimplemented():
    """Catching `NotImplementedError` should also catch ours, so users
    using broad exception handlers don't break."""
    assert issubclass(TargetNotImplementedError, NotImplementedError)
