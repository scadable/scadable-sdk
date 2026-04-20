"""Integration: end-to-end init → add → verify → compile flow."""

from __future__ import annotations

import json
import os
import tarfile
from pathlib import Path

import yaml
from typer.testing import CliRunner

from scadable.cli.main import app
from scadable.compiler import compile_project

runner = CliRunner()


def _project(tmp_path: Path) -> Path:
    os.chdir(tmp_path)
    runner.invoke(app, ["init", "linux", "myproj"])
    proj = tmp_path / "myproj"
    os.chdir(proj)
    return proj


def test_full_pipeline_produces_runnable_artifacts(tmp_path):
    """init → add device → compile → bundle has manifest + driver yaml."""
    proj = _project(tmp_path)
    runner.invoke(app, ["add", "device", "modbus-tcp", "sensor"])
    out = proj / "build"
    runner.invoke(app, ["compile", "--target", "linux", "--output", str(out)])

    assert (out / "manifest.json").exists()
    assert (out / "bundle.tar.gz").exists()

    # Manifest is valid JSON with the expected top-level keys
    manifest = json.loads((out / "manifest.json").read_text())
    assert manifest["target"] == "linux"
    assert manifest["project"]["name"] == "myproj"

    # Driver yaml is a valid YAML doc
    yamls = list((out / "drivers").glob("*.yaml"))
    assert len(yamls) >= 1
    body = yaml.safe_load(yamls[0].read_text())
    assert "device" in body
    assert "protocol" in body["device"]


def test_compile_idempotent(tmp_path):
    """Running compile twice produces identical manifest content."""
    proj = _project(tmp_path)
    runner.invoke(app, ["add", "device", "modbus-tcp", "sensor"])
    out = proj / "build"
    runner.invoke(app, ["compile", "--target", "linux", "--output", str(out)])
    first = (out / "manifest.json").read_text()
    runner.invoke(app, ["compile", "--target", "linux", "--output", str(out)])
    second = (out / "manifest.json").read_text()
    assert first == second


def test_bundle_extracts_to_expected_layout(tmp_path):
    proj = _project(tmp_path)
    runner.invoke(app, ["add", "device", "modbus-tcp", "sensor"])
    out = proj / "build"
    runner.invoke(app, ["compile", "--target", "linux", "--output", str(out)])

    extract = tmp_path / "extract"
    extract.mkdir()
    with tarfile.open(out / "bundle.tar.gz") as tar:
        tar.extractall(extract)
    assert (extract / "manifest.json").exists()
    assert (extract / "drivers").is_dir()


def test_compile_with_invalid_dtype_via_python(tmp_path):
    """Direct API: bad dtype raises at Register construction time."""
    import pytest
    from scadable import Register
    with pytest.raises(ValueError):
        Register(40001, "x", dtype="float128")


def test_compile_with_invalid_on_error_via_python():
    import pytest
    from scadable import Register
    with pytest.raises(ValueError):
        Register(40001, "x", on_error="ignore")


def test_compile_after_add_controller(tmp_path):
    proj = _project(tmp_path)
    runner.invoke(app, ["add", "device", "modbus-tcp", "sensor"])
    runner.invoke(app, ["add", "controller", "monitor"])
    out = proj / "build"
    result = runner.invoke(app, ["compile", "--target", "linux", "--output", str(out)])
    assert result.exit_code == 0
    manifest = json.loads((out / "manifest.json").read_text())
    assert manifest["controllers"], "expected controller in manifest"
