# Error catalog

Every compile error and warning the SDK can emit, with the cause and
the fix. Search this page first when `scadable verify` or `scadable
compile` complains.

Errors fail the compile (non-zero exit). Warnings don't fail the
compile but surface in `CompileResult.warnings` and on the CLI.

## Errors

### `Device 'X': no connection defined`

A device class is missing the `connection = ...` attribute.

**Fix:** add a connection helper, e.g.
`connection = modbus_tcp(host="...")`.

### `Device 'X': duplicate register address N ('a' and 'b')`

Two registers in the same device share the same address. The runtime
can't reason about which one to read first.

**Fix:** check your register list — the second address is wrong, or
one of the entries was copy-pasted.

### `Device 'X': register 'r' uses dtype='Y' which target 'T' doesn't support (allowed: [...])`

You wrote `dtype="float64"` but compiled for `target="rtos"`, which
only supports a narrower set.

**Fix:** either pick a supported dtype, or change the compile target.
See [docs/targets.md](targets.md) for the per-target capability matrix.

### `Device 'X': protocol 'P' is not supported on target 'T' (allowed: [...])`

You used `modbus_tcp(...)` but compiled for `target="esp32"`, which
doesn't host a TCP/IP stack at production scale.

**Fix:** switch the device to `modbus_rtu(...)` (serial), or compile
for `target="linux"`.

### `Controller 'X': @on.data in <method> references unknown device 'd'`

Your `@on.data(SomeDevice)` decorator names a device that the parser
didn't find. Either the device file was excluded, or the import path
is wrong.

**Fix:** confirm `devices/some_device.py` exists, defines a class
inheriting `Device`, and the import in your controller matches.

### `Controller 'X': @on.change in <method> references unknown field 'd.f'`

Same as above but for a field reference (`@on.change(Device.field)`).
Either the device is missing or the register name doesn't match.

**Fix:** check the spelling against the `Register(..., "name")`
declaration on the device.

### `Controller 'X': @on.threshold in <method> references unknown field 'd.f'`

Same shape as `@on.change`.

### `Controller 'X': @on.device in <method> references unknown device 'd'`

Same shape as `@on.data`.

### `unknown target 'X'. Known: linux, esp32, rtos`

You passed `--target windows` (or similar). v0.2.0 ships three
targets and validates the spelling.

**Fix:** pick one of `linux | esp32 | rtos`.

## Warnings

### `target 'esp32' is in preview (preview). DSL accepted; runtime support not yet shipped.`

Compiling for a non-production target. The validator runs full
checks, but the emitter raises `TargetNotImplementedError` rather
than producing an artifact. This is informational — see
[docs/targets.md](targets.md).

### `Device 'X': modbus_tcp host is empty`

You wrote `modbus_tcp(host="")` or the env-var placeholder
(`${HOST}`) wasn't set when verifying. Won't fail the compile, but
the device won't connect at runtime.

**Fix:** populate the env var, or hard-code the host.

### `Device 'X': modbus_rtu port is empty`

Same shape as above for `modbus_rtu(port="")`.

### `Device 'X': BLE mac address is empty`

Same shape for `ble(mac="")`.

### `Device 'X': serial port is empty`

Same shape for `serial(port="")`.

### `Device 'X': RTSP url is empty`

Same shape for `rtsp(url="")`.

### `skipped device file devices/X.py — SyntaxError on line N: ...`

A file in `devices/` didn't parse. v0.2.0 surfaces this as a warning
and continues the compile (v0.1 silently skipped, which was the #1
"why isn't my device showing up" bug).

**Fix:** read the line number; either fix the syntax or delete the
file if it's no longer used.

### `skipped controller file controllers/X.py — SyntaxError on line N: ...`

Same shape for controllers.

## Reading the output

CLI output, after `scadable verify`:

```text
── Result ──
errors:   2
warnings: 1
  • Device 'temp-1': no connection defined
  • Device 'temp-2': protocol 'modbus_tcp' is not supported on target 'esp32' (allowed: ['gpio', 'i2c', 'modbus_rtu', 'spi'])
  • target 'esp32' is in preview (preview). DSL accepted; runtime support not yet shipped.
```

Programmatic access:

```python
from scadable.compiler import compile_project

result = compile_project(Path("./myproj"), target="linux")
for err in result.errors:
    print("error:", err)
for warn in result.warnings:
    print("warn:", warn)
```
