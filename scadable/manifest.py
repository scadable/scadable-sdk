"""Hardware manifest loader (W1 — SDK side).

The same `hardware.toml` schema is parsed by the gateway-esp firmware
(`gateway-esp/esp-gateway/src/hardware/mod.rs`) and the gateway-linux
runtime (`gateway-linux/src/hardware/mod.rs`). This module is the
Python mirror so the SDK can do compile-time validation (W2) and
emitter inspection (W8) without re-implementing the schema in three
places.

The loader is deliberately permissive: every section except `[chip]`
is optional and defaults to an empty/disabled state, so legacy
manifests that only declare `[chip]` keep loading cleanly. Validation
of *what* must be declared for a given controller is the validator's
job (W2), not this loader's.

Schema (per `partitioned-enchanting-lighthouse.md` plan, W1 section):

    [chip]
    family = "esp32-s3"          # or rpi3 | rpi4 | rpi5 | x86_64 | ...
    flash_size_mb = 4
    psram_size_mb = 8

    [pins]                       # logical name -> GPIO number
    door_reed = 27
    status_led = 2

    [modules]                    # runtime activation gates
    i2c        = { enabled = true, freq_hz = 400000 }
    sd         = { enabled = true, bus = "spi", cs_pin = "sd_cs" }
    deep_sleep = { enabled = true, default_timeout_secs = 1800 }

    [memory]
    reserved_heap_kb = 80

    [telemetry]
    heartbeat_interval_secs = 86400
    heartbeat_grace_factor  = 1.1
    log_batch_interval_secs = 86400
    log_batch_max_records   = 5000
    metrics_interval_secs   = 3600

The `[modules]` section is open-ended on purpose — ESP and Linux
gateways have different module sets (ESP: i2c/i2s/sd/esp_now_lr/
deep_sleep; Linux: i2c/gpio/serial/modbus_tcp/modbus_rtu/ble) and the
SDK validator decides which combinations are legal per target. We
just preserve the raw module config dicts here.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

# tomllib is stdlib in 3.11+; fall back to the third-party `toml`
# package (already a hard dep via pyproject.toml) on 3.10 so the SDK
# stays installable on the documented minimum.
try:
    import tomllib as _toml_loader

    def _parse_toml(text: str) -> dict[str, Any]:
        return _toml_loader.loads(text)

    _ParseError: type[Exception] = _toml_loader.TOMLDecodeError
except ImportError:  # pragma: no cover - exercised only on 3.10
    import toml as _toml_loader  # type: ignore[no-redef]

    def _parse_toml(text: str) -> dict[str, Any]:
        return _toml_loader.loads(text)

    _ParseError = _toml_loader.TomlDecodeError  # type: ignore[attr-defined]


# Telemetry defaults match the firmware's existing behavior pre-W5
# (30s metrics, 60s heartbeat, immediate log flush). Keeping these in
# sync with `gateway-esp/esp-gateway/src/modules/telemetry.rs` and
# `gateway-linux/src/hardware/mod.rs` is critical — if a manifest
# omits `[telemetry]`, all three layers must agree on what "missing"
# means or operators see different behavior on each platform.
DEFAULT_HEARTBEAT_INTERVAL_SECS = 60
DEFAULT_HEARTBEAT_GRACE_FACTOR = 1.1
DEFAULT_LOG_BATCH_INTERVAL_SECS = 0  # 0 = flush immediately, no batching
DEFAULT_LOG_BATCH_MAX_RECORDS = 5000
DEFAULT_METRICS_INTERVAL_SECS = 30


class ManifestParseError(ValueError):
    """Raised when a hardware.toml file is malformed or unreadable.

    Carries the offending file path + the underlying parser message so
    operators can fix the typo without grepping through stack traces.
    """

    def __init__(self, path: str | Path, message: str) -> None:
        self.path = str(path)
        self.message = message
        super().__init__(f"hardware.toml at {self.path}: {message}")


@dataclass(frozen=True)
class ChipInfo:
    """The `[chip]` section. The only mandatory section in the file."""

    family: str
    revision: str | None = None
    flash_size_mb: int | None = None
    psram_size_mb: int | None = None
    ram_mb: int | None = None  # Linux uses ram_mb (no flash/psram concept)


@dataclass(frozen=True)
class PeripheralsInfo:
    """The `[peripherals]` section — what the chip *can* do at the SoC
    level. Distinct from `[modules]`, which is what we *will* activate."""

    wifi: bool = False
    ble: bool = False
    ethernet: bool = False
    usb_native: bool = False
    digital_signature_peripheral: bool = False
    crypto_accel: bool = False


@dataclass(frozen=True)
class FirmwareInfo:
    """The `[firmware]` section — variant + SDK provenance."""

    variant: str | None = None
    sdk_version: str | None = None
    git_sha: str | None = None
    build_ts: str | None = None


@dataclass(frozen=True)
class MemoryInfo:
    """The `[memory]` section — operator override for budget checks."""

    reserved_heap_kb: int = 0


@dataclass(frozen=True)
class TelemetryInfo:
    """The `[telemetry]` section — heartbeat / log batching cadence."""

    heartbeat_interval_secs: int = DEFAULT_HEARTBEAT_INTERVAL_SECS
    heartbeat_grace_factor: float = DEFAULT_HEARTBEAT_GRACE_FACTOR
    log_batch_interval_secs: int = DEFAULT_LOG_BATCH_INTERVAL_SECS
    log_batch_max_records: int = DEFAULT_LOG_BATCH_MAX_RECORDS
    metrics_interval_secs: int = DEFAULT_METRICS_INTERVAL_SECS


@dataclass(frozen=True)
class HardwareManifest:
    """In-memory representation of a parsed hardware.toml file.

    All accessors return `None` / empty containers when the underlying
    section is absent — callers MUST handle missing data rather than
    assuming a key exists. The validator (W2) is responsible for
    rejecting controllers whose declared dependencies aren't met.
    """

    chip: ChipInfo
    peripherals: PeripheralsInfo = field(default_factory=PeripheralsInfo)
    firmware: FirmwareInfo = field(default_factory=FirmwareInfo)
    pins: dict[str, int] = field(default_factory=dict)
    modules: dict[str, dict[str, Any]] = field(default_factory=dict)
    memory: MemoryInfo = field(default_factory=MemoryInfo)
    telemetry: TelemetryInfo = field(default_factory=TelemetryInfo)
    source_path: Path | None = None

    # ------------------------------------------------------------------
    # Convenience accessors used by validator + emitters.
    # ------------------------------------------------------------------

    def pin(self, name: str) -> int | None:
        """Resolve a logical pin name (e.g. "door_reed") to its GPIO
        number. Returns None when the pin isn't declared so callers
        can produce a precise error message rather than KeyError-ing."""
        return self.pins.get(name)

    def module(self, name: str) -> dict[str, Any] | None:
        """Return the raw `[modules.<name>]` config dict, or None when
        the module isn't declared at all. Note: a *declared but
        disabled* module returns its dict (with `enabled=False`); use
        `module_enabled()` if you only care about activation state."""
        return self.modules.get(name)

    def module_enabled(self, name: str) -> bool:
        """True iff the module is both declared AND `enabled=true`.

        Treats a missing `[modules.<name>]` section as disabled rather
        than raising — matches the firmware's "only load what's
        declared" rule (architectural commitment #1)."""
        cfg = self.modules.get(name)
        if cfg is None:
            return False
        return bool(cfg.get("enabled", False))


