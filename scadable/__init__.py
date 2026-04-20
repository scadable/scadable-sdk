"""Scadable Edge SDK — write device logic in Python, compile to native.

Usage:
    from scadable import Device, Controller, Register, on, every, SECONDS
"""

from .control import PID, State, StateMachine
from .core import Controller, Device
from .models import Model, ONNXModel
from .ota import BLE_DFU, ModbusOTA, SerialBootloader
from .protocols import ble, gpio, i2c, modbus_rtu, modbus_tcp, rtsp, serial
from .registers import Characteristic, Field, Pin, Register
from .routes import notify, upload_route
from .storage import data, files, state
from .system import system
from .time import HOURS, MILLISECONDS, MINUTES, SECONDS, every
from .topics import Topics
from .triggers import CONNECTED, DEGRADED, DISCONNECTED, ERROR, TIMEOUT, UPDATING, on

__version__ = "0.2.0"

__all__ = [
    # Core
    "Device",
    "Controller",
    "Topics",
    # Registers
    "Register",
    "Characteristic",
    "Pin",
    "Field",
    # Protocols
    "modbus_tcp",
    "modbus_rtu",
    "ble",
    "gpio",
    "serial",
    "i2c",
    "rtsp",
    # Time
    "every",
    "SECONDS",
    "MINUTES",
    "HOURS",
    "MILLISECONDS",
    # Triggers
    "on",
    # Device status constants
    "CONNECTED",
    "DISCONNECTED",
    "TIMEOUT",
    "DEGRADED",
    "ERROR",
    "UPDATING",
    # Storage
    "data",
    "files",
    "state",
    # Control
    "PID",
    "StateMachine",
    "State",
    # Models
    "Model",
    "ONNXModel",
    # Routes
    "upload_route",
    "notify",
    # OTA
    "ModbusOTA",
    "BLE_DFU",
    "SerialBootloader",
    # System
    "system",
]
