"""Core base classes: Device and Controller.

Device uses a custom metaclass (DeviceMeta) to:
  1. Register itself in the global registry
  2. Intercept class-level attribute access so that
     `LineSensor.temperature` returns the scaled value (float)
     and `LineSensor.setpoint = 75` writes without destroying
     the register descriptor
"""

from __future__ import annotations

from typing import Any

from . import _registry
from . import storage as _storage
from .registers import Characteristic, Field, Pin, Register

# All register-like types that the metaclass should intercept
_REGISTER_TYPES = (Register, Characteristic, Pin, Field)


class DeviceMeta(type):
    """Metaclass for Device that makes class-level register access work.

    Without this, `LineSensor.temperature` returns the Register object
    and `LineSensor.setpoint = 75` replaces the descriptor with an int.

    With this:
      LineSensor.temperature  → returns reg._value * reg.scale (float)
      LineSensor.setpoint = 75 → sets reg._value (preserves descriptor)
      LineSensor.temperature = 50 → raises AttributeError (read-only)
    """

    def __init__(cls, name: str, bases: tuple, namespace: dict, **kwargs: Any) -> None:
        super().__init__(name, bases, namespace, **kwargs)

        # Build a lookup dict: register name → register object
        reg_map: dict[str, Any] = {}
        for reg in getattr(cls, "registers", []):
            reg_name = getattr(reg, "name", None)
            if reg_name:
                reg_map[reg_name] = reg
        cls._register_map = reg_map

        # Register in global registry
        device_id = namespace.get("id", "")
        if device_id:
            _registry.register_device(cls)

    def __getattr__(cls, name: str) -> float:
        """Class-level read: LineSensor.temperature → scaled float value."""
        reg_map = cls.__dict__.get("_register_map", {})
        if name in reg_map:
            reg = reg_map[name]
            return reg._value * reg.scale
        raise AttributeError(f"'{cls.__name__}' has no register '{name}'")

    def __setattr__(cls, name: str, value: Any) -> None:
        """Class-level write: LineSensor.setpoint = 75 → sets reg._value."""
        reg_map = cls.__dict__.get("_register_map", {})
        if name in reg_map:
            reg = reg_map[name]
            if not reg.writable:
                raise AttributeError(
                    f"Register '{name}' on '{cls.__name__}' is read-only "
                    f"(address {getattr(reg, 'address', '?')})"
                )
            # Store the inverse-scaled raw value
            if reg.scale != 0:
                reg._value = value / reg.scale
            else:
                reg._value = value
            return
        # Non-register attributes (id, connection, poll, etc.) go through normally
        type.__setattr__(cls, name, value)


class Device(metaclass=DeviceMeta):
    """Base class for all Scadable device definitions.

    Subclasses define:
      id             — unique device identifier (str)
      name           — human-readable name (str, optional)
      connection     — protocol connection (modbus_tcp, ble, gpio, etc.)
      poll           — polling interval (every(5, SECONDS))
      heartbeat      — health check interval (every(30, SECONDS), optional)
      health_timeout — offline after N missed heartbeats (default 3)
      historian      — cloud historian rate (every(5, MINUTES), optional)
      ota            — OTA update config (ModbusOTA, BLE_DFU, optional)
      capabilities   — list of actions the device supports (optional)
      registers      — list of Register/Characteristic/Pin/Field
    """

    id: str = ""
    name: str = ""
    connection: Any = None
    poll: Any = None
    heartbeat: Any = None
    health_timeout: int = 3
    historian: Any = None
    ota: Any = None
    live: bool = False
    capabilities: list[str] = []
    registers: list = []


