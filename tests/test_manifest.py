"""Tests for `scadable.manifest` — the hardware.toml loader.

Covers W1 SDK side: schema parsing, default-fill for missing sections,
typed accessors, error reporting. Mirrors the Rust-side tests in
`gateway-linux/src/hardware/mod.rs` so the same fixtures parse
identically across both sides of the platform.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from scadable.manifest import (
    DEFAULT_HEARTBEAT_GRACE_FACTOR,
    DEFAULT_HEARTBEAT_INTERVAL_SECS,
    DEFAULT_LOG_BATCH_INTERVAL_SECS,
    DEFAULT_METRICS_INTERVAL_SECS,
    HardwareManifest,
    ManifestParseError,
    load_manifest,
    parse_manifest,
)


# ----------------------------------------------------------------------
# Fixtures — keep TOML literals in one place so cross-platform parity
# tests can re-use the exact same input bytes.
# ----------------------------------------------------------------------


MINIMAL_MANIFEST = """
[chip]
family = "esp32"
"""


FULL_ESP_MANIFEST = """
[chip]
family = "esp32-s3"
revision = "v0.2"
flash_size_mb = 8
psram_size_mb = 8

[peripherals]
wifi = true
ble = true
ethernet = false

[firmware]
variant = "verdant"
sdk_version = "0.5.12"

[pins]
door_reed   = 27
status_led  = 2
sd_cs       = 5
i2c_sda     = 21
i2c_scl     = 22

[modules]
i2c        = { enabled = true,  freq_hz = 400000 }
i2s        = { enabled = true,  sample_rate = 16000, bits = 16, mode = "mono" }
sd         = { enabled = true,  bus = "spi", cs_pin = "sd_cs" }
esp_now_lr = { enabled = true,  channel = 1 }
deep_sleep = { enabled = true,  default_timeout_secs = 1800 }

[memory]
reserved_heap_kb = 80

[telemetry]
heartbeat_interval_secs = 86400
heartbeat_grace_factor  = 1.5
log_batch_interval_secs = 86400
log_batch_max_records   = 5000
metrics_interval_secs   = 3600
"""


FULL_PI_MANIFEST = """
[chip]
family = "raspberry-pi-4"
ram_mb = 4096

[pins]
door_reed = 17
status_led = 22
relay      = 23

[modules]
i2c        = { enabled = true, bus = 1, freq_hz = 400000 }
gpio       = { enabled = true }
serial     = { enabled = true, device = "/dev/ttyAMA0", baud = 115200 }
modbus_tcp = { enabled = false }
modbus_rtu = { enabled = false }
ble        = { enabled = false }

[memory]
reserved_heap_kb = 0

[telemetry]
heartbeat_interval_secs = 60
heartbeat_grace_factor  = 1.1
log_batch_interval_secs = 0
log_batch_max_records   = 5000
metrics_interval_secs   = 30
"""


# ----------------------------------------------------------------------
# Test 1: minimal manifest — only [chip] declared, everything else None
# / empty / default.
# ----------------------------------------------------------------------


def test_loads_minimal_manifest(tmp_path: Path) -> None:
    p = tmp_path / "hardware.toml"
    p.write_text(MINIMAL_MANIFEST)

    m = load_manifest(p)

    assert isinstance(m, HardwareManifest)
    assert m.chip.family == "esp32"
    # Every optional chip field must be None on a minimal manifest.
    assert m.chip.revision is None
    assert m.chip.flash_size_mb is None
    assert m.chip.psram_size_mb is None
    assert m.chip.ram_mb is None
    # Optional sections all default-fill, no AttributeError.
    assert m.pins == {}
    assert m.modules == {}
    assert m.peripherals.wifi is False
    assert m.peripherals.ble is False
    assert m.firmware.variant is None
    assert m.memory.reserved_heap_kb == 0
    # Telemetry defaults match the firmware's pre-W5 hardcoded behavior.
    assert m.telemetry.heartbeat_interval_secs == DEFAULT_HEARTBEAT_INTERVAL_SECS
    assert m.telemetry.metrics_interval_secs == DEFAULT_METRICS_INTERVAL_SECS
    # source_path round-trips so callers can produce filename-aware errors.
    assert m.source_path == p


# ----------------------------------------------------------------------
# Test 2: full ESP manifest exercises every accessor on the ESP module
# set (i2c, i2s, sd, esp_now_lr, deep_sleep).
# ----------------------------------------------------------------------


def test_loads_full_esp_manifest() -> None:
    m = parse_manifest(FULL_ESP_MANIFEST)

    assert m.chip.family == "esp32-s3"
    assert m.chip.flash_size_mb == 8
    assert m.chip.psram_size_mb == 8

    assert m.peripherals.wifi is True
    assert m.peripherals.ble is True
    assert m.peripherals.ethernet is False

    assert m.firmware.variant == "verdant"
    assert m.firmware.sdk_version == "0.5.12"

    # Every ESP module declared above is reachable + enabled.
    for name in ("i2c", "i2s", "sd", "esp_now_lr", "deep_sleep"):
        assert m.module_enabled(name) is True, f"{name!r} should be enabled"
        assert m.module(name) is not None
    # Module-specific config preserved verbatim.
    assert m.module("i2c") == {"enabled": True, "freq_hz": 400000}
    assert m.module("deep_sleep") == {"enabled": True, "default_timeout_secs": 1800}

    # Pins resolve.
    assert m.pin("door_reed") == 27
    assert m.pin("i2c_sda") == 21

    # Telemetry honors operator overrides.
    assert m.telemetry.heartbeat_interval_secs == 86400
    assert m.telemetry.heartbeat_grace_factor == 1.5
    assert m.telemetry.metrics_interval_secs == 3600

    assert m.memory.reserved_heap_kb == 80


# ----------------------------------------------------------------------
# Test 3: full Pi manifest — same shape, Linux module set instead.
# Confirms the loader doesn't hard-code a known-modules whitelist.
# ----------------------------------------------------------------------


def test_loads_full_pi_manifest() -> None:
    m = parse_manifest(FULL_PI_MANIFEST)

    assert m.chip.family == "raspberry-pi-4"
    assert m.chip.ram_mb == 4096

    # Linux-side modules present.
    for name in ("i2c", "gpio", "serial", "modbus_tcp", "modbus_rtu", "ble"):
        assert m.module(name) is not None, f"expected {name!r} in modules"

    # Enabled vs disabled — i2c/gpio/serial on, the rest off.
    assert m.module_enabled("i2c") is True
    assert m.module_enabled("gpio") is True
    assert m.module_enabled("serial") is True
    assert m.module_enabled("modbus_tcp") is False
    assert m.module_enabled("modbus_rtu") is False
    assert m.module_enabled("ble") is False

    # ESP-only modules absent — module() returns None, module_enabled
    # returns False (architectural commitment #1: don't load anything
    # that wasn't declared).
    assert m.module("i2s") is None
    assert m.module_enabled("i2s") is False
    assert m.module("esp_now_lr") is None
    assert m.module("deep_sleep") is None

    # Pi pin numbers (BCM numbering) — different from ESP, same shape.
    assert m.pin("door_reed") == 17
    assert m.pin("status_led") == 22
    assert m.pin("relay") == 23


# ----------------------------------------------------------------------
# Test 4: pin lookup happy + sad paths.
# ----------------------------------------------------------------------


def test_pin_lookup() -> None:
    m = parse_manifest(
        """
