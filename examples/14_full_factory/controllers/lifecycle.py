"""Lifecycle manager — startup, shutdown, commands."""
from scadable import Controller, on
from devices.motor_drive import MotorDrive
from devices.line_sensor import LineSensor
from storage import device_config


class Lifecycle(Controller):

    @on.startup
    def boot(self):
        self.publish("system", {"event": "online"})
        MotorDrive.enable = True

    @on.shutdown
    def shutdown(self):
        MotorDrive.enable = False
        LineSensor.flow_rate = 0
        self.publish("system", {"event": "offline"})

    @on.message("calibrate")
    def handle_calibrate(self, message):
        offset = message.get("offset", 0)
        device_config.set("temp_offset", offset)
        self.alert("info", f"Calibration offset: {offset}")

    @on.message("emergency_stop")
    def handle_stop(self, message):
        MotorDrive.enable = False
        LineSensor.flow_rate = 0
        self.alert("critical", "Emergency stop")
