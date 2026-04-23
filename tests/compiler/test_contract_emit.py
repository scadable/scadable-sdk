"""Tests for the contract-crate-compatible TOML emitter + manifest drivers list.

The emitter produces `devices/{driver}.toml` in the shape the Rust
`scadable-driver-contract::DeviceConfig` crate parses. Round-tripping
through Python toml.loads is a reasonable proxy; a Rust-side
integration test in the driver crate validates the actual decode.
"""

from __future__ import annotations

import json
from pathlib import Path

import toml

from scadable.compiler import compile_project
from scadable.compiler._drivers import StagedDriver
from scadable.compiler.discover import ProjectFiles
from scadable.compiler.emitter import LinuxEmitter
from scadable.compiler.memory import MemoryEstimate

# ── per-driver TOML grouping ─────────────────────────────────────


MODBUS_TCP_DEVICE = {
    "id": "pump-1",
    "connection": {"protocol": "modbus_tcp", "host": "10.0.0.5", "port": 502, "unit_id": 1},
    "poll_ms": 1000,
    "registers": [
        {"name": "temp_c", "address": 40001, "type": "holding", "dtype": "float32"},
        {"name": "flag", "address": 40010, "type": "holding", "dtype": "bool"},
    ],
}

MODBUS_RTU_DEVICE = {
    "id": "valve-2",
    "connection": {
        "protocol": "modbus_rtu",
        "serial_port": "/dev/ttyUSB0",
        "baud": 9600,
        "unit_id": 3,
    },
    "poll_ms": 500,
    "registers": [
        {"name": "open_pct", "address": 40020, "type": "holding", "dtype": "uint16"},
    ],
}


def test_contract_toml_groups_modbus_tcp_and_rtu_into_one_file(tmp_path):
    # Both map to the `modbus` driver, so one TOML file covers both.
    written = LinuxEmitter().emit_device_configs_contract(
        [MODBUS_TCP_DEVICE, MODBUS_RTU_DEVICE], tmp_path
    )
    assert written == [tmp_path / "devices" / "modbus.toml"]


def test_contract_toml_parses_with_expected_shape(tmp_path):
    LinuxEmitter().emit_device_configs_contract([MODBUS_TCP_DEVICE], tmp_path)
    body = toml.loads((tmp_path / "devices" / "modbus.toml").read_text())

    assert len(body["device"]) == 1
    dev = body["device"][0]
    # SDK protocol modbus_tcp → contract transport tcp.
    assert dev["transport"] == "tcp"
    assert dev["id"] == "pump-1"
    assert dev["poll_ms"] == 1000
    assert dev["unit_id"] == 1
    # Connection extras flattened to device top-level — that's what
    # the contract crate's `#[serde(flatten)] extra: toml::Table`
    # picks up.
    assert dev["host"] == "10.0.0.5"
    assert dev["port"] == 502


def test_contract_toml_register_dtype_maps_sdk_to_contract(tmp_path):
    LinuxEmitter().emit_device_configs_contract([MODBUS_TCP_DEVICE], tmp_path)
    body = toml.loads((tmp_path / "devices" / "modbus.toml").read_text())
    regs = body["device"][0]["register"]
    # float32 → f32, bool stays bool.
    by_name = {r["name"]: r for r in regs}
    assert by_name["temp_c"]["dtype"] == "f32"
    assert by_name["flag"]["dtype"] == "bool"


def test_contract_toml_omits_default_fc_and_byte_order(tmp_path):
    # Holding + big-endian are the contract crate's defaults, so omit
    # them from the TOML to keep it readable. The Rust deserializer
    # fills the defaults in.
    LinuxEmitter().emit_device_configs_contract([MODBUS_TCP_DEVICE], tmp_path)
    body = toml.loads((tmp_path / "devices" / "modbus.toml").read_text())
    regs = body["device"][0]["register"]
    for r in regs:
        assert "fc" not in r  # holding is default
        assert "byte_order" not in r  # big is default


def test_contract_toml_emits_byte_order_when_non_default(tmp_path):
    dev = {
        **MODBUS_TCP_DEVICE,
        "registers": [
            {
                "name": "t",
                "address": 40001,
                "type": "holding",
                "dtype": "uint32",
                "endianness": "little",
            }
        ],
    }
    LinuxEmitter().emit_device_configs_contract([dev], tmp_path)
    body = toml.loads((tmp_path / "devices" / "modbus.toml").read_text())
    assert body["device"][0]["register"][0]["byte_order"] == "little"


def test_contract_toml_handles_coil_fc(tmp_path):
    dev = {
        **MODBUS_TCP_DEVICE,
        "registers": [{"name": "r", "address": 0, "type": "coil", "dtype": "bool"}],
    }
    LinuxEmitter().emit_device_configs_contract([dev], tmp_path)
    body = toml.loads((tmp_path / "devices" / "modbus.toml").read_text())
    assert body["device"][0]["register"][0]["fc"] == "coil"


