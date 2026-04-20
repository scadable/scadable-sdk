# 07 — Historian + device OTA

Cloud time-series storage at a slower-than-poll cadence, plus
Modbus-driven firmware updates for the downstream device.

## What this demonstrates

- `historian = every(5, MINUTES)` — cloud rollup independent of poll rate
- `ModbusOTA(...)` — push firmware to a downstream PLC via register writes
  - `version` register holds current firmware version
  - `firmware` register range receives chunked binary
  - `trigger` register kicks off the flash

## Hardware required

A Modbus TCP device with OTA-capable firmware: a version register,
a contiguous range for firmware bytes, and a "go" register. Tested
against a Schneider M251 with the OTA add-on.

## Compile + deploy

```bash
cd examples/07_historian_and_ota
SENSOR_HOST=192.168.1.50 scadable compile --output dist
```

## Expected behavior

Polled samples land in the gateway's local buffer at 5 s cadence.
Every 5 minutes a rollup is posted to the cloud historian
(TimescaleDB). When the dashboard initiates an OTA, the gateway
chunks the firmware blob into the configured register range and
sets the trigger register; rollback is automatic on version
mismatch after restart.

## Try it / extend it

- Switch the historian cadence to `every(1, MINUTES)` for finer
  resolution at a cloud-storage cost trade-off.
- Use `store=False` on noisy registers so they're not historized.
