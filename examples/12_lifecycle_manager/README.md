# 12 — Lifecycle manager (gateway hooks)

Long-running gateway management: startup health checks, periodic
self-test, graceful shutdown.

## What this demonstrates

- `@on.startup` — bring-up sequencing (verify devices online,
  load operator presets from `state`)
- Long-lived background heartbeat publishing
- `@on.shutdown` — flush in-flight uploads, save final state
- Surviving config reloads via `state.set / state.get`

## Hardware required

An ESP32-class gateway with a small bank of low-rate sensors. The
example targets ESP32 in `fleet.toml`, but the same controller
also runs on a Linux gateway.

> ⚠️ **v0.2.0 status:** ESP32 emitter is preview — the validator
> runs the full target check (memory, protocols, dtypes) but
> compiling for `target="esp32"` raises `TargetNotImplementedError`.
> Compile this example for `linux` to actually deploy.

## Compile + deploy

```bash
cd examples/12_lifecycle_manager
SENSOR_HOST=192.168.1.50 scadable compile --target linux --output dist
```

## Expected behavior

On gateway boot the controller checks each declared device for
liveness, loads the last known operator setpoints from local state,
and announces ready. While running it publishes a heartbeat every
30 s. On shutdown (`SIGTERM`) it persists the live setpoints and
ACKs the shutdown signal so systemd can stop the service cleanly.

## Try it / extend it

- Add a `@on.device(..., status=DEGRADED)` handler that fails the
  startup if any critical device is degraded at boot.
- Use `system.info()` in the heartbeat payload to surface gateway
  uptime + load to the dashboard.
