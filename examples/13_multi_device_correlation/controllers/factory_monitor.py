"""Cross-device factory monitor with ML and local storage.

Reads from 3 devices across 2 protocols (Modbus + BLE), uses local
storage for aggregation, runs ML inference, loops over threshold
checks, and publishes combined results.
"""
from scadable import Controller, on, SECONDS
from devices.line_sensor import LineSensor
from devices.motor_drive import MotorDrive
from devices.env_sensor import EnvSensor
from models.air_quality import AirQualityClassifier
from storage import sensor_data, device_config

air_model = AirQualityClassifier()


class FactoryMonitor(Controller):

    @on.interval(5, SECONDS)
    def correlate(self):
        # Read calibration offset from persistent state
        offset = device_config.get("temp_offset", 0)
        temp = LineSensor.temperature + offset

        # Store locally for trend analysis
        sensor_data.write("temperature", temp)
        sensor_data.write("motor_current", MotorDrive.current)

        # Local aggregation — no cloud round-trip
        avg_temp = sensor_data.avg("temperature", window="1h")
        trend = sensor_data.trend("temperature", window="30m")

        # Cross-device efficiency calculation
        efficiency = 0
        if MotorDrive.speed > 0:
            efficiency = LineSensor.flow_rate / MotorDrive.speed * 100

        # Loop over multi-sensor threshold checks
        checks = [
            ("line_temp",   temp,                    95),
            ("motor_temp",  MotorDrive.bearing_temp,  85),
            ("motor_vib",   MotorDrive.vibration,     10),
            ("room_co2",    EnvSensor.co2,           1000),
        ]
        for name, value, limit in checks:
            if value > limit:
                self.alert("warning", f"{name} high: {value} (limit {limit})")

        # Publish combined view
        self.publish("factory-status", {
            "temperature": temp,
            "avg_temp_1h": avg_temp,
            "temp_trend": trend,
            "pressure": LineSensor.pressure,
            "motor_rpm": MotorDrive.speed,
            "motor_current": MotorDrive.current,
            "efficiency": round(efficiency, 2),
            "room_co2": EnvSensor.co2,
            "humidity": EnvSensor.humidity,
        })

    @on.interval(60, SECONDS)
    def check_air_quality(self):
        result = air_model.run(
            EnvSensor.temperature,
            EnvSensor.humidity,
            EnvSensor.co2,
        )
        if result["quality"] in ("poor", "hazardous"):
            self.alert("warning", f"Air quality: {result['quality']}")
        self.publish("air-quality", result)
