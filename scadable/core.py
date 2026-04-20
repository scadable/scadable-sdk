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
from .registers import Register, Characteristic, Pin, Field


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
      self.upload(route, blob)         — upload file to cloud storage
      self.alert(severity, msg)        — send notification
      self.actuate(device.field, value) — write to a device register
      self.capture(device)             — trigger a capture action on a device
    """

    def __init_subclass__(cls, **kwargs: Any) -> None:
        super().__init_subclass__(**kwargs)
        _registry.register_controller(cls)

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
            raise ValueError(
                f"publish: quality={quality!r} must be 'good', 'stale', or 'bad'"
            )
        pass  # implemented by gateway runtime

    def upload(self, route: str, blob: bytes, *,
               name: str = "", metadata: dict | None = None) -> None:
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
