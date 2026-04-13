"""All controller trigger types demonstrated in one class.

Each method shows a different trigger decorator. A real project
would typically use separate controllers, but this example puts
them together for reference.

Trigger types:
  @on.interval     — run on a fixed timer
  @on.data         — run when a device has new data
  @on.change       — run when a value changes by more than delta
  @on.threshold    — run when a value crosses a limit
  @on.message      — run when an MQTT command arrives from the cloud
  @on.startup      — run once when the gateway boots
  @on.shutdown     — run once when the gateway shuts down
"""
from scadable import Controller, on, system, SECONDS, MINUTES
from devices.line_sensor import LineSensor
from devices.motor_drive import MotorDrive


class MultiTriggerDemo(Controller):

    # ── Time-based ────────────────────────────────
    @on.interval(5, SECONDS)
    def poll_and_publish(self):
        """Runs every 5 seconds regardless of data changes."""
        self.publish("telemetry", {
            "temperature": LineSensor.temperature,
            "motor_rpm": MotorDrive.speed,
        })

    @on.interval(1, MINUTES)
    def periodic_health_check(self):
        """Runs every minute — less frequent background task."""
        self.publish("health", {
            "motor_current": MotorDrive.current,
            "motor_vibration": MotorDrive.vibration,
        })

    # ── Data-driven ───────────────────────────────
    @on.data(LineSensor)
    def on_new_sensor_data(self):
        """Runs every time LineSensor delivers a new reading."""
        self.publish("raw", {"temp": LineSensor.temperature})

    @on.change(LineSensor.temperature, delta=2.0)
    def on_temp_shift(self):
        """Runs only when temperature changes by more than 2°C.
        Avoids noise — small fluctuations are ignored."""
        self.alert("info", f"Temperature shifted to {LineSensor.temperature}°C")

    @on.threshold(LineSensor.temperature, above=95)
    def on_overheat(self):
        """Runs when temperature crosses above 95°C.
        Fires once on crossing, not repeatedly while above."""
        MotorDrive.enable = False
        self.alert("critical", f"Overheat: {LineSensor.temperature}°C — motor stopped")

    # ── Message-driven (cloud commands) ───────────
    @on.message("emergency_stop")
    def handle_emergency(self, message):
        """Runs when the cloud sends an 'emergency_stop' command."""
        MotorDrive.enable = False
        MotorDrive.setpoint = 0
        self.alert("critical", "Emergency stop triggered by operator")

    @on.message("set_speed")
    def handle_set_speed(self, message):
        """Runs when the cloud sends a 'set_speed' command."""
        new_speed = message.get("rpm", 0)
        MotorDrive.setpoint = new_speed
        self.alert("info", f"Speed set to {new_speed} RPM")

    # ── Lifecycle ─────────────────────────────────
    @on.startup
    def boot(self):
        """Runs once when the gateway starts."""
        self.publish("system", {"event": "online", "version": "1.0.0"})

    @on.shutdown
    def cleanup(self):
        """Runs once when the gateway is shutting down."""
        MotorDrive.enable = False
        self.publish("system", {"event": "offline"})
