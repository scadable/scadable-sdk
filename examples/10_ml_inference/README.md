# 10 — On-gateway ML inference

ONNX model running locally on the gateway against live sensor
data, with predictions feeding controller logic.

## What this demonstrates

- `ONNXModel("models/predictive_maintenance.onnx")` — wraps a model
  file from the project's `models/` directory
- Subclassing to add `preprocess()` for feature engineering
- Calling `model.inference(features)` from a controller
- Action on prediction: alert + actuate

## Hardware required

A motor drive (Modbus TCP) exposing vibration, current, and
temperature registers. The gateway needs ~50 MB free for the model
and ONNX runtime.

## Compile + deploy

```bash
cd examples/10_ml_inference
MOTOR_HOST=192.168.1.51 scadable compile --output dist
# Bundle includes models/ — copy bundle and extract on the gateway
scp dist/bundle.tar.gz gw:/var/lib/scadable/bundle.tar.gz
ssh gw "tar -xzf /var/lib/scadable/bundle.tar.gz -C /etc/scadable/"
```

## Expected behavior

Every minute the controller pulls the latest sensor window, runs
inference, and publishes the predicted remaining-useful-life. If
the prediction crosses below a threshold it raises a maintenance
alert.

## Try it / extend it

- Add a second model for anomaly detection running at higher
  frequency, with both models writing to the same dashboard.
- Train a new model with fresh data; bump the version in the
  `ONNXModel` declaration; redeploy — the runtime swaps models on
  reload without downtime.
