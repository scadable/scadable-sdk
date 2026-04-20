# 09 — State machine

A multi-step calibration sequence implemented with `StateMachine`
and `State` blocks.

## What this demonstrates

- `StateMachine(initial=..., states=[...])` — declarative FSM
- `State(name, on_enter=, on_exit=, transitions=...)`
- Transitions guarded by sensor readings or time
- Persisted state across reboots via the storage layer

## Hardware required

A pH sensor (Modbus TCP) and a calibration solution feeder
controlled by the same gateway.

## Compile + deploy

```bash
cd examples/09_state_machine
SENSOR_HOST=192.168.1.50 scadable compile --output dist
```

## Expected behavior

The controller cycles through `idle → flushing → calibrating →
verifying → done` states based on time + sensor stability.
Operators can interrupt with `@on.message("commands/abort")`. Each
state transition publishes a status update so the dashboard can
visualize where the calibration is.

## Try it / extend it

- Add a `failed` state that the FSM falls into if calibration
  doesn't converge within N minutes; alert from `on_enter`.
- Replace the time-guarded transition with a sensor-stability
  check: stay in `verifying` until pH variance drops below a
  threshold.