def test_contract_toml_skips_unknown_protocols(tmp_path):
    # A future protocol that isn't in PROTOCOL_TO_DRIVER yet should
    # be silently dropped — compile still succeeds, but there's no
    # .toml for it (no driver would run anyway).
    dev = {"id": "x", "connection": {"protocol": "snmp"}, "poll_ms": 100, "registers": []}
    written = LinuxEmitter().emit_device_configs_contract([dev], tmp_path)
    assert written == []


def test_contract_toml_no_devices_emits_nothing(tmp_path):
    # Empty project — no protocol files, no TOML produced.
    written = LinuxEmitter().emit_device_configs_contract([], tmp_path)
    assert written == []


# ── manifest.drivers ─────────────────────────────────────────────


def test_manifest_drivers_empty_by_default(tmp_path):
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
    LinuxEmitter().emit_manifest(project, [], [], mem, "linux", tmp_path)
    body = json.loads((tmp_path / "manifest.json").read_text())
    assert body["drivers"] == []


def test_manifest_drivers_lists_staged_entries(tmp_path):
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
    drivers = [
        StagedDriver(
            name="modbus",
            version="0.1.0",
            arch="linux-amd64",
            sha256="a" * 64,
            relative_path="drivers/linux-amd64/driver-modbus",
        ),
        StagedDriver(
            name="modbus",
            version="0.1.0",
            arch="linux-arm64",
            sha256="b" * 64,
            relative_path="drivers/linux-arm64/driver-modbus",
        ),
    ]
    LinuxEmitter().emit_manifest(project, [], [], mem, "linux", tmp_path, drivers=drivers)
    body = json.loads((tmp_path / "manifest.json").read_text())
    assert len(body["drivers"]) == 2
    names = {d["name"] for d in body["drivers"]}
    archs = {d["arch"] for d in body["drivers"]}
    assert names == {"modbus"}
    assert archs == {"linux-amd64", "linux-arm64"}
    # sha256 propagates so the gateway can re-verify on apply.
    assert all(len(d["sha256"]) == 64 for d in body["drivers"])


# ── compile_project integration ──────────────────────────────────


def _minimal_project(tmp_path: Path, build_yml: str | None = None) -> Path:
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
    if build_yml is not None:
        (proj / ".scadable").mkdir()
        (proj / ".scadable" / "build.yml").write_text(build_yml)
    return proj


def test_compile_without_build_yml_auto_pins_from_capabilities(tmp_path):
    # Device needs `modbus` driver and build.yml has no `drivers:` block.
    # As of 2026-04-23 this falls back to the `driver_versions` mapping in
    # platform/capabilities.yaml — compile auto-pins the recommended
    # version, emits a warning telling the user it did so, and bundles
    # the binaries. Previous behaviour (no bundle, just a warning)
    # silently shipped projects that wouldn't actually run on a gateway.
    proj = _minimal_project(tmp_path)
    out = tmp_path / "out"
    result = compile_project(proj, target="linux", output_dir=out)
    assert not result.errors
    assert any("auto-pinned" in w and "modbus" in w for w in result.warnings), result.warnings
    # Drivers ARE bundled now (one per arch — linux-amd64 + linux-arm64).
    assert {d.name for d in result.drivers} == {"modbus"}
    assert {d.arch for d in result.drivers} == {"linux-amd64", "linux-arm64"}
    # Contract-format TOML still produced.
    assert (out / "devices" / "modbus.toml").exists()


def test_compile_with_build_yml_fetches_drivers(tmp_path, monkeypatch):
    # Stand up a fake CDN and verify compile_project downloads +
    # bundles the pinned driver. This is the end-to-end happy path.
    import hashlib
    from http.server import BaseHTTPRequestHandler, HTTPServer
    from threading import Thread

    from scadable.compiler import _drivers as D

    content = b"fake driver bytes"
    sha = hashlib.sha256(content).hexdigest()

    class H(BaseHTTPRequestHandler):
        def do_GET(self):  # noqa: N802
            if self.path.endswith(".sha256"):
                body = sha.encode()
            elif "driver-modbus" in self.path:
                body = content
            else:
                self.send_response(404)
                self.end_headers()
                return
            self.send_response(200)
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *a, **kw):  # quiet
            return

    srv = HTTPServer(("127.0.0.1", 0), H)
    port = srv.server_address[1]
    t = Thread(target=srv.serve_forever, daemon=True)
    t.start()
    try:
        monkeypatch.setattr(D, "CDN_BASE", f"http://127.0.0.1:{port}")
        # Narrow to one arch to keep the test fast.
        monkeypatch.setitem(D.ARCHS_FOR_TARGET, "linux", ["linux-amd64"])

        proj = _minimal_project(tmp_path, 'drivers:\n  modbus: "0.1.0"\n')
        out = tmp_path / "out"
        result = compile_project(proj, target="linux", output_dir=out)
        assert not result.errors, result.errors
        assert len(result.drivers) == 1
        s = result.drivers[0]
        assert s.name == "modbus"
        assert s.sha256 == sha
        # Binary landed in the bundle at the right path.
        assert (out / "drivers" / "linux-amd64" / "driver-modbus").read_bytes() == content
        # And the manifest records it.
        body = json.loads((out / "manifest.json").read_text())
        assert body["drivers"][0]["name"] == "modbus"
    finally:
        srv.shutdown()
        srv.server_close()
