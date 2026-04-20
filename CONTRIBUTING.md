# Contributing to scadable-sdk

Thanks for taking a look. This is a small, focused codebase — easy
to get productive in.

## Repo layout

```
scadable/
  __init__.py           — public re-exports
  _targets.py           — target capability matrix (single source of truth)
  topics.py             — Topics base class for project-level constants
  core.py               — Device + Controller base classes
  registers.py          — Register, Characteristic, Pin, Field
  protocols.py          — modbus_tcp, modbus_rtu, ble, etc. helpers
  triggers.py           — @on.* decorator family
  time.py               — every() + SECONDS/MINUTES/HOURS constants
  control.py            — PID, StateMachine, State
  models.py             — Model, ONNXModel
  storage.py            — DataStore, FileStore, StateStore
  routes.py             — upload_route(), notify()
  ota.py                — ModbusOTA, BLE_DFU, SerialBootloader
  system.py             — system.shutdown/reboot/info
  cli/
    main.py             — typer App registration
    init_cmd.py
    add_cmd.py
    verify_cmd.py
    compile_cmd.py
    templates/          — starter file templates
  compiler/
    __init__.py         — compile_project() entry point
    discover.py         — find scadable.toml + walk devices/controllers/
    parser.py           — AST extraction (devices + controllers)
    validator.py        — cross-references + target capability checks
    memory.py           — RAM estimate per target budget
    emitter/
      __init__.py       — public API + EMITTERS registry
      base.py           — Emitter ABC (manifest concrete; drivers abstract)
      linux.py          — LinuxEmitter — production
      esp32.py          — Esp32Emitter — stub (raises in v0.2.0)
      rtos.py           — RtosEmitter — stub (raises in v0.2.0)

tests/
  conftest.py           — shared fixtures (make_project, basic_modbus_device)
  parser/, validator/, emitter/, cli/, examples/, integration/, portability/

examples/
  01_basic_sensor/  …  10_ml_inference/   — corpus the test suite walks

docs/                   — user + contributor documentation
```

## Setup

```bash
git clone https://github.com/scadable/scadable-sdk
cd scadable-sdk
python -m venv .venv && source .venv/bin/activate
pip install -e ".[test]"
```

## Run the suite

```bash
pytest -q                       # 172 tests, < 1 second
pytest --cov=scadable           # with coverage
ruff check .                    # lint (also: ruff check --fix .)
mypy --strict scadable          # type check
```

CI runs the same on every PR across Python 3.10/3.11/3.12/3.13.

## Adding a new protocol

The DSL/runtime split:

1. **DSL surface** (in `scadable/protocols.py`): add a helper that
   returns a `dict` with `"protocol": "<name>"` plus required params.
2. **Parser** (in `scadable/compiler/parser.py`): add the protocol
   to `_PROTO_DEFAULTS` if there are sensible defaults.
3. **Validator** (in `scadable/compiler/validator.py`): add a branch
   in `_validate_connection` to warn on missing required params.
4. **Capability matrix** (in `scadable/_targets.py`): add the
   protocol to each target's `protocols` set where it's supported.
5. **Tests**:
   - `tests/parser/test_connections.py` — add a test exercising the
     new helper end-to-end.
   - `tests/validator/test_validator.py` — add a missing-param
     warning test.
   - `tests/portability/test_portability.py` — add capability checks
     to the appropriate targets.

The runtime side (the actual protocol driver) lives in `gateway-linux`,
not here.

## Adding a new target

1. **Capability matrix** (in `scadable/_targets.py`): add a
   `TargetSpec` for it with realistic memory/protocol/dtype limits.
2. **Emitter** (in `scadable/compiler/emitter/`): add `<target>.py`
   with a class that subclasses `Emitter` and implements
   `emit_driver_configs`. Look at `linux.py` for the canonical
   example.
3. **Registry** (in `scadable/compiler/emitter/__init__.py`):
   register your new emitter in `EMITTERS`.
4. **Tests**:
   - `tests/portability/test_portability.py` — add invariants for
     the new target's capability surface.
   - `tests/emitter/test_emitter.py` — add registry/dispatch tests.
   - Optional: `tests/examples/` — add target=X variants once an
     example fits the capability matrix.

## Code style

- `ruff` with `select = E F W I UP B SIM`. We don't enforce line
  length; `ruff format` handles wrapping where it matters.
- `mypy --strict` on the `scadable/` package. Tests are not strict-typed.
- Docstrings on every public function — they're rendered in
  [docs/dsl-reference.md](docs/dsl-reference.md).

## Commits + PRs

- Commit messages: imperative mood, ≤ 72 chars first line, body
  explaining *why* (not *what*). Example:

  ```
  feat(parser): emit warning on SyntaxError instead of silent skip

  Silent skips were the #1 "why isn't my device showing up" support
  question in v0.1. CompileResult.warnings now carries the file path
  and the first error line so users can spot it immediately.
  ```

- PR description: link the issue, summarize the change in 2–3
  sentences, list any user-visible behavior change so we can flag it
  in the changelog.

## Releasing

`release.yml` publishes to PyPI on tag push:

```bash
# Bump scadable/__init__.py and pyproject.toml to the new version.
# Add a CHANGELOG.md entry.
git commit -am "release: v0.X.Y"
git tag v0.X.Y && git push --tags
```

CI builds the wheel + sdist and publishes via PyPI trusted publishing.
