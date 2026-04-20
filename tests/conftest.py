"""Shared pytest fixtures for the scadable-sdk test suite."""

from __future__ import annotations

import textwrap
from collections.abc import Callable
from pathlib import Path

import pytest

EXAMPLES_DIR = Path(__file__).parent.parent / "examples"


@pytest.fixture
def examples_dir() -> Path:
    """Path to the bundled examples/ directory."""
    return EXAMPLES_DIR


@pytest.fixture
def all_example_paths() -> list[Path]:
    """Every example directory under examples/."""
    return sorted(p for p in EXAMPLES_DIR.iterdir() if p.is_dir() and (p / "devices").exists())


@pytest.fixture
def make_project(tmp_path: Path) -> Callable[..., Path]:
    """Build a minimal Scadable project under tmp_path.

    Usage:
        proj = make_project(devices={"temp.py": "..."}, controllers={"ctl.py": "..."})
    """

    def _make(
        name: str = "test-project",
        version: str = "0.1.0",
        devices: dict[str, str] | None = None,
        controllers: dict[str, str] | None = None,
        models: dict[str, str] | None = None,
    ) -> Path:
        root = tmp_path / name
        root.mkdir()
        (root / "scadable.toml").write_text(f'name = "{name}"\nversion = "{version}"\n')
        if devices:
            d = root / "devices"
            d.mkdir()
            for fname, body in devices.items():
                (d / fname).write_text(textwrap.dedent(body).lstrip())
        if controllers:
            c = root / "controllers"
            c.mkdir()
            for fname, body in controllers.items():
                (c / fname).write_text(textwrap.dedent(body).lstrip())
        if models:
            m = root / "models"
            m.mkdir()
            for fname, body in models.items():
                (m / fname).write_text(textwrap.dedent(body).lstrip())
        return root

    return _make


@pytest.fixture
def basic_modbus_device() -> str:
    """Stock Python source for a one-register Modbus TCP device."""
    return """
        from scadable import Device, Register, modbus_tcp, every, SECONDS

        class Sensor(Device):
            id = "s-1"
            name = "Test sensor"
            connection = modbus_tcp(host="1.2.3.4", port=502, slave=1)
            poll = every(5, SECONDS)
            registers = [
                Register(40001, "temperature", unit="C", scale=0.1),
            ]
    """


@pytest.fixture
def basic_controller() -> str:
    """Stock controller that runs every 5s and publishes."""
    return """
        from scadable import Controller, on, SECONDS
        from devices.sensor import Sensor

        class Mon(Controller):
            @on.interval(5, SECONDS)
            def tick(self):
                t = Sensor.temperature
                self.publish("data", {"temperature": t})
    """
