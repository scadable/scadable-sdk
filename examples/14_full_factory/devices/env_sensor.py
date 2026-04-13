"""BLE environment sensor for multi-device example."""
from scadable import Device, Characteristic, ble, every, SECONDS

class EnvSensor(Device):
    id = "env-1"
    connection = ble(mac="${ENV_MAC}")
    poll = every(30, SECONDS)
    registers = [
        Characteristic("0x2A6E", "temperature", unit="°C", scale=0.01),
        Characteristic("0x2A6F", "humidity",    unit="%",  scale=0.01),
        Characteristic("0x2BD2", "co2",         unit="ppm"),
    ]
