"""OTA update type definitions for connected devices."""

from __future__ import annotations
from dataclasses import dataclass
from typing import Tuple


@dataclass
class ModbusOTA:
    """Modbus register-based OTA firmware update."""
    version: int = 0
    firmware: Tuple[int, int] = (0, 0)
    trigger: int = 0


@dataclass
class BLE_DFU:
    """Standard BLE Device Firmware Update profile."""
    pass


@dataclass
class SerialBootloader:
    """Serial bootloader OTA."""
    baud: int = 115200
    trigger: str = "BREAK"
