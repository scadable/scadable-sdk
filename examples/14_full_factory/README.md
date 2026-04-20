# 14 — Full factory

A realistic multi-gateway, multi-controller deployment. Two
gateways, four devices, four controllers, fleet-wide environment
config.

## What this demonstrates

- A full project layout (`devices/`, `controllers/`, `models/`,
  `routes.py`, `storage.py`, `fleet.toml`)
- Multi-gateway `fleet.toml` with per-gateway env vars
- Different gateway targets (`linux-arm64` floor 1, `esp32` floor 2)
- Subset deployment per gateway (floor 2 only gets Modbus devices
  because ESP32 doesn't host BLE/RTSP)
- Production controllers: production monitor, motor controller,
  safety manager, lifecycle manager — each with focused
  responsibilities

## Hardware required

- Floor 1: Raspberry Pi 4 + Modbus PLC + BLE env sensor +
  RTSP camera + Modbus motor drive
- Floor 2: ESP32 dev kit + Modbus PLC

## Compile + deploy

```bash
cd examples/14_full_factory
scadable compile --target linux --output dist/floor-1
# (ESP32 emitter is preview in v0.2.0; floor 2 is forward-compat)
scadable verify --target esp32       # confirms floor-2 fits
```

## Expected behavior

Each gateway runs only the devices + controllers in its fleet.toml
slice. Controllers correlate across the gateway-local devices.
Routes upload incident captures to S3 and post Slack notifications
on critical alerts. Lifecycle manager handles boot + shutdown
cleanly per gateway.

## Try it / extend it

- This example is the closest to a customer-shaped project — fork
  it and substitute your own device configs and thresholds.
- Add a third gateway with `target = "rtos"` and only the modbus_rtu
  + GPIO devices (validator will tell you what's compatible).
- Wire the safety manager into a state machine for a multi-stage
  e-stop with operator confirmation.