[chip]
family = "raspberry-pi-4"

[pins]
door_reed = 27
status_led = 22
"""
    )
    assert m.pin("door_reed") == 27
    assert m.pin("status_led") == 22
    # Missing pin: None, not KeyError. Lets the validator render a
    # precise "controller references undeclared pin X" error.
    assert m.pin("not_declared") is None


# ----------------------------------------------------------------------
# Test 5: module_enabled with declared+enabled module returns True.
# ----------------------------------------------------------------------


def test_module_enabled_check() -> None:
    m = parse_manifest(
        """
[chip]
family = "esp32-s3"

[modules]
i2c = { enabled = true, freq_hz = 100000 }
"""
    )
    assert m.module_enabled("i2c") is True
    assert m.module("i2c") == {"enabled": True, "freq_hz": 100000}


# ----------------------------------------------------------------------
# Test 6: module not declared at all -> module_enabled is False.
# ----------------------------------------------------------------------


def test_module_disabled_by_default() -> None:
    m = parse_manifest(
        """
[chip]
family = "esp32"

[modules]
i2c = { enabled = true }
"""
    )
    # `sd` was never mentioned -> reads as disabled, not crash.
    assert m.module_enabled("sd") is False
    assert m.module("sd") is None
    # Explicit enabled = false also reads as disabled.
    m2 = parse_manifest(
        """
[chip]
family = "esp32"

[modules]
sd = { enabled = false }
"""
    )
    assert m2.module_enabled("sd") is False
    # ...but the dict IS returned so config is inspectable.
    assert m2.module("sd") == {"enabled": False}


# ----------------------------------------------------------------------
# Test 7: missing [telemetry] section yields documented defaults.
# ----------------------------------------------------------------------


def test_telemetry_defaults() -> None:
    m = parse_manifest(
        """
[chip]
family = "esp32"
"""
    )
    assert m.telemetry.heartbeat_interval_secs == 60
    assert m.telemetry.metrics_interval_secs == 30
    assert m.telemetry.log_batch_interval_secs == 0
    assert m.telemetry.heartbeat_grace_factor == 1.1
    # Constants must agree with the literal numbers above — guards
    # against an accidental DEFAULT_* rename.
    assert DEFAULT_HEARTBEAT_INTERVAL_SECS == 60
    assert DEFAULT_METRICS_INTERVAL_SECS == 30
    assert DEFAULT_LOG_BATCH_INTERVAL_SECS == 0
    assert DEFAULT_HEARTBEAT_GRACE_FACTOR == 1.1


# ----------------------------------------------------------------------
# Test 8: corrupt TOML raises ManifestParseError with the file path.
# ----------------------------------------------------------------------


def test_invalid_toml_raises(tmp_path: Path) -> None:
    p = tmp_path / "broken.toml"
    p.write_text("[chip]\nfamily = \nbroken = = =")

    with pytest.raises(ManifestParseError) as ei:
        load_manifest(p)
    # Error must name the offending file so operators know what to fix.
    assert str(p) in str(ei.value)
    assert "invalid TOML" in str(ei.value).lower() or "invalid toml" in str(ei.value).lower()


# Bonus: missing [chip] section is also a hard error — required field.
def test_missing_chip_section_raises() -> None:
    with pytest.raises(ManifestParseError, match="\\[chip\\]"):
        parse_manifest("[modules]\ni2c = { enabled = true }\n")
