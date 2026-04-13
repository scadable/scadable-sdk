"""Factory camera with RTSP connection and live view.

The `live = True` flag tells the platform to set up WebRTC signaling
so the dashboard can show a live video player. The platform handles
TURN/STUN/signaling — no WebRTC code in the SDK.
"""
from scadable import Device, rtsp


class FactoryCamera(Device):
    id = "cam-line1"
    name = "Line 1 camera"

    connection = rtsp("${CAMERA_URL}")
    live = True  # dashboard shows "Live View" button

    def capture(self):
        """Take a snapshot. Called by controllers."""
        return self.connection.snapshot()
