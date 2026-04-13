"""Photo monitor — captures and uploads on high temperature.

Demonstrates:
  self.publish()  — send structured data via MQTT (always available)
  self.upload()   — upload a file to a configured route (S3/Spaces)
  self.alert()    — send notification to configured targets (Slack/email)
"""
from scadable import Controller, on, SECONDS
from devices.line_sensor import LineSensor
from devices.factory_camera import FactoryCamera


class PhotoMonitor(Controller):

    @on.threshold(LineSensor.temperature, above=75)
    def on_high_temp(self):
        temp = LineSensor.temperature

        # Take photo
        photo = FactoryCamera.capture()

        # Upload to S3 (routed by "high-temp-photos" in routes.py)
        self.upload("high-temp-photos", photo,
                    name=f"alert_{temp:.0f}C.jpg",
                    metadata={"temperature": temp})

        # Alert goes to Slack + email (routed by notify config)
        self.alert("warning", f"High temperature {temp}°C — photo captured")

        # Telemetry still flows via MQTT
        self.publish("events", {
            "type": "high_temp_photo",
            "temperature": temp,
        })
