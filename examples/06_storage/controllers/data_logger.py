"""Data logger — demonstrates local storage read/write/query.

Uses all three storage types:
  sensor_data   — write time-series, query averages and trends
  camera_roll   — not used here (see example 11)
  device_config — read/write persistent state (calibration offsets)
"""
from scadable import Controller, on, SECONDS
from devices.line_sensor import LineSensor
from storage import sensor_data, device_config


class DataLogger(Controller):

    @on.interval(5, SECONDS)
    def log_and_analyze(self):
        # Read calibration offset from persistent state
        offset = device_config.get("temp_offset", default=0)
        temp = LineSensor.temperature + offset

        # Write to local time-series storage
        sensor_data.write("temperature", temp)
        sensor_data.write("pressure", LineSensor.pressure)

        # Query local history (no cloud round-trip)
        avg_1h = sensor_data.avg("temperature", window="1h")
        max_today = sensor_data.max("temperature", window="24h")
        last_10 = sensor_data.read("temperature", last=10)
        trend = sensor_data.trend("temperature", window="30m")

        # Publish enriched data to cloud
        self.publish("sensor-data", {
            "temperature": temp,
            "pressure": LineSensor.pressure,
            "avg_1h": avg_1h,
            "max_today": max_today,
            "trend": trend,
        })

        # Sustained high temp detection using local history
        if avg_1h > 80 and max_today < 90:
            self.alert("warning", "Sustained high temperature — check cooling")

    @on.message("calibrate")
    def handle_calibrate(self, message):
        """Set calibration offset from cloud command."""
        offset = message.get("offset", 0)
        device_config.set("temp_offset", offset)
        self.alert("info", f"Calibration offset set to {offset}")

    @on.message("reset_state")
    def handle_reset(self, message):
        """Clear all persistent state."""
        device_config.clear()
        self.alert("info", "Device state cleared")
