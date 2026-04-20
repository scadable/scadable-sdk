"""Examples: every bundled example must compile cleanly on linux."""

from __future__ import annotations

from pathlib import Path

import pytest

from scadable.compiler import compile_project

EXAMPLES_DIR = Path(__file__).parent.parent.parent / "examples"


def _example_dirs() -> list[Path]:
    return sorted(p for p in EXAMPLES_DIR.iterdir() if p.is_dir() and (p / "devices").exists())


@pytest.mark.parametrize("example", _example_dirs(), ids=lambda p: p.name)
def test_example_compiles_clean_on_linux(example, tmp_path):
    """Compile every example for target=linux. Errors fail the test;
    warnings are logged but allowed (e.g. modbus_tcp w/o explicit host
    on examples that use env var placeholders)."""
    result = compile_project(example, target="linux", output_dir=tmp_path / example.name)
    assert result.errors == [], f"{example.name} errors: {result.errors}"


@pytest.mark.parametrize("example", _example_dirs(), ids=lambda p: p.name)
def test_example_emits_yaml_drivers(example, tmp_path):
    """Every example with at least one device must produce drivers/*.yaml."""
    out = tmp_path / example.name
    result = compile_project(example, target="linux", output_dir=out)
    if not result.devices:
        pytest.skip(f"{example.name} has no devices")
    yamls = list((out / "drivers").glob("*.yaml"))
    assert len(yamls) >= 1


@pytest.mark.parametrize("example", _example_dirs(), ids=lambda p: p.name)
def test_example_emits_manifest(example, tmp_path):
    out = tmp_path / example.name
    compile_project(example, target="linux", output_dir=out)
    assert (out / "manifest.json").exists()
