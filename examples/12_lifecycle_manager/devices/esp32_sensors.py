"""ESP32 soil sensors for BioBox deployment."""
from scadable import Device, Pin, gpio, every, SECONDS


class ESP32Sensors(Device):
    id = "biobox-sensors"
    name = "BioBox soil sensors"

    connection = gpio()
    poll = every(60, SECONDS)

    registers = [
        Pin(32, "soil_temp",     mode="analog", unit="°C", scale=0.1),
        Pin(33, "soil_moisture", mode="analog", unit="%",  scale=0.1),
        Pin(34, "light_level",   mode="analog", unit="lux"),
        Pin(25, "pump_relay",    mode="output"),
    ]
