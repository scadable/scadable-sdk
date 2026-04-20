"""CLI: every subcommand exercised via typer's CliRunner."""

from __future__ import annotations

import os
from pathlib import Path

import pytest
from typer.testing import CliRunner

from scadable.cli.main import app

runner = CliRunner()


# ── version + help ──────────────────────────────────────────────


def test_version_subcommand():
    result = runner.invoke(app, ["version"])
    assert result.exit_code == 0
    assert "0.2.0" in result.stdout


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
    proj = _init_project(tmp_path)
    runner.invoke(app, ["add", "device", "modbus-tcp", "sensor"])
    result = runner.invoke(app, ["verify"])
    assert result.exit_code == 0


def test_verify_target_flag(tmp_path):
    proj = _init_project(tmp_path)
    runner.invoke(app, ["add", "device", "modbus-tcp", "sensor"])
    # modbus-tcp on esp32 should still produce a non-zero exit (or warnings)
    result = runner.invoke(app, ["verify", "--target", "esp32"])
    # verify exit code is non-zero OR error appears
    assert result.exit_code != 0 or "esp32" in result.stdout.lower()


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
