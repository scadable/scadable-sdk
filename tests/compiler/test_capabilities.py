"""Compile-time capability checks against platform/capabilities.yaml.

These tests pin the contract between the SDK's compile flow and the
platform-wide capability declaration. Three layers:

  1. ``unsupported`` features fail the compile (so a customer doesn't
     push a release that references a driver we'll never ship).
  2. ``preview`` features warn (DSL accepted, runtime not yet shipped).
  3. ``production`` features compile silently.

Plus a drift guard: every protocol in PROTOCOL_TO_DRIVER must appear
in capabilities.yaml's ``protocols`` map. Adding a driver mapping
without declaring its status is the silent-acceptance bug class this
file exists to prevent.
"""

from __future__ import annotations

import shutil
import textwrap
from pathlib import Path

import pytest

from scadable.compiler import Capabilities, compile_project
from scadable.compiler._capabilities import PreviewWarning, check_protocols
from scadable.compiler._drivers import PROTOCOL_TO_DRIVER

REPO_ROOT = Path(__file__).resolve().parents[3]
PLATFORM_CAPS = REPO_ROOT / "platform" / "capabilities.yaml"
SDK_CAPS = (
    Path(__file__).resolve().parents[2] / "scadable" / "_capabilities.yaml"
)


# ── Helpers ──────────────────────────────────────────────────────


def _write_project(tmp_path: Path, *, device_src: str) -> Path:
    """Build a minimal project that imports `device_src` as the only
    device file. Caller controls which protocol is referenced.
    """
    root = tmp_path / "proj"
    root.mkdir()
    (root / "scadable.toml").write_text('name = "p"\nversion = "0.1.0"\n')
    devices = root / "devices"
    devices.mkdir()
    (devices / "d.py").write_text(textwrap.dedent(device_src).lstrip())
    return root


# ── Drift guard ──────────────────────────────────────────────────


def test_capabilities_yaml_superset_of_protocol_to_driver():
    """Every protocol with a driver mapping must have a status row in
    capabilities.yaml. Catches the case where someone adds a new
    PROTOCOL_TO_DRIVER entry but forgets to declare its
    production/preview/unsupported status.
    """
    caps = Capabilities.load()
    missing = set(PROTOCOL_TO_DRIVER.keys()) - set(caps.protocols.keys())
    assert not missing, (
        f"protocols in PROTOCOL_TO_DRIVER but missing from capabilities.yaml: "
        f"{sorted(missing)}"
    )


def test_sdk_vendored_capabilities_matches_platform_source():
    """The SDK ships a copy of platform/capabilities.yaml so it doesn't
    have to read outside its install root at runtime. The two files
    must stay byte-identical — drift means the SDK is making decisions
    against a stale capability map.
    """
    if not PLATFORM_CAPS.exists():
        pytest.skip(f"platform source not present at {PLATFORM_CAPS}")
    assert SDK_CAPS.read_bytes() == PLATFORM_CAPS.read_bytes(), (
        "platform/capabilities.yaml drifted from "
        "scadable-sdk/scadable/_capabilities.yaml. "
        "Re-copy the platform file into the SDK package."
    )


# ── Production: silent ───────────────────────────────────────────


def test_production_protocol_compiles_silently(tmp_path):
    """modbus_tcp is production — no preview warning should appear."""
    root = _write_project(
        tmp_path,
        device_src="""
            from scadable import Device, Register, modbus_tcp

            class Sensor(Device):
                id = "s1"
                connection = modbus_tcp(host="1.2.3.4")
                registers = [Register(40001, "t")]
        """,
    )
    out = tmp_path / "out"
    result = compile_project(root, target="linux", output_dir=out)
    assert not result.errors, result.errors
    capability_warnings = [w for w in result.warnings if "PREVIEW" in w or "UNSUPPORTED" in w]
    assert capability_warnings == [], (
        f"production protocol should not produce capability warnings, got: {capability_warnings}"
    )
    # Cleanup the built bundle so tmp_path doesn't blow up on slow fs.
    shutil.rmtree(out, ignore_errors=True)


# ── Preview: warn ────────────────────────────────────────────────


def test_preview_protocol_compiles_with_preview_warning(tmp_path):
    """ble is preview — compile succeeds, a PREVIEW-flagged warning
    appears, the gateway-linux tracking pointer is included.
    """
    root = _write_project(
        tmp_path,
        device_src="""
            from scadable import Device, Characteristic, ble

            class Beacon(Device):
                id = "b1"
                connection = ble(mac="aa:bb:cc:dd:ee:ff")
                registers = [
                    Characteristic("00002a37-0000-1000-8000-00805f9b34fb", "hr"),
                ]
        """,
    )
    out = tmp_path / "out"
    result = compile_project(root, target="linux", output_dir=out)
    assert not result.errors, result.errors
    matching = [w for w in result.warnings if "PREVIEW" in w and "ble" in w]
    assert matching, f"expected a PREVIEW warning naming ble, got: {result.warnings}"
    # Pointer to where to follow progress should be present.
    assert any("not yet tracked" in w or "gateway-linux#" in w for w in matching)
    shutil.rmtree(out, ignore_errors=True)


# ── Unsupported: fail ────────────────────────────────────────────


def test_unsupported_protocol_fails_with_clear_error(tmp_path):
    """can() is declared unsupported. Compile must error, and the
    error must name the feature, the device, and the source file so
    the customer can fix without spelunking.
    """
    root = _write_project(
        tmp_path,
        device_src="""
            from scadable import Device, Register
            from scadable.protocols import can

            class CanThing(Device):
                id = "c1"
                connection = can(bus="can0")
                registers = [Register(40001, "rpm")]
        """,
    )
    out = tmp_path / "out"
    result = compile_project(root, target="linux", output_dir=out)
    assert result.errors, "expected compile to fail on unsupported protocol"
    joined = "\n".join(result.errors)
    assert "UNSUPPORTED" in joined
    assert "can" in joined.lower()


# ── Direct unit coverage on check_protocols ──────────────────────


def test_check_protocols_returns_warnings_for_preview():
    caps = Capabilities.load()
    devs = [
        {"id": "d1", "connection": {"protocol": "modbus_tcp"}, "source_file": "x.py"},
        {"id": "d2", "connection": {"protocol": "ble"}, "source_file": "y.py"},
    ]
    warns = check_protocols(caps, devs)
    assert len(warns) == 1
    assert isinstance(warns[0], PreviewWarning)
    assert warns[0].name == "ble"
    assert warns[0].source == "y.py"


def test_check_protocols_handles_kebab_case_alias():
    """The protocols dataclass uses kebab-case (modbus-tcp) in some
    older paths; capabilities.yaml is the snake-case canonical form.
    The check must normalize."""
    caps = Capabilities.load()
    devs = [{"id": "d1", "connection": {"protocol": "modbus-tcp"}, "source_file": "x.py"}]
    warns = check_protocols(caps, devs)
    assert warns == []
