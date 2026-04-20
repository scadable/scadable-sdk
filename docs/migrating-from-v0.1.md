# Migrating from v0.1 → v0.2

The v0.2 release is intentionally low-friction. There's exactly one
behavior change you need to know about; everything else is opt-in.

## TL;DR

```bash
pip install --upgrade scadable-sdk
scadable compile        # output is now drivers/*.yaml (was *.toml)
```

Re-run `compile` once. Update any `scp` deploy script that hard-coded
`*.toml` paths. Done.

## What changed

### Driver config emit format: TOML → YAML

v0.1 emitted `dist/<target>/drivers/<id>.toml` files. v0.2 emits
`dist/<target>/drivers/<id>.yaml`. The schema is identical — same
field names, same nesting — only the wire format flipped.

Why: gateway-linux's `DriverManager` reads `config.yaml` (or `.json`)
natively and silently skipped TOML. Customers were doing manual TOML→
YAML conversion to deploy. Now the SDK emits what the gateway reads.

**If you have a deploy script** that copies the compiled drivers onto
a gateway, change the file extension:

```diff
- scp build/drivers/*.toml pi@gw:/etc/scadable/devices/.../config.yaml
+ scp build/drivers/*.yaml pi@gw:/etc/scadable/devices/.../config.yaml
```

(The destination filename was already `.yaml` because that's what
the gateway looks for.)

### Parser warns on `SyntaxError` instead of silently skipping

In v0.1, a Python file that didn't parse silently disappeared from
the compile. v0.2 surfaces the failure as a `CompileResult.warnings`
entry and prints it from the CLI:

```text
warning: skipped device file devices/broken.py — SyntaxError on line 3: invalid syntax
```

If you previously had silently-broken files in your repo, they'll
now surface as warnings. Fix them or delete them.

### Validator runs target-capability checks

Compiling for `target="esp32"` or `"rtos"` now flags compile-time
errors for unsupported protocols and dtypes:

```text
error: Device 'temp-1': protocol 'modbus_tcp' is not supported on target 'esp32'
       (allowed: ['gpio', 'i2c', 'modbus_rtu', 'spi'])
```

If you were targeting `linux`, this never fires. If you were
opportunistically compiling for `esp32` to test the workflow, you'll
now see real capability checks.

## What's new (opt-in)

All v0.2 additions have v0.1-compatible defaults. You don't need to
change a single line of existing code unless you want the new
behavior.

### `Register(..., dtype=...)`

Default `"uint16"` matches v0.1 behavior (single-word reads). Specify
`"uint32"`, `"float32"` etc. for multi-word registers:

```python
Register(40001, "temp",  dtype="float32")  # v0.2
Register(40001, "temp")                    # v0.1 / v0.2 — both work
```

### `Register(..., on_error=...)`

Default `"skip"` matches v0.1 (drop sample on read failure).
Switch to `"last_known"` to hold the previous value and tag it
`quality="stale"`, or `"fail"` to surface as an alert:

```python
Register(40001, "temp", on_error="last_known")
```

### `Register(..., endianness=...)`

Default `"big"` matches v0.1 byte order. Set to `"little"` for
devices that flip word order:

```python
Register(40001, "flow", dtype="uint32", endianness="little")
```

### `Topics` constants

New `Topics` base class for project-level topic constants. v0.1 used
inline strings:

```python
# v0.1 — string-typo prone
self.publish("sensor-data", {...})

@on.message("set-target")
def update(self, message): ...
```

```python
# v0.2 — caught at compile time
from scadable import Topics

class Topics(Topics):
    SENSOR_DATA = "sensor-data"
    SET_TARGET  = "set-target"

self.publish(Topics.SENSOR_DATA, {...})

@on.message(Topics.SET_TARGET)
def update(self, message): ...
```

### `self.publish(..., quality=...)`

Default `"good"` matches v0.1 implicit behavior. Tag with
`"stale"` or `"bad"` so downstream dashboards can color-code:

```python
self.publish(Topics.SENSOR_DATA, {"temp": t},
             quality="stale" if reading_age > 60 else "good")
```

## Compatibility window

v0.2 is fully backward-compatible with v0.1 source code. Every example
in `examples/` was authored against v0.1 and still compiles green
under v0.2 with no edits.

The only case that needs attention is the deploy script (TOML →
YAML extension) and any project that used the `dtype` / `on_error`
defaults differently than v0.2 prescribes (which is impossible —
v0.1 had no such fields).
