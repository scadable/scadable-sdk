"""ONNX model base class for edge ML inference."""

from __future__ import annotations

from typing import Any


class Model:
    """Reference to an ONNX model file."""

    def __init__(self, path: str):
        self.path = path

    def predict(self, inputs: list[float]) -> list[float]:
        """Run inference. Implemented by gateway runtime."""
        return [0.0]


class ONNXModel:
    """Base class for ONNX model definitions.

    Users MUST implement preprocess() and inference().
    The run() method chains: preprocess → model.predict → inference.

    Attributes:
      id      — unique model identifier for fleet tracking
      name    — human-readable name
      version — semantic version for MLOps
      file    — path to the .onnx file
    """

    id: str = ""
    name: str = ""
    version: str = ""
    file: str = ""
    model: Model | None = None

    def __init__(self) -> None:
        if self.file:
            self.model = Model(self.file)

    def preprocess(self, *args: float) -> list[float]:
        """MUST implement: transform raw values into model input tensor."""
        raise NotImplementedError("ONNXModel subclasses must implement preprocess()")

    def inference(self, prediction: list[float]) -> dict[str, Any]:
        """MUST implement: interpret model output into actionable result."""
        raise NotImplementedError("ONNXModel subclasses must implement inference()")

    def run(self, *args: float) -> dict[str, Any]:
        """Execute the full pipeline: preprocess → predict → inference."""
        inputs = self.preprocess(*args)
        if self.model is None:
            raise RuntimeError(f"Model file not set for {self.__class__.__name__}")
        prediction = self.model.predict(inputs)
        return self.inference(prediction)
