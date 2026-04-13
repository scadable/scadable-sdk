"""Motor speed controller with PID."""
from scadable import Controller, on, SECONDS
from scadable.control import PID
from devices.line_sensor import LineSensor
from devices.motor_drive import MotorDrive


class MotorController(Controller):

    pid = PID(
        input=LineSensor.flow_rate,
        output=MotorDrive.setpoint,
        setpoint=50.0,
        kp=2.0, ki=0.5, kd=0.1,
        output_min=0, output_max=3600,
    )

    @on.interval(1, SECONDS)
    def monitor(self):
        if MotorDrive.current > 15:
            MotorDrive.enable = False
            self.alert("critical", f"Overcurrent: {MotorDrive.current}A")
