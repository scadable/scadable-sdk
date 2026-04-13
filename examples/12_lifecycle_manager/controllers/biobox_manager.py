"""BioBox lifecycle manager.

Demonstrates startup/shutdown hooks and command handling for
devices that power on/off on a schedule. Based on the v3 BioBox
example for Verdant Metrics deployments.
"""
from scadable import Controller, on, system, SECONDS, MINUTES, HOURS
from devices.esp32_sensors import ESP32Sensors


class BioBoxManager(Controller):

    @on.startup
    def boot(self):
        self.publish("system", {"event": "online", "device": "biobox"})
        self.alert("info", "BioBox online, starting data collection")

    @on.shutdown
    def goodbye(self):
        ESP32Sensors.pump_relay = 0  # turn off pump
        self.publish("system", {"event": "offline"})

    @on.interval(1, MINUTES)
    def collect(self):
        temp = ESP32Sensors.soil_temp
        moisture = ESP32Sensors.soil_moisture

        self.publish("soil-data", {
            "temperature": temp,
            "moisture": moisture,
            "light": ESP32Sensors.light_level,
        })

        if temp > 45:
            self.alert("warning", f"High soil temperature: {temp}°C")

        # Auto-watering: pump on if soil is too dry
        if moisture < 30:
            ESP32Sensors.pump_relay = 1
        elif moisture > 60:
            ESP32Sensors.pump_relay = 0

    @on.message("halt")
    def handle_halt(self, message):
        self.alert("info", "Halt command received")
        duration = message.get("duration", 2) if isinstance(message, dict) else 2
        system.shutdown(duration=duration, unit=HOURS)

    @on.message("water")
    def handle_water(self, message):
        duration = message.get("seconds", 30)
        ESP32Sensors.pump_relay = 1
        self.alert("info", f"Manual watering for {duration}s")
