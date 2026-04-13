"""Predictive maintenance controller using ML inference.

Imports the model, calls model.run() with sensor values,
acts on the result. The model is a reusable class — it can
be imported by multiple controllers across the project.
"""
from scadable import Controller, on, SECONDS
from devices.motor_drive import MotorDrive
from models.motor_anomaly import MotorAnomaly

anomaly = MotorAnomaly()


class PredictiveMaintenance(Controller):

    @on.interval(30, SECONDS)
    def check_motor(self):
        result = anomaly.run(
            MotorDrive.bearing_temp,
            MotorDrive.vibration,
            MotorDrive.current,
            MotorDrive.speed,
        )

        if result["needs_maintenance"]:
            self.alert("warning",
                       f"Motor {result['label']}: score={result['score']:.2f}")

        self.publish("motor-health", result)

    @on.threshold(MotorDrive.current, above=15)
    def overcurrent_protection(self):
        MotorDrive.enable = False
        self.alert("critical", f"Overcurrent: {MotorDrive.current}A — motor disabled")
