"""Basic temperature monitor — simplest controller.

Reads a sensor on an interval, publishes data, alerts on threshold.
Demonstrates direct device access: import the device class and
reference its fields directly (e.g. LineSensor.temperature).
"""
from scadable import Controller, on, SECONDS
from devices.line_sensor import LineSensor


class TempMonitor(Controller):

    @on.interval(5, SECONDS)
    def check_temperature(self):
        temp = LineSensor.temperature
        pressure = LineSensor.pressure

        self.publish("sensor-data", {
            "temperature": temp,
            "pressure": pressure,
        })

        if temp > 85:
            self.alert("warning", f"High temperature: {temp}°C")

        if temp > 95:
            LineSensor.flow_rate = 0  # emergency: cut flow
            self.alert("critical", f"CRITICAL temperature: {temp}°C")
