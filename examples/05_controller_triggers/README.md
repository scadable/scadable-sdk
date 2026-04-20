# 05 — Controller triggers

The full inventory of `@on.*` decorators on one controller.

## What this demonstrates

- `@on.interval(...)` — periodic
- `@on.threshold(field, above=, below=)` — value crossings
- `@on.change(field)` — every change in a field
- `@on.message(topic)` — inbound MQTT command
- `@on.startup` / `@on.shutdown` — lifecycle hooks
- `@on.device(device, status)` — device status changes

## Hardware required

A line sensor and a motor drive (both Modbus TCP). The motor is
the actuator — its setpoint register is written by the controller
in response to thresholds and inbound commands.

## Compile + deploy

```bash
cd examples/05_controller_triggers
SENSOR_HOST=... MOTOR_HOST=... scadable compile --output dist
```

## Expected behavior

- On startup: publish `{"state": "armed"}` on the status topic.
- Every 10 s: heartbeat publish.
- When `LineSensor.temperature` crosses above 85: derate the motor.
- When an inbound message arrives on `commands/setpoint`: update
  the motor's setpoint to `message["value"]`.
- On `LineSensor` going `DISCONNECTED`: alert and pause the motor.
- On shutdown: publish `{"state": "shutting-down"}`.

## Try it / extend it

- Add `@on.threshold(..., below=10)` to detect underrun conditions.
- Combine `@on.change` + `Topics` constants for a typo-proof
  publish/subscribe pattern (see example 14).
