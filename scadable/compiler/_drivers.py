"""Driver fetcher — pulls per-arch driver binaries from the CDN at
compile time and stages them into the bundle so the gateway just
unpacks and runs.

Why CDN-fetch at compile time (instead of bundling at SDK release
time, or letting the gateway pull drivers on its own):
  - SDK + driver evolve independently. A driver-modbus 0.1.0 → 0.1.1
    fix doesn't force an SDK rebuild + republish.
  - Gateway pulls one bundle, gets everything. No second hop, no
    "what if the gateway has stale drivers" reconciliation problem.
  - Compile-time pin in `.scadable/build.yml` makes the running
    driver version auditable from the user's git history.

Bundle layout this module fills in:
    bundle/drivers/<arch>/driver-<name>          (binary)
    bundle/drivers/<arch>/driver-<name>.sha256   (hex digest sidecar)

The gateway-side applier (W4) symlinks
    /etc/scadable/drivers/  ->  bundle/drivers/<native_arch>/
on apply, so each driver subprocess sees its binary at the same path
regardless of gateway architecture.
"""

from __future__ import annotations

import hashlib
import os
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path

import yaml

# --------------------------------------------------------------------
# CDN base + arch matrix
# --------------------------------------------------------------------
#
# The CDN publishes each driver under a stable layout; this module is
# the single place that knows the URL pattern. Per W2.5 (the driver
# CD pipeline), each tagged release writes:
#
#   drivers/<name>/<version>/<arch>/driver-<name>
#   drivers/<name>/<version>/<arch>/driver-<name>.sha256
#
# `linux` projects compile against all three archs because we don't
# know ahead of time which gateways will subscribe — bundling all
# linux archs adds ~9MB but keeps the apply path arch-agnostic.

CDN_BASE = os.environ.get(
    "SCADABLE_DRIVER_CDN",
    "https://scadable-cdn.tor1.digitaloceanspaces.com",
)

# arch tuples per project target. esp and rtos are stubbed out — they
# raise TargetNotImplementedError further upstream, so this just
# records the eventual mapping for clarity.
ARCHS_FOR_TARGET: dict[str, list[str]] = {
    # linux-armv7 is intentionally absent until both the gateway and
    # every driver ship for that target — fetching a missing arch from
    # the CDN would 404 and fail the compile. Add it back when
    # gateway-linux's release.yml + cd-driver-*.yml workflows include
    # armv7-unknown-linux-musleabihf.
    "linux": ["linux-amd64", "linux-arm64"],
    "esp32": ["esp32"],
    "rtos": ["rtos-cortex-m4"],
}

# Protocol declared by the user → driver binary that handles it.
# Modbus TCP and RTU share one driver; Bluetooth covers BLE + classic;
# etc. Adding a new driver: add the protocol(s) here + spin up its
# repo. Nothing in the SDK or gateway changes.
PROTOCOL_TO_DRIVER: dict[str, str] = {
    "modbus_tcp": "modbus",
    "modbus_rtu": "modbus",
    "ble": "bluetooth",
    "gpio": "gpio",
    "i2c": "i2c",
    "spi": "spi",
    "can": "can",
    "rtsp": "rtsp",
    "serial": "serial",
}


# --------------------------------------------------------------------
# Errors
# --------------------------------------------------------------------


class DriverFetchError(RuntimeError):
    """Raised when a driver binary can't be fetched, downloaded, or
    verified. The compile pipeline catches this, prints the message,
    and surfaces it as a build failure rather than an exception
    traceback.
    """


# --------------------------------------------------------------------
# Public surface
# --------------------------------------------------------------------


@dataclass(frozen=True)
class DriverPin:
    """One entry from .scadable/build.yml's `drivers` block."""

    name: str
    version: str


@dataclass(frozen=True)
class StagedDriver:
    """One arch-specific driver binary already written into the bundle.
    Returned so the manifest emitter can list it for traceability.
    """

    name: str
    version: str
    arch: str
    sha256: str
    relative_path: str  # path inside the bundle, forward-slashed


def read_driver_pins(project_root: Path) -> list[DriverPin]:
    """Read `.scadable/build.yml` and return the declared driver
    versions. Empty list if the file or the `drivers` block is
    missing — matches the v0.2.0 pre-driver behavior so existing
    projects keep building until they opt into telemetry.
    """
    build_yml = project_root / ".scadable" / "build.yml"
    if not build_yml.exists():
        return []
    body = yaml.safe_load(build_yml.read_text()) or {}
    raw = body.get("drivers") or {}
    if not isinstance(raw, dict):
        raise DriverFetchError(
            "drivers in .scadable/build.yml must be a mapping of name → version, "
            f"got {type(raw).__name__}"
        )
    return [DriverPin(name=str(k), version=str(v)) for k, v in raw.items()]


def required_drivers(devices: list[dict]) -> set[str]:
    """Map a parsed device list to the set of driver names they need.
    A project with both modbus_tcp and modbus_rtu devices needs the
    `modbus` driver once.
    """
    names: set[str] = set()
    for dev in devices:
        proto = (dev.get("connection") or {}).get("protocol")
        if not proto:
            continue
        driver = PROTOCOL_TO_DRIVER.get(proto)
        if driver:
            names.add(driver)
    return names


