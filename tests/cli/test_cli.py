"""CLI: every subcommand exercised via typer's CliRunner."""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest
from typer.testing import CliRunner

from scadable.cli.main import app

runner = CliRunner()


# ── version + help ──────────────────────────────────────────────


def test_version_subcommand():
    # Pull from the same place the CLI does (scadable.__version__) so
    # bumping the version in scadable/__init__.py + pyproject doesn't
    # regress this test. importlib.metadata reads from installed
    # metadata which can lag the source tree in editable installs;
    # __version__ is what `scadable version` actually prints.
    from scadable import __version__

    result = runner.invoke(app, ["version"])
    assert result.exit_code == 0
    assert __version__ in result.stdout


def test_help_lists_all_subcommands():
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    for cmd in ("init", "add", "verify", "compile", "version"):
        assert cmd in result.stdout


# ── init ────────────────────────────────────────────────────────


def test_init_creates_project_structure(tmp_path):
    os.chdir(tmp_path)
    result = runner.invoke(app, ["init", "linux", "myproj"])
    assert result.exit_code == 0
    proj = tmp_path / "myproj"
    assert proj.is_dir()
    assert (proj / "scadable.toml").exists()
    assert (proj / "devices").is_dir()
    assert (proj / "controllers").is_dir()


def test_init_esp32_target(tmp_path):
    os.chdir(tmp_path)
    result = runner.invoke(app, ["init", "esp32", "espproj"])
    assert result.exit_code == 0
    assert (tmp_path / "espproj" / "scadable.toml").exists()


def test_init_rtos_target(tmp_path):
    os.chdir(tmp_path)
    result = runner.invoke(app, ["init", "rtos", "rtosproj"])
    assert result.exit_code == 0
    assert (tmp_path / "rtosproj" / "scadable.toml").exists()


# ── add ─────────────────────────────────────────────────────────


def _init_project(tmp_path: Path, name: str = "p") -> Path:
    os.chdir(tmp_path)
    runner.invoke(app, ["init", "linux", name])
    proj = tmp_path / name
    os.chdir(proj)
    return proj


# i2c + rtsp are reserved in the SDK API but the `add device` CLI
# template scaffolder doesn't support them yet. Test only what add
# really emits today; tests/parser/test_connections.py covers the
# parser-level support for i2c + rtsp.
@pytest.mark.parametrize("protocol", ["modbus-tcp", "modbus-rtu", "ble", "gpio", "serial"])
def test_add_device_each_protocol(tmp_path, protocol):
    proj = _init_project(tmp_path)
    name = f"dev_{protocol.replace('-', '_')}"
    result = runner.invoke(app, ["add", "device", protocol, name])
    assert result.exit_code == 0
    assert (proj / "devices" / f"{name}.py").exists()


def test_add_controller(tmp_path):
    proj = _init_project(tmp_path)
    result = runner.invoke(app, ["add", "controller", "monitor"])
    assert result.exit_code == 0
    assert (proj / "controllers" / "monitor.py").exists()


# ── verify ──────────────────────────────────────────────────────


def test_verify_clean_project_zero_exit(tmp_path):
    _init_project(tmp_path)
    runner.invoke(app, ["add", "device", "modbus-tcp", "sensor"])
    result = runner.invoke(app, ["verify"])
    assert result.exit_code == 0


def test_verify_target_flag(tmp_path):
    _init_project(tmp_path)
    runner.invoke(app, ["add", "device", "modbus-tcp", "sensor"])
    # modbus-tcp on esp32 should still produce a non-zero exit (or warnings)
    result = runner.invoke(app, ["verify", "--target", "esp32"])
    # verify exit code is non-zero OR error appears
    assert result.exit_code != 0 or "esp32" in result.stdout.lower()


# ── verify --json ───────────────────────────────────────────────


def test_verify_json_clean_project(tmp_path):
    """`--json` on a clean project: ok=true, empty errors/warnings.

    Consumed by the service-agents `validate_syntax` tool, so the
    shape MUST be the documented schema and the stdout MUST contain
    exactly one JSON object.
    """
    _init_project(tmp_path)
    runner.invoke(app, ["add", "device", "modbus-tcp", "sensor"])
    result = runner.invoke(app, ["verify", "--json"])

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["ok"] is True
    assert payload["errors"] == []
    # `validated_files` should at least include the device we added
    assert any(f.endswith("devices/sensor.py") for f in payload["validated_files"])
    # All warnings are well-formed dicts (init scaffolds an empty
    # controllers/ directory, so a warning here is allowed but optional).
    for w in payload["warnings"]:
        assert set(w.keys()) >= {"file", "line", "code", "message", "severity"}
        assert w["severity"] == "warning"


