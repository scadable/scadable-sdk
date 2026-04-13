"""Production monitor — reads all sensors, stores, publishes."""
from scadable import Controller, on, SECONDS
from devices.line_sensor import LineSensor
from devices.motor_drive import MotorDrive
from devices.env_sensor import EnvSensor
from storage import sensor_data, device_config


class ProductionMonitor(Controller):

    @on.interval(5, SECONDS)
    def collect(self):
        offset = device_config.get("temp_offset", 0)
        temp = LineSensor.temperature + offset

        sensor_data.write("temperature", temp)

        efficiency = 0
        if MotorDrive.speed > 0:
            efficiency = LineSensor.flow_rate / MotorDrive.speed * 100

        self.publish("production", {
            "temperature": temp,
            "pressure": LineSensor.pressure,
            "motor_rpm": MotorDrive.speed,
            "efficiency": round(efficiency, 2),
            "co2": EnvSensor.co2,
        })
