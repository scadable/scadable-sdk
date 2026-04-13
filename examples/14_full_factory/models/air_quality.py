"""Air quality classifier model."""
from scadable import ONNXModel

class AirQualityClassifier(ONNXModel):
    id = "air-quality"
    name = "Indoor air quality"
    version = "2.0.1"
    file = "models/air_quality_v2.onnx"

    def preprocess(self, temperature, humidity, co2):
        return [temperature, humidity / 100, co2 / 5000]

    def inference(self, prediction):
        classes = ["good", "moderate", "poor", "hazardous"]
        idx = max(range(len(prediction)), key=lambda i: prediction[i])
        return {
            "quality": classes[idx],
            "confidence": prediction[idx],
            "index": idx,
        }
