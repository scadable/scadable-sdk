"""BLE environmental sensor.

BLE devices use Characteristic UUIDs instead of register addresses.
The standard BLE GATT UUIDs for environmental sensing are used here.
"""
from scadable import Device, Characteristic, ble, every, SECONDS, MINUTES


class BLEEnvSensor(Device):
    id = "env-office-1"
    name = "Office environment sensor"

    connection = ble(mac="${ENV_SENSOR_MAC}")
    poll = every(30, SECONDS)
    historian = every(5, MINUTES)

    registers = [
        Characteristic("0x2A6E", "temperature", unit="°C", scale=0.01),
        Characteristic("0x2A6F", "humidity",    unit="%",  scale=0.01),
        Characteristic("0x2BD2", "co2",         unit="ppm"),
        Characteristic("0x2BD3", "tvoc",        unit="ppb"),
    ]
