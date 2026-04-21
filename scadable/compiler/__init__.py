"""Scadable compiler — AST-based extraction and artifact generation.

Entry point: compile_project(project_root, target, output_dir, verbose)
"""

from __future__ import annotations

import shutil
from dataclasses import asdict
from pathlib import Path

from ._drivers import (
    DriverFetchError,
    StagedDriver,
    fetch_drivers,
    read_driver_pins,
    required_drivers,
)
from .discover import discover_project
from .emitter import EMITTERS, emit_bundle, emit_driver_configs, emit_manifest
from .memory import estimate_memory
from .parser import parse_controllers, parse_devices
from .validator import validate


class CompileResult:
    """Holds the full compilation output for CLI display."""

    __slots__ = (
        "devices",
        "controllers",
        "memory",
        "errors",
        "warnings",
        "output_dir",
        "manifest_path",
        "bundle_path",
        "drivers",
    )

    def __init__(self) -> None:
        self.devices: list[dict] = []
        self.controllers: list[dict] = []
        self.memory: dict = {}
        self.errors: list[str] = []
        self.warnings: list[str] = []
        self.output_dir: Path = Path(".")
        self.manifest_path: Path | None = None
        self.bundle_path: Path | None = None
        # Driver binaries fetched from the CDN and bundled into the
        # release. Empty list means no drivers were pinned in
        # .scadable/build.yml — matches pre-W3 behavior.
        self.drivers: list[StagedDriver] = []


def compile_project(
    project_root: Path,
    target: str = "linux",
    output_dir: Path | None = None,
    verbose: bool = False,
) -> CompileResult:
    """Compile a Scadable project into deployable artifacts.

    1. Discover project files
    2. Parse devices and controllers via AST
    3. Validate cross-references
    4. Estimate memory
    5. Fetch pinned driver binaries from the CDN (W3)
    6. Emit manifest.json + per-device YAML + per-driver TOML + bundle
    """
    result = CompileResult()
    out = output_dir or (project_root / "out")
    result.output_dir = out

    # 1. Discover
    project = discover_project(project_root)

    # 2. Parse — parsers also surface SyntaxError-skipped files as warnings
    #    so the user knows why a file didn't show up.
    devices, class_map, device_warnings = parse_devices(project.device_files)
    controllers, controller_warnings = parse_controllers(project.controller_files, class_map)

    result.devices = devices
    result.controllers = controllers

    # 3. Validate (target-aware — flags protocol/dtype mismatches)
    errors, warnings = validate(devices, controllers, class_map, target=target)
    result.errors = errors
    result.warnings = device_warnings + controller_warnings + warnings

    if errors:
        return result

    # 4. Memory estimate
    mem = estimate_memory(devices, controllers, target)
    result.memory = asdict(mem)

    # 5. Emit artifacts (per-target — esp32/rtos raise TargetNotImplementedError)
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True, exist_ok=True)

    # 5a. Driver fetch — only when build.yml has pins AND devices use
    #     driver-backed protocols. Missing pins for used protocols are
    #     a loud warning today (not an error) so pre-W3 projects keep
    #     compiling; future releases will upgrade this to an error.
    pins = read_driver_pins(project_root)
    needed = required_drivers(devices)
    if needed and pins:
        try:
            result.drivers = fetch_drivers(pins, needed, target, out)
        except DriverFetchError as e:
            result.errors.append(str(e))
            return result
    elif needed and not pins:
        result.warnings.append(
            f"devices use driver(s) {sorted(needed)} but .scadable/build.yml "
            "has no `drivers` block — binaries will not be bundled. Add e.g.:\n"
            f'    drivers:\n      {next(iter(sorted(needed)))}: "0.1.0"'
        )

    # 6. Emit manifest + per-device YAML + (linux only) per-driver TOML
    manifest_path = emit_manifest(
        project, devices, controllers, mem, target, out, drivers=result.drivers
    )
    emit_driver_configs(devices, out, target=target)
    # Contract-format configs are a Linux-emitter responsibility today;
    # esp32/rtos emitters raise at their driver-config step anyway, so
    # this call is gated the same way.
    emitter = EMITTERS[target]
    if hasattr(emitter, "emit_device_configs_contract"):
        emitter.emit_device_configs_contract(devices, out)

    bundle_path = emit_bundle(out, target=target)

    result.manifest_path = manifest_path
    result.bundle_path = bundle_path

    return result
