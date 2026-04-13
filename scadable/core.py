"""Core base classes: Device and Controller.

Device uses __init_subclass__ to:
  1. Register itself in the global registry
  2. Create typed descriptors from the registers list so that
     `LineSensor.temperature` works for both IDE autocomplete
     and runtime access
"""

from __future__ import annotations
from typing import Any

from . import _registry
from .registers import Register, Characteristic, Pin, Field


class Device:
    """Base class for all Scadable device definitions.

    Subclasses define:
      id          — unique device identifier (str)
      name        — human-readable name (str, optional)
      connection  — protocol connection (modbus_tcp, ble, gpio, etc.)
      poll        — polling interval (every(5, SECONDS))
      historian   — cloud historian rate (every(5, MINUTES), optional)
      ota         — OTA update config (ModbusOTA, BLE_DFU, optional)
      registers   — list of Register/Characteristic/Pin/Field
    """

    id: str = ""
    name: str = ""
    connection: Any = None
    poll: Any = None
    historian: Any = None
    ota: Any = None
    live: bool = False
    registers: list = []

    def __init_subclass__(cls, **kwargs: Any) -> None:
        super().__init_subclass__(**kwargs)

        # Create typed descriptors from the registers list.
        # After this, `LineSensor.temperature` resolves to the
        # Register descriptor — IDE sees float, runtime sees metadata.
        for reg in cls.registers:
            reg_name = getattr(reg, "name", None)
            if reg_name and not hasattr(cls, reg_name):
                setattr(cls, reg_name, reg)
                reg.__set_name__(cls, reg_name)

        # Register in the global registry for verify/compile
        if cls.id:
            _registry.register_device(cls)


class Controller:
    """Base class for all Scadable controller definitions.

    Subclasses define methods decorated with @on.interval, @on.data,
    @on.message, @on.startup, @on.shutdown, etc. The runtime calls
    these methods based on their trigger conditions.

    Available methods inside a controller:
      self.publish(topic, data)   — send telemetry via MQTT
      self.upload(route, blob)    — upload file to cloud storage
      self.alert(severity, msg)   — send notification
      self.actuate(device.field, value) — write to a device register
    """

    def __init_subclass__(cls, **kwargs: Any) -> None:
        super().__init_subclass__(**kwargs)
        _registry.register_controller(cls)

    def publish(self, topic: str, data: dict) -> None:
        """Publish structured data via MQTT → NATS → cloud."""
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
