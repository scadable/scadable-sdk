"""Safety manager with state machine."""
from scadable import Controller, on, SECONDS
from scadable.control import StateMachine, State
from devices.line_sensor import LineSensor
from devices.motor_drive import MotorDrive


class SafetyManager(Controller):

    machine = StateMachine(initial="running")
    machine.add_states([
        State("running"),
        State("warning",  on_enter=lambda: None),
        State("shutdown", on_enter=lambda: (
            setattr(MotorDrive, "enable", False),
            setattr(LineSensor, "flow_rate", 0),
        )),
        State("lockout"),
    ])
    machine.add_transitions([
        {"from": "running",  "to": "warning",  "when": "LineSensor.temperature > 85"},
        {"from": "warning",  "to": "shutdown", "when": "LineSensor.temperature > 95"},
        {"from": "warning",  "to": "running",  "when": "LineSensor.temperature < 80"},
        {"from": "shutdown", "to": "lockout",  "when": "elapsed > 300"},
        {"from": "lockout",  "to": "running",  "when": "command:reset"},
    ])

    @on.interval(1, SECONDS)
    def check(self):
        self.publish("safety", {
            "state": self.machine.current,
            "temperature": LineSensor.temperature,
        })

    @on.message("reset")
    def handle_reset(self, message):
        self.machine.transition("running")
        self.alert("info", "Safety lockout cleared")