# ----------------------------------------------------------------------
# Loader
# ----------------------------------------------------------------------


def load_manifest(path: str | Path) -> HardwareManifest:
    """Parse a `hardware.toml` file from disk.

    Raises `ManifestParseError` on:
      - file not found / not readable
      - malformed TOML
      - missing required `[chip]` section
      - `[chip].family` missing or non-string

    Every other section is optional + defaulted.
    """
    p = Path(path)
    try:
        text = p.read_text(encoding="utf-8")
    except FileNotFoundError as e:
        raise ManifestParseError(p, f"file not found: {e}") from e
    except OSError as e:
        raise ManifestParseError(p, f"could not read file: {e}") from e

    try:
        data = _parse_toml(text)
    except _ParseError as e:
        raise ManifestParseError(p, f"invalid TOML: {e}") from e

    return _from_dict(data, source_path=p)


def parse_manifest(text: str) -> HardwareManifest:
    """Parse `hardware.toml` content from an in-memory string. Used by
    tests and any in-process tooling that doesn't want to round-trip
    through the filesystem."""
    try:
        data = _parse_toml(text)
    except _ParseError as e:
        raise ManifestParseError("<string>", f"invalid TOML: {e}") from e
    return _from_dict(data, source_path=None)


def _from_dict(data: dict[str, Any], source_path: Path | None) -> HardwareManifest:
    if not isinstance(data, dict):
        raise ManifestParseError(
            source_path or "<string>", "expected a TOML table at the document root"
        )

    chip = _parse_chip(data.get("chip"), source_path)
    peripherals = _parse_peripherals(data.get("peripherals"))
    firmware = _parse_firmware(data.get("firmware"))
    pins = _parse_pins(data.get("pins"), source_path)
    modules = _parse_modules(data.get("modules"), source_path)
    memory = _parse_memory(data.get("memory"))
    telemetry = _parse_telemetry(data.get("telemetry"))

    return HardwareManifest(
        chip=chip,
        peripherals=peripherals,
        firmware=firmware,
        pins=pins,
        modules=modules,
        memory=memory,
        telemetry=telemetry,
        source_path=source_path,
    )


