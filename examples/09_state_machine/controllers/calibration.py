"""State machine for pH sensor calibration routine.

States: measuring → zero_point → span_point → measuring
Triggered by a cloud command. Each state writes to the sensor's
calibration registers and auto-advances after a timeout.
"""
from scadable import Controller, on, SECONDS
from scadable.control import StateMachine, State
from devices.ph_sensor import PHSensor


class CalibrationController(Controller):

    machine = StateMachine(initial="measuring")

    machine.add_states([
        State("measuring",
              on_enter=lambda: setattr(PHSensor, "cal_mode", 0)),

        State("zero_point",
              on_enter=lambda: (
                  setattr(PHSensor, "cal_mode", 1),
                  setattr(PHSensor, "cal_point", 7),
              ),
              timeout=30,
              next="span_point"),

        State("span_point",
              on_enter=lambda: (
                  setattr(PHSensor, "cal_mode", 2),
                  setattr(PHSensor, "cal_point", 4),
              ),
              timeout=30,
              next="measuring"),
    ])

    @on.message("calibrate")
    def start_calibration(self, message):
        """Trigger calibration from the cloud."""
        self.machine.transition("zero_point")
        self.alert("info", "pH calibration started")

    @on.interval(2, SECONDS)
    def monitor(self):
        self.publish("ph-status", {
            "ph": PHSensor.ph_value,
            "raw_mv": PHSensor.ph_raw,
            "cal_state": self.machine.current,
        })
