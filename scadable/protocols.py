"""Protocol connection helpers.

Each function returns a connection descriptor that holds the
protocol configuration. The Device class stores it as `connection`.
The compiler reads it to generate the right driver code.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any


@dataclass
class ModbusTCPConnection:
    protocol: str = "modbus-tcp"
    host: str = ""
    port: int = 502
    slave: int = 1


@dataclass
class ModbusRTUConnection:
    protocol: str = "modbus-rtu"
    port: str = ""
    baudrate: int = 9600
    slave: int = 1
    parity: str = "N"
    stopbits: int = 1


@dataclass
class BLEConnection:
    protocol: str = "ble"
    mac: str = ""


@dataclass
class GPIOConnection:
    protocol: str = "gpio"


@dataclass
class SerialConnection:
    protocol: str = "serial"
    port: str = ""
    baudrate: int = 9600
    parity: str = "N"
    stopbits: int = 1


@dataclass
class I2CConnection:
    protocol: str = "i2c"
    bus: int = 1
    address: int = 0


@dataclass
class RTSPConnection:
    protocol: str = "rtsp"
    url: str = ""

    def snapshot(self) -> bytes:
        """Take a snapshot. Implemented by gateway runtime."""
        return b""


def modbus_tcp(host: str = "", port: int = 502, slave: int = 1) -> ModbusTCPConnection:
    return ModbusTCPConnection(host=host, port=port, slave=slave)


def modbus_rtu(port: str = "", baudrate: int = 9600, slave: int = 1,
               parity: str = "N", stopbits: int = 1) -> ModbusRTUConnection:
    return ModbusRTUConnection(port=port, baudrate=baudrate, slave=slave,
                               parity=parity, stopbits=stopbits)


def ble(mac: str = "") -> BLEConnection:
    return BLEConnection(mac=mac)


def gpio() -> GPIOConnection:
    return GPIOConnection()


def serial(port: str = "", baudrate: int = 9600,
           parity: str = "N", stopbits: int = 1) -> SerialConnection:
    return SerialConnection(port=port, baudrate=baudrate,
                            parity=parity, stopbits=stopbits)


def i2c(bus: int = 1, address: int = 0) -> I2CConnection:
    return I2CConnection(bus=bus, address=address)


def rtsp(url: str = "") -> RTSPConnection:
    return RTSPConnection(url=url)
