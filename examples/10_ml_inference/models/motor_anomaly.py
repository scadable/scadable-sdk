"""Motor anomaly detection model.

An ONNXModel subclass with a unique ID for fleet-wide tracking.
Users MUST implement preprocess() and inference().
The runtime calls: preprocess → model.predict → inference.

The id + version fields enable future MLOps:
  - Track which model version runs on which gateway
  - A/B test across fleet splits
  - Detect model drift
  - Roll back to a previous version
"""
from scadable import ONNXModel


class MotorAnomaly(ONNXModel):
    id = "motor-anomaly"
    name = "Motor predictive maintenance"
    version = "1.2.0"
    file = "models/motor_anomaly_v1.2.onnx"

    def preprocess(self, bearing_temp, vibration, current, speed):
        """Transform raw sensor values into model input tensor.

        Normalize speed to 0-1 range (max 3600 RPM).
        All other values passed as-is.
        """
        return [bearing_temp, vibration, current, speed / 3600]

    def inference(self, prediction):
        """Interpret model output tensor into actionable result.

        prediction[0] is the anomaly score (0-1).
        Returns a dict that controllers can use directly.
        """
        score = prediction[0]
        return {
            "score": score,
            "label": "healthy" if score < 0.5 else "degraded" if score < 0.85 else "failing",
            "needs_maintenance": score > 0.85,
        }
