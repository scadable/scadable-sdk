"""Closed-loop boiler temperature control using PID.

The PID block is declarative — you specify input, output, setpoint,
and gains. The runtime handles the PID computation (3 float ops per
cycle). The controller monitors safety bounds and overrides if needed.
"""
from scadable import Controller, on, SECONDS
from scadable.control import PID
from devices.boiler import Boiler
from devices.temp_probe import TempProbe


class BoilerController(Controller):

    pid = PID(
        input    = TempProbe.outlet_temp,     # what we're measuring
        output   = Boiler.burner_pwm,         # what we're controlling
        setpoint = 72.0,                      # target temperature
        kp = 2.0, ki = 0.5, kd = 0.1,        # PID gains
        output_min = 0, output_max = 100,     # clamp output range
    )

    @on.interval(1, SECONDS)
    def monitor(self):
        """PID runs automatically — this method monitors safety."""
        # Overheat protection
        if Boiler.flue_temp > 400:
            Boiler.burner_pwm = 0
            self.alert("critical", f"Flue temp {Boiler.flue_temp}°C — burner off")

        # Flame failure
        if Boiler.flame_status == 0 and Boiler.burner_pwm > 10:
            Boiler.burner_pwm = 0
            self.alert("critical", "Flame failure detected")

        self.publish("boiler", {
            "water_temp": Boiler.water_temp,
            "flue_temp": Boiler.flue_temp,
            "burner_pwm": Boiler.burner_pwm,
            "outlet_temp": TempProbe.outlet_temp,
            "setpoint": 72.0,
        })

    @on.message("set_temperature")
    def update_setpoint(self, message):
        new_target = message.get("target", 72.0)
        self.pid.setpoint = new_target
        self.alert("info", f"Boiler setpoint changed to {new_target}°C")