def _parse_chip(raw: Any, source_path: Path | None) -> ChipInfo:
    if raw is None:
        raise ManifestParseError(
            source_path or "<string>", "missing required [chip] section"
        )
    if not isinstance(raw, dict):
        raise ManifestParseError(source_path or "<string>", "[chip] must be a table")
    family = raw.get("family")
    if not isinstance(family, str) or not family:
        raise ManifestParseError(
            source_path or "<string>", "[chip].family must be a non-empty string"
        )
    return ChipInfo(
        family=family,
        revision=_opt_str(raw.get("revision")),
        flash_size_mb=_opt_int(raw.get("flash_size_mb")),
        psram_size_mb=_opt_int(raw.get("psram_size_mb")),
        ram_mb=_opt_int(raw.get("ram_mb")),
    )


def _parse_peripherals(raw: Any) -> PeripheralsInfo:
    if raw is None:
        return PeripheralsInfo()
    if not isinstance(raw, dict):
        return PeripheralsInfo()
    return PeripheralsInfo(
        wifi=bool(raw.get("wifi", False)),
        ble=bool(raw.get("ble", False)),
        ethernet=bool(raw.get("ethernet", False)),
        usb_native=bool(raw.get("usb_native", False)),
        digital_signature_peripheral=bool(raw.get("digital_signature_peripheral", False)),
        crypto_accel=bool(raw.get("crypto_accel", False)),
    )


def _parse_firmware(raw: Any) -> FirmwareInfo:
    if not isinstance(raw, dict):
        return FirmwareInfo()
    return FirmwareInfo(
        variant=_opt_str(raw.get("variant")),
        sdk_version=_opt_str(raw.get("sdk_version")),
        git_sha=_opt_str(raw.get("git_sha")),
        build_ts=_opt_str(raw.get("build_ts")),
    )


