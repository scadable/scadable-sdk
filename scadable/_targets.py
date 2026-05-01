"""Target capability matrix — single source of truth.

When the user picks a target (linux/esp32/rtos), the validator reads
this matrix and flags compile-time errors for unsupported protocols,
unsupported dtypes, or memory budgets that won't fit. This is the
early-warning system that prevents customers from writing code that
"compiles" on Linux but silently won't fit on a smaller target.

v0.2.0 only ships `linux` as production-supported. `esp32` and `rtos`
entries reserve the shape and capability info so the validator can
already flag obvious mistakes (e.g. "you used dtype=float64 on RTOS"),
but compilation for those targets raises NotImplementedError until
their emitters land.
"""

from __future__ import annotations

from typing import TypedDict


class TargetSpec(TypedDict):
    memory_kb: int | None  # None = unbounded
    protocols: frozenset[str]
    dtypes: frozenset[str]
    controller_execution: str
    status: str  # "production" | "connection_only" | "preview" | "not-implemented"
    # connection_only: gateway runtime ships and connects to cloud (presence + logs +
    # metrics); SDK project bundles for this target are NOT compiled yet. The dashboard
    # surfaces gateways at this status as "connected, no project bundle support" so
    # operators can verify the device is online and see its log stream while the
    # per-target compiler emitter is still in flight.


TARGETS: dict[str, TargetSpec] = {
    "linux": {
        "memory_kb": None,
        "protocols": frozenset(
            {
                "modbus_tcp",
                "modbus_rtu",
                "ble",
                "gpio",
                "serial",
                "i2c",
                "rtsp",
            }
        ),
        "dtypes": frozenset(
            {
                "uint16",
                "int16",
                "uint32",
                "int32",
                "float32",
                "float64",
                "bool",
            }
        ),
        "controller_execution": "python_subprocess",
        "status": "production",
    },
    "esp32": {
        "memory_kb": 520,
        "protocols": frozenset(
            {
                "modbus_rtu",
                "i2c",
                "spi",
                "gpio",
            }
        ),
        "dtypes": frozenset(
            {
                "uint16",
                "int16",
                "uint32",
                "int32",
                "float32",
                "bool",
            }
        ),
        "controller_execution": "micropython_or_codegen",
        # Bumped from "preview" 2026-05-01: the gateway-esp MVP ships a runtime
        # that connects, enrolls via EST, and streams logs into the dashboard.
        # The SDK project-bundle compile path for this target is still pending
        # (compile_cmd.py raises NotImplementedError); validator behaviour is
        # unchanged. See plan: ../../../.claude/plans/partitioned-enchanting-lighthouse.md
        "status": "connection_only",
    },
    "rtos": {
        "memory_kb": 256,
        "protocols": frozenset(
            {
                "modbus_rtu",
                "gpio",
                "can",
            }
        ),
        "dtypes": frozenset(
            {
                "uint16",
                "int16",
                "bool",
            }
        ),
        "controller_execution": "codegen",
        "status": "preview",
    },
}


def get_target(name: str) -> TargetSpec:
    """Look up a target by name. Raises ValueError on unknown."""
    if name not in TARGETS:
        raise ValueError(f"unknown target {name!r}. Known: {', '.join(sorted(TARGETS))}")
    return TARGETS[name]


def is_supported_protocol(target: str, protocol: str) -> bool:
    """True if `protocol` is in `target`'s supported protocol set."""
    return protocol in get_target(target)["protocols"]


def is_supported_dtype(target: str, dtype: str) -> bool:
    """True if `dtype` is in `target`'s supported dtype set."""
    return dtype in get_target(target)["dtypes"]


class TargetNotImplementedError(NotImplementedError):
    """Raised when compile is requested for a target whose emitter
    isn't shipped yet. Carries the target name + planned version
    so users see a concrete "wait for v0.X" message rather than a
    generic NotImplementedError.
    """
