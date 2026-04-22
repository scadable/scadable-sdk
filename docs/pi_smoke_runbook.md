# Pi smoke runbook — modbus sim → gateway → dashboard

End-to-end verification path for the Pi gateway already enrolled in
SCADABLE org (gateway_id `8a9afb48-eb7d-43d2-a49a-3c2edd56337e`).

This runbook does NOT require a fleet release tag. Everything is
single-target — only your one Pi sees the new binary.

## Prerequisites

- SSH access to the Pi (`pi@<lan-ip>` or `pi@<hostname>.local`).
- `python -m pip install scadable-sdk[sim]` (or local editable install
  of the sdk repo) on either your laptop or the Pi — the Modbus sim
  runs as a Python process.
- Local dev box has the cross-compiled binary at:
  `gateway-linux/target/aarch64-unknown-linux-musl/release/gateway-linux`
  (built by `cross build --release -p gateway-linux --target aarch64-unknown-linux-musl`).

## Stage 1 — verify the sim by itself (laptop, 1 min)

```bash
cd scadable-sdk
python -m scadable.sim.modbus_sim --config examples/01_basic_sensor/sim.yaml
# → should print: "modbus-sim listening on 127.0.0.1:1502"
```

In another terminal, hit it with a Modbus client to confirm:

```bash
python -c "
from pymodbus.client import ModbusTcpClient
c = ModbusTcpClient('127.0.0.1', port=1502); c.connect()
r = c.read_holding_registers(0, 2, slave=1)
print('values:', r.registers)
"
```

You should see two integers that drift slowly each call.

## Stage 2 — deploy v0.3.4 binary to the Pi (5 min)

```bash
# From the laptop, with the cross-compiled binary in place:
GATEWAY_IP=<pi.lan.ip>
scp gateway-linux/target/aarch64-unknown-linux-musl/release/gateway-linux \
    pi@$GATEWAY_IP:/tmp/scadable-gateway-v0.3.4

# Swap on the Pi:
ssh pi@$GATEWAY_IP <<'EOS'
sudo systemctl stop scadable-gateway
sudo mv /usr/local/bin/scadable-gateway /usr/local/bin/scadable-gateway.v0.3.3
sudo mv /tmp/scadable-gateway-v0.3.4 /usr/local/bin/scadable-gateway
sudo chmod 0755 /usr/local/bin/scadable-gateway
sudo systemctl start scadable-gateway
sudo journalctl -u scadable-gateway -f --since=now
EOS
```

In the journal you should see:
- `metrics_interval_secs=N` (≥5; if it was set lower, the floor clamp warning fires)
- `MQTT online` within ~15s
- presence published

Press Ctrl+C on the journal once it's stable.

## Stage 3 — point the gateway at the sim (3 min)

The sim either runs **on the Pi** (port 1502) or on your **laptop** at
`<laptop_ip>:1502`. Pick whichever the Pi can reach. If laptop, make
sure the firewall allows the inbound MQTT port and your laptop's
on the same LAN.

Drop a Modbus device config on the Pi:

```bash
ssh pi@$GATEWAY_IP <<EOS
sudo mkdir -p /etc/scadable/devices /etc/scadable/drivers
# This TOML matches the contract crate's DeviceConfig.
sudo tee /etc/scadable/devices/modbus.toml <<'TOML'
[[devices]]
device_id = "sim-temp-1"
transport = "tcp"
host = "<sim_host>"
port = 1502
slave = 1
poll_ms = 1000           # 1Hz; floor is 100ms

[[devices.registers]]
addr = 40001
type = "holding"
name = "temperature"
unit = "C"
scale = 0.1
TOML

# Modbus driver binary needs to be present too. If your gateway image
# already shipped driver-modbus alongside, you're done. Otherwise
# scp the binary from your dev box first:
EOS
```

If `driver-modbus` isn't installed, build + ship it the same way:

```bash
cross build --release -p scadable-driver-modbus --target aarch64-unknown-linux-musl
scp gateway-linux/target/aarch64-unknown-linux-musl/release/driver-modbus \
    pi@$GATEWAY_IP:/tmp/driver-modbus
ssh pi@$GATEWAY_IP "sudo mv /tmp/driver-modbus /etc/scadable/drivers/driver-modbus && sudo chmod 0755 /etc/scadable/drivers/driver-modbus && sudo systemctl restart scadable-gateway"
```

## Stage 4 — verify in the dashboard (2 min)

Open the dashboard, navigate to the gateway's detail page → Insights.

Expected within 1 minute:
- **Status: online** (presence chip green)
- **Messages sent / sec**: roughly 1 (sim ticks at 1Hz × 1 register
  = 1 sample/s; bounded by the new 10/s token bucket)
- **Latency p50 / p95**: under 100ms (LAN-local)
- **Telemetry stream** (gateway → telemetry/sim-temp-1 topic): rows
  appearing in the storage tab every second

## Stage 5 — verify the rate-limit floor actually engages

```bash
ssh pi@$GATEWAY_IP "sudo systemctl edit scadable-gateway"
# add an override:
#   [Service]
#   Environment=METRICS_INTERVAL_SECS=1
ssh pi@$GATEWAY_IP "sudo systemctl restart scadable-gateway"
sudo journalctl -u scadable-gateway --since=now | grep -i 'clamping to'
# → expect: "metrics_interval_secs=1 below floor; clamping to 5s"
```

Reset:

```bash
ssh pi@$GATEWAY_IP "sudo systemctl revert scadable-gateway && sudo systemctl restart scadable-gateway"
```

## What to do when something fails

- **No telemetry in dashboard**: `journalctl -u scadable-gateway` →
  look for "driver subprocess died" or "MQTT disconnected".
- **`driver-modbus connect timeout`**: the sim isn't reachable from
  the Pi. Confirm `nc -zv <sim_host> 1502` from the Pi.
- **`sample rate-limited`**: token bucket dropped a publish. Expected
  occasionally if poll_ms is too low; bump to 1000ms.

## Rollback

If anything goes sideways, restore the prior binary:

```bash
ssh pi@$GATEWAY_IP "sudo systemctl stop scadable-gateway && sudo mv /usr/local/bin/scadable-gateway.v0.3.3 /usr/local/bin/scadable-gateway && sudo systemctl start scadable-gateway"
```

## Promoting to fleet release (only after Stage 4 is green)

When you're satisfied with the Pi result:

```bash
cd gateway-linux
# bump version locally first if not already done
git tag v0.3.4 && git push origin v0.3.4
# (this triggers the release workflow → builds binaries → notifies
#  EVERY enrolled gateway via service-edge → fleet rollout.)
```