def _parse_pins(raw: Any, source_path: Path | None) -> dict[str, int]:
    if raw is None:
        return {}
    if not isinstance(raw, dict):
        raise ManifestParseError(source_path or "<string>", "[pins] must be a table")
    out: dict[str, int] = {}
    for name, value in raw.items():
        if not isinstance(value, int) or isinstance(value, bool):
            # bool is an int subclass in Python — explicitly reject so
            # `door_reed = true` doesn't silently end up as pin 1.
            raise ManifestParseError(
                source_path or "<string>",
                f"[pins].{name} must be an integer GPIO number, got {value!r}",
            )
        out[name] = value
    return out


def _parse_modules(raw: Any, source_path: Path | None) -> dict[str, dict[str, Any]]:
    if raw is None:
        return {}
    if not isinstance(raw, dict):
        raise ManifestParseError(source_path or "<string>", "[modules] must be a table")
    out: dict[str, dict[str, Any]] = {}
    for name, value in raw.items():
        if not isinstance(value, dict):
            raise ManifestParseError(
                source_path or "<string>",
                f"[modules.{name}] must be a table (e.g. `{{ enabled = true }}`)",
            )
        # Normalize: every module dict has at least an `enabled` key.
        normalized = dict(value)
        normalized.setdefault("enabled", False)
        out[name] = normalized
    return out


def _parse_memory(raw: Any) -> MemoryInfo:
    if not isinstance(raw, dict):
        return MemoryInfo()
    reserved = raw.get("reserved_heap_kb", 0)
    if not isinstance(reserved, int) or isinstance(reserved, bool) or reserved < 0:
        # Defensive: a malformed memory section shouldn't crash the
        # whole loader; fall back to the safe default.
        reserved = 0
    return MemoryInfo(reserved_heap_kb=reserved)


def _parse_telemetry(raw: Any) -> TelemetryInfo:
    if not isinstance(raw, dict):
        return TelemetryInfo()
    return TelemetryInfo(
        heartbeat_interval_secs=_int_or_default(
            raw.get("heartbeat_interval_secs"), DEFAULT_HEARTBEAT_INTERVAL_SECS
        ),
        heartbeat_grace_factor=_float_or_default(
            raw.get("heartbeat_grace_factor"), DEFAULT_HEARTBEAT_GRACE_FACTOR
        ),
        log_batch_interval_secs=_int_or_default(
            raw.get("log_batch_interval_secs"), DEFAULT_LOG_BATCH_INTERVAL_SECS
        ),
        log_batch_max_records=_int_or_default(
            raw.get("log_batch_max_records"), DEFAULT_LOG_BATCH_MAX_RECORDS
        ),
        metrics_interval_secs=_int_or_default(
            raw.get("metrics_interval_secs"), DEFAULT_METRICS_INTERVAL_SECS
        ),
    )


# ----------------------------------------------------------------------
# Tiny coercion helpers — keep loader bodies above readable.
# ----------------------------------------------------------------------


def _opt_str(v: Any) -> str | None:
    return v if isinstance(v, str) and v else None


def _opt_int(v: Any) -> int | None:
    if isinstance(v, bool):
        return None
    return v if isinstance(v, int) else None


def _int_or_default(v: Any, default: int) -> int:
    if isinstance(v, bool):
        return default
    return v if isinstance(v, int) else default


def _float_or_default(v: Any, default: float) -> float:
    if isinstance(v, bool):
        return default
    if isinstance(v, (int, float)):
        return float(v)
    return default


__all__ = [
    "ChipInfo",
    "FirmwareInfo",
    "HardwareManifest",
    "ManifestParseError",
    "MemoryInfo",
    "PeripheralsInfo",
    "TelemetryInfo",
    "DEFAULT_HEARTBEAT_INTERVAL_SECS",
    "DEFAULT_HEARTBEAT_GRACE_FACTOR",
    "DEFAULT_LOG_BATCH_INTERVAL_SECS",
    "DEFAULT_LOG_BATCH_MAX_RECORDS",
    "DEFAULT_METRICS_INTERVAL_SECS",
    "load_manifest",
    "parse_manifest",
]