class Controller:
    """Base class for all Scadable controller definitions.

    Subclasses define methods decorated with @on.interval, @on.data,
    @on.message, @on.device, @on.startup, @on.shutdown, etc.

    Available methods inside a controller:
      self.publish(topic, data)        — send telemetry via MQTT
      self.send_data/event/alert(name, data) — channel-aware publish verbs
      self.upload(route, blob)         — upload file to cloud storage
      self.alert(severity, msg)        — send notification
      self.actuate(device.field, value) — write to a device register
      self.capture(device)             — trigger a capture action on a device

    Available attributes:
      self.state — per-gateway persistent key-value store. Read with
        self.state.get("k") or self.state.<k>; write with
        self.state.set/.increment/.delete/.clear. The chip executes
        state ops at apply time — see scadable/storage.py for the
        sandbox semantics that apply when running locally.
    """

    # Class-level shared sandbox so `self.state` is available without
    # users calling super().__init__(). The chip side has a per-gateway
    # store; this Python-side StateStore is just the local sandbox the
    # SDK exposes for `scadable verify` + laptop testing. See
    # scadable/storage.py for why the in-process dict is fine here.
    state: _storage.StateStore = _storage.StateStore()

    def __init_subclass__(cls, **kwargs: Any) -> None:
        super().__init_subclass__(**kwargs)
        _registry.register_controller(cls)
        # Each controller subclass gets its own sandbox so unit tests
        # don't bleed state across classes when run in-process.
        cls.state = _storage.StateStore()

    # Quality flag values for self.publish(). Industrial-standard data
    # quality tagging — downstream dashboards can color-code or filter.
    QUALITY_GOOD: str = "good"
    QUALITY_STALE: str = "stale"
    QUALITY_BAD: str = "bad"

    def publish(self, topic: str, data: dict, *, quality: str = "good") -> None:
        """Publish structured data via MQTT → NATS → cloud.

        `quality` rides through the pipeline as a label so downstream
        consumers can filter ("only show good data") or color-code
        (red badge on stale readings). Defaults to "good".
        Accepts: "good" | "stale" | "bad".
        """
        if quality not in ("good", "stale", "bad"):
            raise ValueError(f"publish: quality={quality!r} must be 'good', 'stale', or 'bad'")
        pass  # implemented by gateway runtime

    def upload(
        self, route: str, blob: bytes, *, name: str = "", metadata: dict | None = None
    ) -> None:
        """Upload a file to a configured cloud storage route."""
        pass

    def alert(self, severity: str, message: str) -> None:
        """Send a notification alert (routed by notify() config)."""
        pass

    def actuate(self, target: Any, value: Any = None, **kwargs: Any) -> None:
        """Write a value to a device register or trigger an action."""
        pass

    def capture(self, device: Any) -> bytes:
        """Trigger a capture action (photo, snapshot) on a device."""
        return b""  # implemented by gateway runtime

    def log(self, message: str, *, level: str = "info") -> None:
        """Emit an application log line (NW-F.2).

        On chip-side runtimes (ESP32 v0.3.10+) this routes through the
        gateway's standard log path so the message lands on both the
        Live tail (`Logs` sub-tab) and the offline batch buffer
        (`Logs → History` sub-tab) — the latter only when the operator
        has enabled `[telemetry] log_batch_interval_secs` in
        hardware.toml. The chip stamps the record with this controller
        class name + the emitting method so the dashboard's
        Application/Runtime filter pivots correctly.

        v1 takes a static string + level. f-string interpolation is a
        follow-up — declarative-only constraint stays.

        Levels: ``info`` | ``warn`` | ``error`` | ``debug`` | ``trace``.
        Unknown values surface as INFO on the chip so a typo doesn't
        drop the message.

        On the local Python sandbox this is a no-op — the chip is the
        runtime, not your laptop.
        """
        if not isinstance(message, str):
            raise TypeError(f"self.log message must be a string, got {type(message).__name__}")
        if level not in ("info", "warn", "warning", "error", "err", "debug", "trace"):
            # Sandbox-side validation: nudge the user toward the supported
            # set, even though the chip falls back to INFO on unknown.
            raise ValueError(
                f"self.log: unknown level={level!r}; expected info|warn|error|debug|trace"
            )
        # No-op in the local sandbox.
        return None
