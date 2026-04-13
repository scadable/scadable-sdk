"""Trigger decorators for controller methods.

Usage:
    from scadable import Controller, on, SECONDS

    class MyController(Controller):

        @on.interval(5, SECONDS)
        def poll(self): ...

        @on.data(LineSensor)
        def on_new_data(self): ...

        @on.change(LineSensor.temperature, delta=2.0)
        def on_temp_shift(self): ...

        @on.threshold(LineSensor.temperature, above=95)
        def on_overheat(self): ...

        @on.message("emergency_stop")
        def handle_stop(self, message): ...

        @on.device(LineSensor, DISCONNECTED)
        def sensor_lost(self): ...

        @on.device(LineSensor, CONNECTED)
        def sensor_back(self): ...

        @on.startup
        def boot(self): ...

        @on.shutdown
        def cleanup(self): ...
"""

from __future__ import annotations
from typing import Any, Callable


# Device status constants — used with @on.device(Device, STATUS)
CONNECTED    = 0   # device is responding normally
DISCONNECTED = 1   # device missed heartbeat × health_timeout
TIMEOUT      = 2   # device responded but slower than expected
DEGRADED     = 3   # device returning partial/corrupt data
ERROR        = 4   # device returned an error code
UPDATING     = 5   # device is being OTA-updated (temporarily unavailable)


def _tag(func: Callable, trigger_type: str, **kwargs: Any) -> Callable:
    """Attach trigger metadata to a function."""
    func._scadable_trigger = {"type": trigger_type, **kwargs}  # type: ignore[attr-defined]
    return func


class _OnNamespace:
    """Decorator namespace accessed as `on.interval(...)` etc."""

    @staticmethod
    def interval(value: int, unit: str = "s") -> Callable:
        def decorator(func: Callable) -> Callable:
            return _tag(func, "interval", value=value, unit=unit)
        return decorator

    @staticmethod
    def data(device_or_field: Any) -> Callable:
        def decorator(func: Callable) -> Callable:
            return _tag(func, "data", source=device_or_field)
        return decorator

    @staticmethod
    def change(field: Any, *, delta: float = 0) -> Callable:
        def decorator(func: Callable) -> Callable:
            return _tag(func, "change", field=field, delta=delta)
        return decorator

    @staticmethod
    def threshold(field: Any, *, above: float | None = None,
                  below: float | None = None) -> Callable:
        def decorator(func: Callable) -> Callable:
            return _tag(func, "threshold", field=field, above=above, below=below)
        return decorator

    @staticmethod
    def message(topic: str) -> Callable:
        def decorator(func: Callable) -> Callable:
            return _tag(func, "message", topic=topic)
        return decorator

    @staticmethod
    def device(device_class: Any, status: int) -> Callable:
        """Trigger when a device's connection status changes.

        Usage:
            @on.device(LineSensor, DISCONNECTED)
            def sensor_lost(self): ...
        """
        def decorator(func: Callable) -> Callable:
            return _tag(func, "device", device=device_class, status=status)
        return decorator

    @staticmethod
    def startup(func: Callable) -> Callable:
        return _tag(func, "startup")

    @staticmethod
    def shutdown(func: Callable) -> Callable:
        return _tag(func, "shutdown")


on = _OnNamespace()
