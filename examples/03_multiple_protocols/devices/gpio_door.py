"""GPIO door contact sensor.

GPIO devices use pin numbers. They can be polled or event-driven
(trigger on change). This door contact triggers on state change
rather than polling on an interval.
"""
from scadable import Device, Pin, gpio


class GPIODoor(Device):
    id = "door-main-entry"
    name = "Main entry door contact"

    connection = gpio()

    registers = [
        Pin(17, "contact", mode="input_pullup", trigger="change"),
        Pin(18, "alarm_led", mode="output"),
    ]