def test_verify_json_broken_device_reports_error(tmp_path):
    """A device file missing required attrs surfaces in `errors`."""
    proj = _init_project(tmp_path)
    # Hand-write a Device class that is missing `connection` + `registers`
    # so the validator emits a structured error.
    (proj / "devices" / "broken.py").write_text(
        "class Broken:\n    id = 'broken'\n",
    )
    result = runner.invoke(app, ["verify", "--json"])

    assert result.exit_code == 1, f"expected non-zero exit, got: {result.stdout}"
    payload = json.loads(result.stdout)
    assert payload["ok"] is False
    assert len(payload["errors"]) >= 1
    err = next(
        e for e in payload["errors"] if e["file"] and e["file"].endswith("broken.py")
    )
    assert err["severity"] == "error"
    assert "missing" in err["message"]
    # Code is reserved for future stable error codes; today it's null.
    assert err["code"] is None
    # Class-level findings carry a line number.
    assert isinstance(err["line"], int)


def test_verify_json_syntax_error_reports_line(tmp_path):
    """Syntax errors include the offending line number."""
    proj = _init_project(tmp_path)
    (proj / "devices" / "bad_syntax.py").write_text("def broken(:\n")
    result = runner.invoke(app, ["verify", "--json"])

    assert result.exit_code == 1
    payload = json.loads(result.stdout)
    assert payload["ok"] is False
    syntax_errs = [
        e
        for e in payload["errors"]
        if e["file"] and e["file"].endswith("bad_syntax.py")
    ]
    assert syntax_errs, f"no syntax error reported in payload: {payload}"
    assert syntax_errs[0]["line"] is not None
    assert syntax_errs[0]["severity"] == "error"


def test_verify_default_output_unchanged(tmp_path):
    """Without `--json`, output is the legacy rich-formatted text."""
    _init_project(tmp_path)
    runner.invoke(app, ["add", "device", "modbus-tcp", "sensor"])
    result = runner.invoke(app, ["verify"])

    assert result.exit_code == 0
    # Legacy human-readable section headers must still be present.
    assert "Checking project structure" in result.stdout
    assert "Validating Python syntax" in result.stdout
    assert "Result" in result.stdout
    # And the output is NOT a JSON document.
    with pytest.raises(json.JSONDecodeError):
        json.loads(result.stdout)


# ── compile ─────────────────────────────────────────────────────


def test_compile_produces_yaml_output(tmp_path):
    proj = _init_project(tmp_path)
    runner.invoke(app, ["add", "device", "modbus-tcp", "sensor"])
    out = proj / "build"
    result = runner.invoke(app, ["compile", "--target", "linux", "--output", str(out)])
    assert result.exit_code == 0
    yamls = list((out / "drivers").glob("*.yaml"))
    assert len(yamls) >= 1


def test_compile_no_toml_files(tmp_path):
    """Regression guard against the v0.1 TOML output."""
    proj = _init_project(tmp_path)
    runner.invoke(app, ["add", "device", "modbus-tcp", "sensor"])
    out = proj / "build"
    runner.invoke(app, ["compile", "--target", "linux", "--output", str(out)])
    tomls = list((out / "drivers").glob("*.toml"))
    assert tomls == []


def test_compile_emits_manifest(tmp_path):
    proj = _init_project(tmp_path)
    runner.invoke(app, ["add", "device", "modbus-tcp", "sensor"])
    out = proj / "build"
    runner.invoke(app, ["compile", "--target", "linux", "--output", str(out)])
    assert (out / "manifest.json").exists()


def test_compile_emits_bundle(tmp_path):
    proj = _init_project(tmp_path)
    runner.invoke(app, ["add", "device", "modbus-tcp", "sensor"])
    out = proj / "build"
    runner.invoke(app, ["compile", "--target", "linux", "--output", str(out)])
    assert (out / "bundle.tar.gz").exists()