def fetch_drivers(
    pins: list[DriverPin],
    needed: set[str],
    target: str,
    output_dir: Path,
    *,
    default_versions: dict[str, str] | None = None,
    auto_pinned_warnings: list[str] | None = None,
) -> list[StagedDriver]:
    """Download each declared+needed driver for every arch the target
    runs on, verify sha256, stage into output_dir/drivers/<arch>/.

    A pin is silently ignored if no device on this project uses it
    (saves bandwidth on projects that pin extra drivers).

    For a needed driver with no pin: the previous behaviour was to hard-
    error and force the user to add a pin to ``.scadable/build.yml``. As
    of 2026-04-23, callers may pass ``default_versions`` (typically the
    ``Capabilities.driver_versions`` mapping from the platform-wide
    ``capabilities.yaml``); a needed driver without a pin falls back to
    this mapping with a warning appended to ``auto_pinned_warnings``.
    Only when BOTH the pin and the default are missing does this raise —
    that's a real "we don't ship a driver for this protocol" condition,
    not a missing-pin paperwork error. Driven by the customer-zero
    incident where every fresh project compile failed because the
    template didn't pre-pin driver-modbus and the customer had no way
    to know which version to write.
    """
    if target not in ARCHS_FOR_TARGET:
        raise DriverFetchError(f"no arch matrix for target {target!r}")

    pins_by_name = {p.name: p for p in pins}
    defaults = default_versions or {}

    missing = needed - pins_by_name.keys()
    truly_missing: set[str] = set()
    for name in missing:
        if name in defaults:
            pins_by_name[name] = DriverPin(name=name, version=defaults[name])
            if auto_pinned_warnings is not None:
                auto_pinned_warnings.append(
                    f"driver {name!r} not pinned in .scadable/build.yml — "
                    f"auto-pinned to {defaults[name]!r} from platform capabilities. "
                    f"Add an explicit pin if you need to lock to a different version."
                )
        else:
            truly_missing.add(name)

    if truly_missing:
        raise DriverFetchError(
            f"devices use driver(s) {sorted(truly_missing)!r} but no version is "
            f"pinned in .scadable/build.yml AND no default version is declared "
            f"in platform/capabilities.yaml. Add e.g.\n"
            f"    drivers:\n"
            f'      {next(iter(sorted(truly_missing)))}: "0.1.0"'
        )

    archs = ARCHS_FOR_TARGET[target]
    staged: list[StagedDriver] = []
    for name in sorted(needed):
        pin = pins_by_name[name]
        for arch in archs:
            staged.append(_fetch_one(pin, arch, output_dir))
    return staged


# --------------------------------------------------------------------
# Internals
# --------------------------------------------------------------------


def _fetch_one(pin: DriverPin, arch: str, output_dir: Path) -> StagedDriver:
    base = f"{CDN_BASE}/drivers/{pin.name}/{pin.version}/{arch}"
    bin_url = f"{base}/driver-{pin.name}"
    sha_url = f"{bin_url}.sha256"

    # Sidecar first — if it 404s, the binary wasn't published for this
    # arch and we abort BEFORE downloading megabytes of binary that
    # wouldn't be safe to use anyway.
    try:
        expected_sha = _http_get_text(sha_url).strip()
    except urllib.error.HTTPError as e:
        raise DriverFetchError(
            f"driver {pin.name}@{pin.version} for {arch} not found on CDN "
            f"({sha_url} returned HTTP {e.code}). "
            f"Either the driver hasn't been built for {arch} or the version is wrong."
        ) from e
    except urllib.error.URLError as e:
        raise DriverFetchError(f"could not reach CDN at {sha_url}: {e}") from e

    if not _looks_like_sha256_hex(expected_sha):
        raise DriverFetchError(
            f"sidecar at {sha_url} is not a valid sha256 hex digest (got {expected_sha!r:.80s})"
        )

    binary_bytes = _http_get_bytes(bin_url)
    actual_sha = hashlib.sha256(binary_bytes).hexdigest()
    if actual_sha != expected_sha:
        raise DriverFetchError(
            f"sha256 mismatch for {pin.name}@{pin.version} {arch}:\n"
            f"  CDN sidecar : {expected_sha}\n"
            f"  computed    : {actual_sha}\n"
            f"Refusing to bundle a driver whose CDN object doesn't match its sidecar."
        )

    arch_dir = output_dir / "drivers" / arch
    arch_dir.mkdir(parents=True, exist_ok=True)
    bin_path = arch_dir / f"driver-{pin.name}"
    bin_path.write_bytes(binary_bytes)
    bin_path.chmod(0o755)
    # Sidecar in the bundle too — the gateway can re-verify on apply
    # without trusting the bundle's own integrity check alone.
    (arch_dir / f"driver-{pin.name}.sha256").write_text(expected_sha)

    return StagedDriver(
        name=pin.name,
        version=pin.version,
        arch=arch,
        sha256=expected_sha,
        relative_path=f"drivers/{arch}/driver-{pin.name}",
    )


def _http_get_text(url: str, timeout: float = 30.0) -> str:
    with urllib.request.urlopen(url, timeout=timeout) as r:  # noqa: S310
        return r.read().decode("utf-8")


def _http_get_bytes(url: str, timeout: float = 60.0) -> bytes:
    with urllib.request.urlopen(url, timeout=timeout) as r:  # noqa: S310
        return r.read()


def _looks_like_sha256_hex(s: str) -> bool:
    return len(s) == 64 and all(c in "0123456789abcdef" for c in s.lower())
