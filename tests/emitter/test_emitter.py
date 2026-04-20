"""Emitter: YAML output, manifest schema, bundle, registry, per-target stubs."""

from __future__ import annotations

import json
import tarfile

import pytest
import yaml

from scadable._targets import TargetNotImplementedError
from scadable.compiler import compile_project
from scadable.compiler.discover import ProjectFiles
from scadable.compiler.emitter import (
    EMITTERS,
    Esp32Emitter,
    LinuxEmitter,
    RtosEmitter,
    emit_driver_configs,
)
from scadable.compiler.memory import MemoryEstimate

# ── registry ─────────────────────────────────────────────────────


def test_emitter_registry_has_three_targets():
    assert set(EMITTERS) == {"linux", "esp32", "rtos"}


def test_emitter_classes_match_targets():
    assert isinstance(EMITTERS["linux"], LinuxEmitter)
    assert isinstance(EMITTERS["esp32"], Esp32Emitter)
    assert isinstance(EMITTERS["rtos"], RtosEmitter)


def test_esp32_emitter_raises_target_not_implemented(tmp_path):
    with pytest.raises(TargetNotImplementedError) as exc:
        EMITTERS["esp32"].emit_driver_configs([], tmp_path)
    assert "v0.3" in str(exc.value)


def test_rtos_emitter_raises_target_not_implemented(tmp_path):
    with pytest.raises(TargetNotImplementedError) as exc:
        EMITTERS["rtos"].emit_driver_configs([], tmp_path)
    assert "v0.4" in str(exc.value)


def test_unknown_target_at_dispatch_raises(tmp_path):
    with pytest.raises(ValueError):
        emit_driver_configs([], tmp_path, target="windows")


# ── linux YAML output ────────────────────────────────────────────


SAMPLE_DEVICE = {
    "id": "temp-1",
    "name": "Temp",
    "connection": {"protocol": "modbus_tcp", "host": "1.2.3.4", "port": 502},
    "poll_ms": 5000,
    "registers": [
        {
            "address": 40001,
            "name": "t",
            "type": "holding",
            "dtype": "float32",
            "endianness": "little",
            "on_error": "last_known",
            "unit": "°C",
            "scale": 0.1,
            "writable": True,
        },
    ],
}


def test_linux_yaml_output_path(tmp_path):
    paths = LinuxEmitter().emit_driver_configs([SAMPLE_DEVICE], tmp_path)
    assert paths == [tmp_path / "drivers" / "temp-1.yaml"]
    assert paths[0].exists()


def test_linux_yaml_no_toml_regression(tmp_path):
    """Guard: never emit .toml again."""
    LinuxEmitter().emit_driver_configs([SAMPLE_DEVICE], tmp_path)
    files = list((tmp_path / "drivers").iterdir())
    assert all(not f.name.endswith(".toml") for f in files)


def test_linux_yaml_parses_clean(tmp_path):
    LinuxEmitter().emit_driver_configs([SAMPLE_DEVICE], tmp_path)
    body = yaml.safe_load((tmp_path / "drivers" / "temp-1.yaml").read_text())
    assert body["device"]["id"] == "temp-1"
    assert body["device"]["protocol"] == "modbus_tcp"
    assert body["connection"]["host"] == "1.2.3.4"
    assert body["registers"][0]["dtype"] == "float32"
    assert body["registers"][0]["on_error"] == "last_known"


def test_linux_yaml_unicode_unit_preserved(tmp_path):
    LinuxEmitter().emit_driver_configs([SAMPLE_DEVICE], tmp_path)
    body = yaml.safe_load((tmp_path / "drivers" / "temp-1.yaml").read_text())
    assert body["registers"][0]["unit"] == "°C"


def test_linux_yaml_endianness_only_when_non_default(tmp_path):
    dev = dict(SAMPLE_DEVICE)
    dev["registers"] = [
        {
            "address": 40001,
            "name": "x",
            "dtype": "uint16",
            "endianness": "big",
            "on_error": "skip",
            "writable": True,
        },
    ]
    LinuxEmitter().emit_driver_configs([dev], tmp_path)
    body = yaml.safe_load(
        (
            tmp_path / "drivers" / "x.yaml" if False else (tmp_path / "drivers" / "temp-1.yaml")
        ).read_text()
    )
    # Big endian is default — must NOT appear in YAML to keep it clean
    assert "endianness" not in body["registers"][0]


