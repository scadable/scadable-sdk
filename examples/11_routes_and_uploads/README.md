# 11 — Cloud routes and blob uploads

Image capture from an RTSP camera → upload to S3 via a configured
upload route.

## What this demonstrates

- `routes.py` — declares cloud upload destinations + notification
  webhooks
- `self.upload(route_name, blob, name=, metadata=)` — pushes to
  a route by name, decoupled from the destination details
- `self.capture(device)` — triggers an out-of-band capture on a
  device (e.g. a video frame from RTSP)
- `@on.threshold` triggering an upload when a sensor crosses

## Hardware required

- An RTSP camera (URL configured via `${CAMERA_URL}`)
- A line sensor (Modbus TCP) used as the trigger

## Compile + deploy

```bash
cd examples/11_routes_and_uploads
SENSOR_HOST=... CAMERA_URL=rtsp://192.168.1.100/stream \
S3_BUCKET=acme-factory-data \
  scadable compile --output dist
```

## Expected behavior

When line-sensor temperature crosses 85°C, the controller triggers
a frame capture from the camera and uploads it to the configured
S3 route. The upload's `metadata` carries the trigger context
(timestamp, sensor reading) so downstream tooling can correlate.

## Try it / extend it

- Add a `notify` route to the operations Slack channel; raise an
  alert with the uploaded image URL.
- Capture every minute regardless of threshold to build a training
  set for an ML inspection model.
