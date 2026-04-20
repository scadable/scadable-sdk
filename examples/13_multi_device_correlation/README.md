# 13 — Multi-device correlation

A controller that pulls fields from three devices, correlates them,
and publishes a derived metric.

## What this demonstrates

- Reading from multiple devices in one trigger
- Computing derived metrics (efficiency = output / input)
- Using `Topics` constants to publish a project-defined topic
  (typo-proof across publishers + subscribers)
- Tagging the publish with `quality="stale"` when one of the
  inputs is older than a threshold

## Hardware required

- A line sensor (input metrics)
- An environment sensor (ambient context)
- A motor drive (output metrics)

All Modbus TCP on the same gateway.

## Compile + deploy

```bash
cd examples/13_multi_device_correlation
SENSOR_HOST=... ENV_HOST=... MOTOR_HOST=... \
  scadable compile --output dist
```

## Expected behavior

Every 30 s the controller computes line throughput vs. motor power
draw, normalizes for ambient temperature, and publishes the
efficiency. If any of the inputs hasn't refreshed within 60 s, the
publish carries `quality="stale"` so dashboards can show the
metric as uncertain.

## Try it / extend it

- Add a `@on.threshold(efficiency, below=0.7)` to alert on
  degradation.
- Persist a rolling 1-hour window in local storage and publish a
  trend metric so the dashboard can graph it without a cloud query.
