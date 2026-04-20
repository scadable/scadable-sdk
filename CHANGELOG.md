# Changelog

All notable changes to scadable-sdk are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.2.0] — 2026-04-19

### Added

- **`Register` `dtype` parameter.** `Register(40001, "t", dtype="uint16")`
  with default `uint16`. Accepts `int16 | uint32 | int32 | float32 |
  float64 | bool`. Real Modbus needs to know if a register is 1 word
  or 2; previously this was ambiguous.
- **`Register` `on_error` parameter.** `Register(..., on_error="skip")`
  with default `skip`. Accepts `last_known | skip | fail`. Lets you
  control read-failure behavior: drop sample, hold previous value,
  or surface as alert.
- **`Register` `endianness` parameter.** `endianness="big"` (default)
  or `"little"`. Picks byte order for multi-word reads. Only emitted
  to YAML when non-default.
- **`Topics` base class.** Subclass to define project-level string
  constants for `self.publish(Topics.X, ...)` and `@on.message(Topics.X)`.
  Eliminates string-typo bugs that were the #1 silent-failure mode in
  v0.1.
- **`Controller.publish(..., quality=...)` keyword.** Accepts
  `good | stale | bad` (default `good`). Industrial-standard data
  quality tagging that rides through to the cloud as a label.
- **Pluggable target emitters.** New `scadable.compiler.emitter`
  package with `Emitter` ABC, `LinuxEmitter` (production), and
  `Esp32Emitter` + `RtosEmitter` stubs that raise
  `TargetNotImplementedError` with planned-version messages.
- **Target capability matrix.** New `scadable._targets` module with
  per-target memory budget, supported protocols, and supported dtypes.
  Validator reads this and rejects compile-time mismatches like
  "you used `dtype=float64` but your target is RTOS".
- **172-test pytest suite.** `pip install -e .[test] && pytest -q`
  runs in under 1 second. Covers parser, validator, emitter, CLI,
  every example, full pipeline integration, and portability invariants.
- **`scadable compile` CLI subcommand.** Was implemented in
  `compile_cmd.py` but not registered on the typer App in v0.1.
- **Build-system + tooling configuration.** `pyproject.toml` now
  declares setuptools build backend, console script, project URLs,
  classifiers, optional `[test]` deps, and ruff + mypy + pytest +
  coverage tooling configs.

### Changed

- **Driver config emit format: TOML → YAML.** Output filenames go from
  `drivers/{id}.toml` to `drivers/{id}.yaml`. Same logical schema —
  field names and nesting unchanged. gateway-linux's DriverManager
  reads YAML natively, removing a manual conversion step that
  customers were silently skipping.
- **Parser no longer silently swallows `SyntaxError`.** v0.1 silently
  skipped device/controller files that wouldn't parse — the #1 "why
  isn't my device showing up" support question. v0.2 surfaces every
  skip as a `CompileResult.warnings` entry with file path and the
  first error line.
- **Validator is target-aware.** `validate(devices, controllers,
  class_map, target=...)` now returns errors for unsupported
  protocol/dtype combos and a warning when targeting a preview
  platform. Default target is still `linux`.

### Removed

- **Dead `jinja2` dependency.** Imported nowhere; removed from
  `pyproject.toml`.

### Internal

- `pyproject.toml`: bumped from 0.1.0 to 0.2.0.
- `scadable/__init__.py`: bumped `__version__` to "0.2.0".

### Migration

If you were on v0.1, see [docs/migrating-from-v0.1.md](docs/migrating-from-v0.1.md).
TL;DR: the only behavior change is `*.toml` → `*.yaml` driver outputs;
all v0.2 additions are opt-in with v0.1-compatible defaults.

## [0.1.0]

Initial release. Static template scaffolding (`init`, `add`),
AST-based compiler pipeline (parser → validator → memory estimate
→ emitter), TOML driver config output, 10 examples in `examples/`.
