# CLI reference

Every `scadable` subcommand, every flag, every exit code.

```text
$ scadable --help
Scadable Edge SDK — write device logic in Python, compile to native.

Usage: scadable [OPTIONS] COMMAND [ARGS]...

Commands:
  init      Create a new Scadable project.
  add       Add a device, controller, or model to the project.
  verify    Validate the current project.
  compile   Compile device definitions into gateway-deployable artifacts.
  version   Show SDK version.
```

## `scadable init <target> <name>`

Scaffold a new project directory.

| Argument | Required | Notes                                  |
|----------|----------|----------------------------------------|
| `target` | yes      | `linux | esp32 | rtos`                 |
| `name`   | yes      | Project directory name (also pkg name) |

```bash
scadable init linux my-factory
scadable init esp32 sensor-node
```

Creates:

```
<name>/
├── scadable.toml      # project manifest (name, version, target)
├── fleet.toml         # gateway → devices/controllers mapping
├── storage.py         # local storage config (sized for target)
├── routes.py          # cloud upload + notification routes
├── devices/           # empty
├── controllers/       # empty
└── models/            # empty
```

**Exit codes:** `0` success, `1` if `<name>` already exists.

## `scadable add <kind> <protocol-or-name> [name]`

Generate a new device, controller, or model file.

### `scadable add device <protocol> <name>`

| Protocol      | Generated file                              |
|---------------|---------------------------------------------|
| `modbus-tcp`  | `devices/<name>.py` with `modbus_tcp` stub |
| `modbus-rtu`  | `devices/<name>.py` with `modbus_rtu` stub |
| `ble`         | `devices/<name>.py` with `ble` stub        |
| `gpio`        | `devices/<name>.py` with `gpio` stub       |
| `serial`      | `devices/<name>.py` with `serial` stub     |

```bash
scadable add device modbus-tcp line-sensor
# → devices/line_sensor.py with class LineSensor(Device)
```

Name conversion: `kebab-case` and `snake_case` accepted; class is
PascalCase, file is snake_case.

### `scadable add controller <name>`

```bash
scadable add controller temp-monitor
# → controllers/temp_monitor.py with class TempMonitor(Controller)
```

### `scadable add model <name>`

```bash
scadable add model anomaly-detector
# → models/anomaly_detector.py with class AnomalyDetector(ONNXModel)
```

**Exit codes:** `0` success, `1` if the file already exists.

## `scadable verify`

Validate the current project. No side effects, no output files.

| Flag                 | Default | Notes                                    |
|----------------------|---------|------------------------------------------|
| `--target <name>`    | `""`    | Run target-capability checks for this target. Empty = no target check, just structure. |

```bash
scadable verify                    # structure + cross-refs
scadable verify --target esp32     # + capability matrix check
scadable verify --target rtos      # + memory estimate
```

What it checks:

- Project structure (`scadable.toml`, `devices/`, `controllers/`)
- Python syntax in every `*.py` (warnings on parse failure, not errors)
- Device declarations (`id`, `connection`, `registers`)
- Register address ranges
- Controller `@on.*` triggers reference real devices/fields
- (with `--target`) protocol + dtype supported on target
- (with `--target`) memory estimate fits target budget

**Exit codes:** `0` clean, `1` errors found, `2` warnings only.

## `scadable compile`

Run the full pipeline and emit gateway artifacts.

| Flag             | Default  | Notes                                |
|------------------|----------|--------------------------------------|
| `--target <name>`| `linux`  | `linux | esp32 | rtos`              |
| `--output <dir>` | `out`    | Where to write artifacts             |
| `-v`             | `false`  | Verbose: print each stage            |

```bash
scadable compile                              # → out/drivers/, manifest.json, bundle.tar.gz
scadable compile --target linux --output dist
scadable compile --target esp32               # raises TargetNotImplementedError
```

Artifacts (Linux target):

```
out/
├── drivers/
│   ├── line-sensor.yaml
│   └── env-sensor.yaml
├── manifest.json
└── bundle.tar.gz       # ↑ contents, plus models/, etc.
```

Deploy by extracting `bundle.tar.gz` onto the gateway, or copying
`drivers/*.yaml` into `/etc/scadable/devices/<id>/config.yaml`.

**Exit codes:** `0` success, `1` validation errors, `2` emit failure
(disk full, permissions, etc.).

## `scadable version`

Print the installed SDK version.

```bash
$ scadable version
scadable-sdk 0.2.0
```

**Exit codes:** always `0`.

## Common workflows

### Author + verify + compile

```bash
scadable init linux my-factory && cd my-factory
scadable add device modbus-tcp line-sensor
# edit devices/line_sensor.py
scadable verify
scadable compile
```

### Test forward-compat with ESP32

```bash
scadable verify --target esp32       # catches dtype/protocol mismatches early
scadable compile --target esp32      # raises TargetNotImplementedError (expected)
```

### Use in a script

```bash
if scadable verify --target linux; then
    scadable compile --target linux --output dist
    scp dist/drivers/*.yaml gateway:/etc/scadable/devices/
fi
```
