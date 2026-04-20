# 06 — Local storage

Storing data, files, and key/value state on the gateway's local
disk for offline operation and post-hoc analysis.

## What this demonstrates

- `data.write(...)` — append to local time-series buffer
- `state.set(...) / state.get(...)` — durable key/value
- `files.put(...)` — local file blob store
- Local storage works offline; gateway sync queue flushes when
  cloud connectivity returns

## Hardware required

A Modbus line sensor. Storage is gateway-local, so any disk-backed
target works. On Linux, defaults sit under
`/var/lib/scadable/storage/`.

## Compile + deploy

```bash
cd examples/06_storage
SENSOR_HOST=192.168.1.50 scadable compile --output dist
```

## Expected behavior

Every 5 s the controller logs the current temperature into the
local time-series buffer (queryable from later controllers via
`data.read("temperature", since=...)`). The most recent value is
also stored under a state key. Periodically the gateway flushes
buffered data to the cloud historian.

## Try it / extend it

- Add a daily snapshot of accumulated state to `files` for audit.
- Use `state.get("last-target", default=20)` so the controller
  survives reboots without re-learning operator setpoints.
