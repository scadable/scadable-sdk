# 08 — Declarative PID control

A complete boiler temperature control loop with a `PID(...)` block.

## What this demonstrates

- `PID(input, output, setpoint, kp, ki, kd, output_min, output_max)`
- Declarative control: the SDK runtime owns the loop
- Dynamic setpoint updates from a controller method
- Reading PID state (error, integral, last output) for telemetry

## Hardware required

- A temperature probe (Modbus TCP, 1 Hz polling)
- A burner with a PWM-writable register for the heating element

## Compile + deploy

```bash
cd examples/08_pid_control
PROBE_HOST=192.168.1.40 BURNER_HOST=192.168.1.41 \
  scadable compile --output dist
```

## Expected behavior

Every loop tick (matched to the input poll rate), the runtime
computes PID error against setpoint and writes the burner PWM,
clamped between 0 and 100. An `@on.message("set-target")` handler
on the controller lets an operator change the setpoint live from
the dashboard.

## Try it / extend it

- Cascade: feed the output of this PID into the setpoint of a
  second PID for a primary/secondary loop.
- Add a `@on.threshold(TempProbe.outlet_temp, above=100)` safety
  override that drops the burner to 0 regardless of PID.
