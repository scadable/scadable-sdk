# 03 — Multiple protocols on one gateway

A Modbus TCP PLC, a BLE environmental sensor, and a GPIO door
contact — all running on the same gateway.

## What this demonstrates

- Mixing protocols in one project
- BLE GATT `Characteristic` UUIDs (16-bit short form)
- GPIO `Pin` declarations
- Per-protocol poll cadences (Modbus 5 s, BLE 30 s, GPIO 1 s)

## Hardware required

- A Modbus TCP PLC (Schneider, AB CompactLogix, Siemens S7)
- A BLE 5 environmental sensor exposing standard GATT UUIDs
  (Ruuvi, Xiaomi LYWSDCGQ)
- A GPIO door contact wired to BCM pin 17

> ⚠️ **v0.2.0 status:** Modbus is production. BLE + GPIO drivers
> ship in `gateway-linux` v0.3. The DSL accepts them today and the
> compile produces YAML, but the runtime won't have a driver to
> consume those configs yet.

## Compile + deploy

```bash
cd examples/03_multiple_protocols
SENSOR_HOST=192.168.1.50 \
ENV_SENSOR_MAC=AA:BB:CC:DD:EE:FF \
scadable compile --output dist
```

## Expected behavior

Three drivers spawn (one per device). Each publishes on its own
schedule. From the controller side they're indistinguishable —
`MyPLC.temperature`, `EnvSensor.co2`, `DoorContact.state` all read
the same way regardless of underlying transport.

## Try it / extend it

- Add a Modbus RTU device on `/dev/ttyUSB0` to see four protocols
  at once.
- Wrap the BLE characteristic in a controller `@on.threshold` to
  alert when CO₂ exceeds 1000 ppm.
