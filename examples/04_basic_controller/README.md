# 04 — Basic controller

A controller that reads from a device, publishes the data, and
alerts on a temperature threshold.

## What this demonstrates

- `Controller` subclass with `@on.interval(...)` trigger
- Direct device-field access from a controller
  (`LineSensor.temperature` reads the latest scaled value)
- `self.publish(topic, data)` — telemetry to cloud
- `self.alert(severity, message)` — notifications
- Writing back to a register (`LineSensor.flow_rate = 0`) for
  emergency actuation

## Hardware required

The line sensor from example 02 (Modbus TCP, registers 40001–40004
with flow rate writable). Same `SENSOR_HOST` env var.

## Compile + deploy

```bash
cd examples/04_basic_controller
SENSOR_HOST=192.168.1.50 scadable compile --output dist
scp dist/bundle.tar.gz gw:/var/lib/scadable/bundle.tar.gz
ssh gw "systemctl restart scadable-gateway"
```

## Expected behavior

Every 5 s the gateway reads sensor values, publishes
`{"temperature": ..., "pressure": ...}`, and emits a `warning` /
`critical` alert if temperature exceeds 85 / 95°C. At 95°C it also
writes 0 to the flow-rate register to stop the line.

## Try it / extend it

- Replace the polling pattern with `@on.threshold(LineSensor.temperature, above=95)` so the trip is event-driven instead of polled.
- Tag the publish with `quality="stale"` when the last read failed,
  so dashboards can color-code uncertain data.
- Add a `@on.message("commands/reset")` handler so an operator can
  restart flow from the dashboard.
