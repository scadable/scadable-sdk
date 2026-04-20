"""Global registry that tracks all Device and Controller subclasses.

When a user defines `class LineSensor(Device)`, the Device metaclass
calls `register_device(LineSensor)`. The registry is used by:
  - scadable verify (walk all defined classes, validate constraints)
  - scadable compile (emit code for every registered class)
  - IDE tooling (introspect available devices for autocomplete)
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    pass

_devices: dict[str, type] = {}
_controllers: dict[str, type] = {}


def register_device(cls: type) -> None:
    """Called by Device.__init_subclass__ for every Device subclass."""
    device_id = getattr(cls, "id", None)
    if device_id:
        _devices[device_id] = cls


def register_controller(cls: type) -> None:
    """Called by Controller.__init_subclass__ for every Controller subclass."""
    name = cls.__name__
    _controllers[name] = cls


def get_devices() -> dict[str, type]:
    return dict(_devices)


def get_controllers() -> dict[str, type]:
    return dict(_controllers)


def clear() -> None:
    """Reset registry — used in tests."""
    _devices.clear()
    _controllers.clear()
