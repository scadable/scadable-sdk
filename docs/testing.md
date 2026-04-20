# Testing (contributors)

How to run the test suite, what's in it, and how to add new tests.

## Run the suite

```bash
# from scadable-sdk/
pip install -e .[test]
pytest -q
```

Expected: ~172 tests, all green, in under 1 second.

## Useful invocations

```bash
pytest -q                               # everything
pytest -q tests/parser                  # one stage
pytest -q -k portability                # by name
pytest -q tests/examples -v             # parametrized corpus
pytest --cov=scadable --cov-report=term # coverage
pytest -x                               # stop on first failure
pytest --lf                             # rerun only last failures
```

Coverage target: 85% line coverage on `scadable/`.

## Layout

```
tests/
├── conftest.py          # shared fixtures: tmpdir projects, sample devices
├── parser/              # AST parsing — connections, registers, triggers, edge cases
├── validator/           # cross-refs + target-capability matrix checks
├── emitter/             # YAML format, manifest schema, bundle, registry
├── cli/                 # typer CliRunner: init, add, verify, compile, version
├── examples/            # parametrized over examples/ — verify + compile + smoke
├── integration/         # full pipeline: init → add → verify → compile
└── portability/         # capability matrix invariants — guardrails for ESP/RTOS
```

One file per concern. If you find yourself reading more than ~150
lines to add a test, start a new file.

## Fixtures (`tests/conftest.py`)

| Fixture                  | What it gives you                                      |
|--------------------------|--------------------------------------------------------|
| `examples_dir`           | `Path` to the repo's `examples/`                       |
| `all_example_paths`      | List of every example project path (parametrize friendly) |
| `make_project(tmp_path)` | Factory: spins up a minimal project tree on disk       |
| `basic_modbus_device`    | Sample device dict for emitter/validator tests         |
| `basic_controller`       | Sample controller dict for trigger tests               |

Most tests use `tmp_path` (built-in) plus `make_project` to get a
disposable project on disk.

## Adding tests

### Parser

```python
def test_register_dtype_uint32_parses(make_project):
    proj = make_project(devices={
        "s.py": dedent("""
            from scadable import Device, Register, modbus_tcp
            class S(Device):
                id = "s-1"
                connection = modbus_tcp(host="x")
                registers = [Register(40001, "x", dtype="uint32")]
        """)
    })
    devices, _, warnings = parse_devices(discover_files(proj).device_files)
    assert not warnings
    assert devices[0]["registers"][0]["dtype"] == "uint32"
```

### Validator

Pass a hand-rolled device dict (faster than going through the
parser):

```python
def test_rejects_float64_on_rtos():
    devices = [{"id": "d", "connection": {"protocol": "modbus_rtu", "port": "/dev/x"},
                "registers": [{"address": 40001, "name": "t", "dtype": "float64"}]}]
    errors, _ = validate(devices, [], {}, target="rtos")
    assert any("float64" in e for e in errors)
```

### Emitter

Use `tmp_path` for the output directory; load the YAML back to
assert structure (don't pin string output, indent is incidental).

### CLI

`typer.testing.CliRunner` invokes commands without spawning a
process:

```python
from typer.testing import CliRunner
from scadable.cli.main import app

def test_version():
    result = CliRunner().invoke(app, ["version"])
    assert result.exit_code == 0
    assert "scadable-sdk" in result.stdout
```

## Snapshot tests

YAML output is snapshot-tested for the example corpus
(`tests/examples/`). To regenerate after an intentional format
change:

```bash
pytest tests/examples --snapshot-update
git diff tests/examples/__snapshots__/  # review carefully
```

If you can't easily explain why every line of the diff is correct,
the format change probably has unintended consequences.

## Portability invariants

`tests/portability/test_portability.py` is the early-warning system
for ESP/RTOS. It asserts:

- The target registry has exactly three entries.
- Linux supports every protocol + dtype the SDK emits.
- ESP32 rejects modbus_tcp, RTSP (correct).
- RTOS rejects float64 (correct).
- `TargetNotImplementedError` subclasses `NotImplementedError` so
  generic exception handlers catch it.

Add to this file when you add a target capability assertion you
want to lock in.

## CI

`.github/workflows/ci.yml` runs lint (ruff), typecheck (mypy
strict), and the test matrix on Python 3.10 / 3.11 / 3.12 / 3.13 on
every push and PR. Green CI is required before merging.

## Pre-commit (local)

Optional but useful:

```bash
pip install pre-commit
pre-commit install
```

Runs ruff + mypy on staged files. Same checks CI runs, just earlier.
