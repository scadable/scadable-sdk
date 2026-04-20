# Architecture (contributors)

How the SDK turns a customer's Python project into a deployable
gateway bundle. Read this before changing the compiler.

## The pipeline

```
project/         scadable.compiler
  devices/        ┌─────────┐  ┌──────────┐  ┌────────┐  ┌─────────┐  ┌────────┐
  controllers/ ─→ │ discover│→ │  parser  │→ │validate│→ │ memory  │→ │ emit   │ ─→ dist/
  models/         └─────────┘  └──────────┘  └────────┘  └─────────┘  └────────┘
  scadable.toml
                                                                          ↓
                                                              drivers/*.yaml
                                                              manifest.json
                                                              bundle.tar.gz
```

Five stages. Each is pure, returns dataclasses, and is independently
testable.

### 1. discover (`compiler/discover.py`)

Walks the project directory. Returns a `ProjectFiles` dataclass with
project name + version (from `scadable.toml`) and lists of paths to
device, controller, and model files. No Python execution; pure file
listing.

### 2. parse (`compiler/parser.py`)

AST-only. Walks each file with the `ast` module, extracts class
definitions that subclass `Device` or `Controller`, and pulls out
their attributes (registers, connection helpers, triggers) by reading
the AST nodes. **Never imports user code.** This is what lets the
compiler run in a clean environment without the user's runtime
dependencies installed.

Returns:
- `(devices, class_map, warnings)` from `parse_devices(files)`
- `(controllers, warnings)` from `parse_controllers(files)`

`class_map` is `{"DeviceClassName": "device_id"}` so the validator
can resolve `@on.threshold(LineSensor.temperature)` references.

`SyntaxError` in a user file → recorded as a warning, skipped, never
crashes the parser. (v0.1 silently swallowed these — the most-asked
support question. Fixed in v0.2.)

### 3. validate (`compiler/validator.py`)

Cross-references devices ↔ controllers, plus runs target-capability
checks against `scadable/_targets.py`:

- duplicate register addresses within a device
- missing connection helpers
- protocol/dtype not supported on the chosen target
- controller triggers referencing unknown devices or fields

Returns `(errors, warnings)`. Errors block the compile; warnings
don't.

### 4. memory estimate (`compiler/memory.py`)

Sums runtime + per-device + per-register + per-controller bytes and
compares against `TARGETS[target]["memory_kb"]`. Returns a
`MemoryEstimate` dataclass; mostly informational on Linux, hard
constraint on ESP/RTOS.

### 5. emit (`compiler/emitter/`)

Pluggable emitter package. Pick the right emitter by target name and
call its three methods:

- `emit_driver_configs(devices, out_dir)` → `drivers/<id>.yaml` (Linux)
- `emit_manifest(project, devices, controllers, mem, target, out_dir)` → `manifest.json`
- `emit_bundle(out_dir)` → `bundle.tar.gz`

`LinuxEmitter` is the only production implementation in v0.2.0.
`Esp32Emitter` and `RtosEmitter` are stubs — they raise
`TargetNotImplementedError` with a planned-version message. The DSL
+ validator already accept these targets so users can author
forward-compatible projects today.

## Data shape

The intermediate representation between stages is plain dicts (with
typed dataclasses at the boundaries). Sample device dict from the
parser:

```python
{
    "id": "temp-1",
    "name": "Temp sensor",
    "class_name": "TempSensor",
    "source_file": "/abs/path/devices/temp_sensor.py",
    "connection": {"protocol": "modbus_tcp", "host": "1.2.3.4", "port": 502, "slave": 1},
    "poll_ms": 5000,
    "registers": [
        {"address": 40001, "name": "temp", "type": "holding",
         "dtype": "uint16", "endianness": "big",
         "on_error": "skip", "writable": True},
    ],
}
```

The emitter strips `class_name` + `source_file` before writing
manifest.json (those are compile-internal).

## Adding a new protocol

1. Add a connection helper in `scadable/protocols.py` returning a
   `dict` with at minimum `{"protocol": "<name>", ...params}`.
2. Add the protocol name to relevant targets in `scadable/_targets.py`.
3. Teach the parser to recognize the helper call (look at how
   `modbus_tcp` is handled in `parser.py::_parse_connection`).
4. Add a connection-validation branch in
   `validator.py::_validate_connection`.
5. Update the emitter's YAML schema for the new protocol fields.
6. Add a parser test, validator test, and emitter test (see
   `tests/parser/test_connections.py` for shape).
7. Add a CLI scaffolder template in `scadable/cli/add_cmd.py` so
   `scadable add device <new-protocol> <name>` works.

## Adding a new target

1. Add an entry to `TARGETS` in `scadable/_targets.py` with the
   memory budget, supported protocols, supported dtypes, and a
   sensible `controller_execution` label.
2. Subclass `Emitter` in `scadable/compiler/emitter/<name>.py`.
   Implement at minimum `emit_driver_configs` (raise
   `TargetNotImplementedError` for whichever methods you're not
   shipping yet).
3. Register the emitter in `scadable/compiler/emitter/__init__.py`
   `EMITTERS` dict.
4. Add a portability test in `tests/portability/test_portability.py`
   asserting the target's capability invariants.
5. Add a CHANGELOG entry under "Added".

The `EMITTERS` dispatch is the only place that knows about target
names — the rest of the compiler is target-agnostic.

## Testing strategy

See [docs/testing.md](testing.md). Short version: 172 tests organized
by pipeline stage in `tests/<stage>/`, parametrized over the example
corpus where it makes sense.

## Why this layout

- **Parser separates from validator** so we can do target-capability
  checks without re-walking the AST.
- **Emitter is pluggable** so Linux runtime decisions (subprocess,
  YAML, tar.gz) don't leak into ESP/RTOS plans.
- **AST-only parsing** means the SDK never executes user code at
  compile time. The compiler can run in a sandbox / CI / cloud
  without any of the user's runtime deps.
- **Pure dataclasses between stages** means each stage is unit-
  testable in isolation, no need to reach into compiler internals.
