"""Scadable Edge SDK — write device logic in Python, compile to native.

Usage:
    from scadable import Device, Controller, Register, on, every, SECONDS
"""

from .core import Device, Controller
from .registers import Register, Characteristic, Pin, Field
from .topics import Topics
from .protocols import modbus_tcp, modbus_rtu, ble, gpio, serial, i2c, rtsp
from .time import every, SECONDS, MINUTES, HOURS, MILLISECONDS
from .triggers import on, CONNECTED, DISCONNECTED, TIMEOUT, DEGRADED, ERROR, UPDATING
from .storage import data, files, state
from .control import PID, StateMachine, State
from .models import Model, ONNXModel
from .routes import upload_route, notify
from .ota import ModbusOTA, BLE_DFU, SerialBootloader
from .system import system

__version__ = "0.2.0"

__all__ = [
    # Core
    "Device", "Controller", "Topics",
    # Registers
    "Register", "Characteristic", "Pin", "Field",
    # Protocols
    "modbus_tcp", "modbus_rtu", "ble", "gpio", "serial", "i2c", "rtsp",
    # Time
    "every", "SECONDS", "MINUTES", "HOURS", "MILLISECONDS",
    # Triggers
    "on",
    # Device status constants
    "CONNECTED", "DISCONNECTED", "TIMEOUT", "DEGRADED", "ERROR", "UPDATING",
    # Storage
    "data", "files", "state",
    # Control
    "PID", "StateMachine", "State",
    # Models
    "Model", "ONNXModel",
    # Routes
    "upload_route", "notify",
    # OTA
    "ModbusOTA", "BLE_DFU", "SerialBootloader",
    # System
    "system",
]
