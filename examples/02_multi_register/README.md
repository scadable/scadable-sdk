# 02 — Multiple registers per device

One device with several measurements: temperature, pressure, flow
rate, plus a debug flag excluded from the historian.

## What this demonstrates

- Multiple `Register(...)` entries on a single device
- Mixed units (°C, bar, L/min) and scales (0.1, 0.01)
- `writable=True` for a setpoint register
- `store=False` to exclude noisy / debug registers from the historian
- `historian = every(5, MINUTES)` for cloud time-series rollup

## Hardware required

A Modbus TCP device with the four registers at 40001–40004. The
flow-rate register (40003) must accept writes (it's RW in this
example).

## Compile + deploy

```bash
cd examples/02_multi_register
SENSOR_HOST=192.168.1.50 scadable compile --output dist
scp dist/drivers/line1-temp-pressure.yaml gw:/etc/scadable/devices/line1-temp-pressure/config.yaml
```

## Expected behavior

The driver reads 40001–40004 every 5 s. Temperature, pressure, and
flow rate are pushed through the gateway → cloud uplink. Every 5
minutes a historian sample (excluding `debug_flag`) lands in
TimescaleDB. Writing to `flow_rate` from a controller scales the
value back through `1/scale` and writes the raw word.

## Try it / extend it

- Add `dtype="float32"` to flow rate if your device exposes it as a
  32-bit float across 40003–40004.
- Add `on_error="last_known"` so transient read failures hold the
  previous value tagged `quality="stale"` instead of dropping it.
