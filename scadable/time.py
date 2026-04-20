"""Time constants and interval helpers."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class TimeInterval:
    value: int
    unit: str

    @property
    def total_ms(self) -> int:
        multipliers = {"ms": 1, "s": 1000, "min": 60_000, "h": 3_600_000}
        return self.value * multipliers.get(self.unit, 1000)

    def __repr__(self) -> str:
        return f"every({self.value}, {self.unit})"


# Unit constants
SECONDS = "s"
MINUTES = "min"
HOURS = "h"
MILLISECONDS = "ms"


def every(value: int, unit: str = SECONDS) -> TimeInterval:
    """Define a time interval for polling, historian, or controller triggers."""
    return TimeInterval(value=value, unit=unit)