def test_linux_yaml_endianness_emitted_when_little(tmp_path):
    dev = dict(SAMPLE_DEVICE)  # already has endianness="little"
    LinuxEmitter().emit_driver_configs([dev], tmp_path)
    body = yaml.safe_load((tmp_path / "drivers" / "temp-1.yaml").read_text())
    assert body["registers"][0]["endianness"] == "little"


# ── manifest ─────────────────────────────────────────────────────


def test_manifest_schema(tmp_path):
    project = ProjectFiles(
        root=tmp_path,
        name="test",
        version="0.1.0",
        device_files=[],
        controller_files=[],
        model_files=[],
    )
    mem = MemoryEstimate(
        runtime_kb=0,
        devices_kb=0,
        registers_kb=0,
        controllers_kb=0,
        total_kb=0,
        ram_limit_kb=0,
        target="linux",
    )
    LinuxEmitter().emit_manifest(project, [SAMPLE_DEVICE], [], mem, "linux", tmp_path)

    body = json.loads((tmp_path / "manifest.json").read_text())
    assert body["project"]["name"] == "test"
    assert body["project"]["version"] == "0.1.0"
    assert body["target"] == "linux"
    assert len(body["devices"]) == 1
    assert body["devices"][0]["id"] == "temp-1"


def test_manifest_strips_internal_keys(tmp_path):
    project = ProjectFiles(
        root=tmp_path,
        name="t",
        version="0.1.0",
        device_files=[],
        controller_files=[],
        model_files=[],
    )
    dev_with_internals = dict(SAMPLE_DEVICE)
    dev_with_internals["class_name"] = "Temp"
    dev_with_internals["source_file"] = "/some/path/temp.py"
    mem = MemoryEstimate(
        runtime_kb=0,
        devices_kb=0,
        registers_kb=0,
        controllers_kb=0,
        total_kb=0,
        ram_limit_kb=0,
        target="linux",
    )
    LinuxEmitter().emit_manifest(project, [dev_with_internals], [], mem, "linux", tmp_path)
    body = json.loads((tmp_path / "manifest.json").read_text())
    assert "class_name" not in body["devices"][0]
    assert "source_file" not in body["devices"][0]


# ── bundle ───────────────────────────────────────────────────────


def test_bundle_contains_drivers_and_manifest(tmp_path):
    """End-to-end: compile, then peek inside the bundle."""
    # Set up a tiny project
    proj = tmp_path / "proj"
    proj.mkdir()
    (proj / "scadable.toml").write_text('name = "p"\nversion = "0.1.0"\n')
    devs_dir = proj / "devices"
    devs_dir.mkdir()
    (devs_dir / "s.py").write_text(
        "from scadable import Device, Register, modbus_tcp\n"
        "class S(Device):\n"
        "    id = 's-1'\n"
        "    connection = modbus_tcp(host='x')\n"
        "    registers = [Register(40001, 'x')]\n"
    )

    out = tmp_path / "out"
    result = compile_project(proj, target="linux", output_dir=out)
    assert not result.errors

    bundle = out / "bundle.tar.gz"
    assert bundle.exists()
    with tarfile.open(bundle) as tar:
        names = tar.getnames()
    assert "manifest.json" in names
    assert any(n.endswith("s-1.yaml") for n in names)


def test_bundle_does_not_contain_itself(tmp_path):
    """Guard: bundle.tar.gz must not contain bundle.tar.gz."""
    LinuxEmitter().emit_driver_configs([SAMPLE_DEVICE], tmp_path)
    bundle_path = LinuxEmitter().emit_bundle(tmp_path)
    with tarfile.open(bundle_path) as tar:
        names = tar.getnames()
    assert "bundle.tar.gz" not in names
