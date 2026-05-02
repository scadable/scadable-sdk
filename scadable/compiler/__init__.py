"""Scadable compiler — AST-based extraction and artifact generation.

Entry point: compile_project(project_root, target, output_dir, verbose)
"""

from __future__ import annotations

import shutil
from dataclasses import asdict
from pathlib import Path

from ._capabilities import (
    Capabilities,
    CapabilityError,
    PreviewWarning,
    check_controllers,
    check_protocols,
    check_storage_imports,
)
from ._drivers import (
    PROTOCOL_TO_DRIVER,
    DriverFetchError,
    StagedDriver,
    fetch_drivers,
    read_driver_pins,
)
from .discover import discover_project
from .emitter import EMITTERS, emit_bundle, emit_driver_configs, emit_manifest
from .emitter.esp32 import Esp32UnsupportedError
from .memory import estimate_memory
from .parser import parse_controllers, parse_devices
from .validator import validate


def _production_drivers(devices: list[dict], capabilities: Capabilities) -> set[str]:
    """Subset of drivers needed by the project that the platform actually
    ships binaries for (i.e. their protocol is `production`). Preview/
    unsupported protocols don't bundle drivers — the user already saw
    a PreviewWarning at the capability check step, and forcing a driver
    fetch would error out before the rest of the bundle gets a chance
    to land.
    """
    needed: set[str] = set()
    for dev in devices:
        proto = (dev.get("connection") or {}).get("protocol")
        if not proto:
            continue
        driver = PROTOCOL_TO_DRIVER.get(proto)
        if not driver:
            continue
        if capabilities.protocols.get(proto) != "production":
            continue
        needed.add(driver)
    return needed


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

    # 3a. Capability check — protocol/storage/controller status against
    #     platform/capabilities.yaml (vendored as scadable/_capabilities.yaml).
    #     unsupported = hard error, preview = warning, production = silent.
    #     Run BEFORE the early-return on validate() errors so users see
    #     all relevant feedback in one pass when both kinds of issue
    #     show up together.
    try:
        capabilities = Capabilities.load()
        preview_warnings: list[PreviewWarning] = []
        preview_warnings.extend(check_protocols(capabilities, devices))
        preview_warnings.extend(check_storage_imports(capabilities, project_root))
        preview_warnings.extend(check_controllers(capabilities, controllers))
        result.warnings.extend(w.format() for w in preview_warnings)
    except CapabilityError as e:
        result.errors.append(str(e))

    if result.errors:
        return result

    # 4. Memory estimate
    mem = estimate_memory(devices, controllers, target)
    result.memory = asdict(mem)

    # 5. Emit artifacts (per-target — esp32/rtos raise TargetNotImplementedError)
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True, exist_ok=True)

    # 5a. Driver fetch.
    #
    # As of 2026-04-23, missing pins fall back to the
    # ``capabilities.driver_versions`` defaults (set in
    # platform/capabilities.yaml) instead of warning-and-skipping. The
    # warn-and-skip behaviour produced bundles without drivers and led
    # to gateways running stale drivers (or no driver) silently — the
    # exact failure mode that bricked customer-zero on the dev Pi when
    # the modbus wire format changed and no compile shipped 0.2.0.
    #
    # Drivers for preview/unsupported protocols are intentionally
    # excluded from `needed` — those protocols don't ship binaries by
    # design and the user already saw a PreviewWarning at step 3a.
    # Including them here would force the compile to error out before
    # we even get a chance to emit a bundle the user can inspect.
    pins = read_driver_pins(project_root)
    needed = _production_drivers(devices, capabilities)
    if needed:
        try:
            auto_pinned: list[str] = []
            result.drivers = fetch_drivers(
                pins,
                needed,
                target,
                out,
                default_versions=capabilities.driver_versions,
                auto_pinned_warnings=auto_pinned,
            )
            result.warnings.extend(auto_pinned)
        except DriverFetchError as e:
            result.errors.append(str(e))
            return result

    # 6. Emit manifest + per-device YAML + (linux only) per-driver TOML.
    # The ESP32 emitter raises Esp32UnsupportedError when a controller
    # uses a feature outside the @on.interval + self.publish allowlist;
    # surface that as a CompileResult error string so users see the
    # file:line + reason instead of a Python traceback. Other emitters
    # don't raise this; the catch is a no-op for them.
    try:
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
    except Esp32UnsupportedError as e:
        result.errors.append(str(e))
        return result

    result.manifest_path = manifest_path
    result.bundle_path = bundle_path

    return result
