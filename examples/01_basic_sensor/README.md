# 01 — Basic sensor

The hello-world. One Modbus TCP temperature sensor, one register,
polled every five seconds.

## What this demonstrates

- Minimum viable `Device` declaration
- Modbus TCP connection helper with env-var placeholder
- A single scaled register (`scale=0.1` → raw 225 becomes 22.5°C)

## Hardware required

A Modbus TCP device with a 16-bit holding register at address 40001
publishing temperature × 10. Tested against an Acromag 967EN-4008
and a generic Schneider M251.

## Compile + deploy

```bash
cd examples/01_basic_sensor
SENSOR_HOST=192.168.1.50 scadable compile --output dist
scp dist/drivers/temp-1.yaml gw:/etc/scadable/devices/temp-1/config.yaml
```

## Expected behavior

The gateway spawns a Modbus TCP driver, polls register 40001 every
5 s, and publishes `{"temperature": <float>}` on the device's
default uplink topic.

## Try it / extend it

- Add a second register: pressure at 40002, scale 0.01.
- Switch to `every(1, SECONDS)` to poll faster (watch CPU on the gw).
- Change `scale=0.1` to `dtype="float32"` if your device returns IEEE-754.
