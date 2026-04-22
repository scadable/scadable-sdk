"""pymodbus-backed Modbus TCP simulator.

Goal: let the smoke test (and curious developers) exercise the full
``driver-modbus → MQTT → cloud → dashboard`` pipeline without a real PLC.
Defaults to ``127.0.0.1:1502`` so it can run alongside a real broker on
``:502`` without root and without a port collision.

The register map is loaded from a YAML file shaped like::

    host: 127.0.0.1
    port: 1502
    slave: 1
    registers:
      - addr: 40001
        type: holding   # holding | input | coil | discrete
        initial: 250    # initial value (units depend on the register)
        drift_per_sec: 0.1   # optional — slowly walks the value so charts move

Each register with a non-zero ``drift_per_sec`` gets its own
``asyncio`` task that pushes a fresh value into the underlying SimDevice
at 10 Hz via the server's ``async_setValues`` API.

The sim prints a single ``modbus-sim listening on host:port`` line on
startup and is otherwise quiet — keeps test logs readable.

CLI entry point::

    python -m scadable.sim.modbus_sim --config sim.yaml [--host H] [--port P]

The ``scadable sim modbus`` Typer subcommand wraps this module.
"""

from __future__ import annotations

import argparse
import asyncio
import contextlib
import signal
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

# pymodbus is in the [sim] optional-dependencies group. Importing at
# module top-level is intentional — if the user is invoking the sim,
# they need pymodbus installed; surface a clear error if not.
try:
    from pymodbus.server import ModbusTcpServer
    from pymodbus.simulator import DataType, SimData, SimDevice
except ImportError as exc:  # pragma: no cover - import guard for clarity
    raise SystemExit(
        "scadable.sim.modbus_sim requires pymodbus. "
        "Install with: pip install 'scadable-sdk[sim]'"
    ) from exc


# ── Config ────────────────────────────────────────────────────────────


_VALID_TYPES = {"holding", "input", "coil", "discrete"}

# Modbus function codes the gateway driver actually issues. We match
# pymodbus' convention so async_setValues() can be called directly.
#  - 1: read coils                 (we update via fc=5/15 territory; setValues uses 1)
#  - 2: read discrete inputs
#  - 3: read holding registers
#  - 4: read input registers
_FC_FOR_TYPE = {"coil": 1, "discrete": 2, "holding": 3, "input": 4}


@dataclass
class RegisterCfg:
    addr: int
    type: str = "holding"
    initial: float = 0.0
    drift_per_sec: float = 0.0


@dataclass
class SimConfig:
    host: str = "127.0.0.1"
    port: int = 1502
    slave: int = 1
    registers: list[RegisterCfg] = field(default_factory=list)


def _normalize_addr(addr: int, kind: str) -> int:
    """Translate Modbus user-facing addresses (4xxxx/3xxxx/0xxxx/1xxxx)
    into 0-based offsets the wire protocol uses.

    The YAML is allowed to use either form (e.g. ``40001`` or ``0`` for
    the first holding register) because the SDK's existing
    ``Register(40001, ...)`` API uses the 4xxxx notation. We strip the
    convention digit when present so the sim and the driver agree on
    what each address means.
    """
    if kind == "holding" and 40001 <= addr <= 49999:
        return addr - 40001
    if kind == "input" and 30001 <= addr <= 39999:
        return addr - 30001
    if kind == "coil" and 1 <= addr <= 9999:
        return addr - 1
    if kind == "discrete" and 10001 <= addr <= 19999:
        return addr - 10001
    return addr


def load_config(path: str | Path) -> SimConfig:
    raw: dict[str, Any] = yaml.safe_load(Path(path).read_text()) or {}
    regs_raw = raw.get("registers", []) or []
    regs: list[RegisterCfg] = []
    for r in regs_raw:
        kind = str(r.get("type", "holding")).lower()
        if kind not in _VALID_TYPES:
            raise ValueError(
                f"register {r!r}: type must be one of {sorted(_VALID_TYPES)}"
            )
        regs.append(
            RegisterCfg(
                addr=int(r["addr"]),
                type=kind,
                initial=float(r.get("initial", 0)),
                drift_per_sec=float(r.get("drift_per_sec", 0)),
            )
        )
    return SimConfig(
        host=str(raw.get("host", "127.0.0.1")),
        port=int(raw.get("port", 1502)),
        slave=int(raw.get("slave", 1)),
        registers=regs,
    )


# ── Datastore + drift tasks ───────────────────────────────────────────


def _clamp_int(v: float) -> int:
    """Coerce a (possibly negative, possibly fractional) value to a
    valid 16-bit Modbus register word. Wraps signed → unsigned to match
    how Modbus drivers reinterpret the bytes downstream."""
    iv = int(round(v))
    if iv < 0:
        iv = (iv + 65536) % 65536
    return iv & 0xFFFF


def _build_device(cfg: SimConfig) -> SimDevice:
    """Build the SimDevice with one wide block per register kind.

    Pymodbus' SimDevice rejects overlapping blocks and refuses reads
    outside the declared range, so we pre-allocate a 1024-register span
    per kind starting at offset 0. Specific addresses are seeded with
    their YAML ``initial`` values; everything else stays at zero.
    """
    span = 1024  # Plenty for our smoke tests; bump if a real config grows.

    # One default-zero block per kind. Per-register overrides are layered
    # on top with non-overlapping addresses (sorted by SimDevice).
    coil_block: list[SimData] = [
        SimData(0, count=span, values=False, datatype=DataType.BITS),
    ]
    discrete_block: list[SimData] = [
        SimData(0, count=span, values=False, datatype=DataType.BITS),
    ]
    holding_block: list[SimData] = [
        SimData(0, count=span, values=0, datatype=DataType.REGISTERS),
    ]
    input_block: list[SimData] = [
        SimData(0, count=span, values=0, datatype=DataType.REGISTERS),
    ]

    # SimData blocks must not overlap. The wide default block already
    # covers every offset, so we keep just the wide block and seed the
    # initial values via the server's async_setValues at startup
    # (handled in `run()` below).
    return SimDevice(
        id=cfg.slave,
        simdata=(coil_block, discrete_block, holding_block, input_block),
    )


async def _drift_task(
    server: ModbusTcpServer,
    state: dict[tuple[str, int], float],
    reg: RegisterCfg,
    slave: int,
) -> None:
    """One task per drifting register. Runs at 10 Hz so chart updates
    look smooth without flooding the datastore."""
    if reg.drift_per_sec == 0:
        return
    offset = _normalize_addr(reg.addr, reg.type)
    fc = _FC_FOR_TYPE[reg.type]
    tick = 0.1
    step = reg.drift_per_sec * tick
    while True:
        await asyncio.sleep(tick)
        state[(reg.type, offset)] += step
        v = state[(reg.type, offset)]
        if reg.type in ("holding", "input"):
            values: list[int] | list[bool] = [_clamp_int(v)]
        else:
            values = [bool(round(v))]
        with contextlib.suppress(Exception):
            await server.async_setValues(slave, fc, offset, values)


# ── Server lifecycle ──────────────────────────────────────────────────


async def run(cfg: SimConfig) -> None:
    """Start the server and keep it running until cancelled.

    Caller installs signal handlers — the CLI wrapper does this;
    programmatic callers should wrap the coroutine in their own
    ``asyncio.Task`` and cancel it.
    """
    device = _build_device(cfg)
    server = ModbusTcpServer(device, address=(cfg.host, cfg.port))

    # Push initial values for every declared register. Done after the
    # server is constructed (so the SimCore exists) but before
    # serve_forever() — first reads see the YAML-declared values.
    state: dict[tuple[str, int], float] = {}
    for r in cfg.registers:
        offset = _normalize_addr(r.addr, r.type)
        fc = _FC_FOR_TYPE[r.type]
        state[(r.type, offset)] = r.initial
        if r.type in ("holding", "input"):
            seed: list[int] | list[bool] = [_clamp_int(r.initial)]
        else:
            seed = [bool(round(r.initial))]
        with contextlib.suppress(Exception):
            await server.async_setValues(cfg.slave, fc, offset, seed)

    drift_tasks = [
        asyncio.create_task(_drift_task(server, state, r, cfg.slave), name=f"drift-{r.addr}")
        for r in cfg.registers
        if r.drift_per_sec
    ]

    # Print exactly one line so the smoke test (and humans) can confirm
    # the sim is up. Then go silent.
    print(f"modbus-sim listening on {cfg.host}:{cfg.port}", flush=True)

    try:
        await server.serve_forever()
    finally:
        for t in drift_tasks:
            t.cancel()
        for t in drift_tasks:
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await t
        with contextlib.suppress(Exception):
            await server.shutdown()


# ── CLI ───────────────────────────────────────────────────────────────


def _build_argparser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="scadable-modbus-sim",
        description="Modbus TCP simulator for end-to-end pipeline testing.",
    )
    p.add_argument("--config", type=Path, help="Path to YAML register-map config.")
    p.add_argument("--host", help="Override host from config (default 127.0.0.1).")
    p.add_argument("--port", type=int, help="Override port from config (default 1502).")
    return p


def main(argv: list[str] | None = None) -> int:
    args = _build_argparser().parse_args(argv)

    cfg = load_config(args.config) if args.config else SimConfig()

    if args.host:
        cfg.host = args.host
    if args.port:
        cfg.port = args.port

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    main_task = loop.create_task(run(cfg))

    def _cancel(*_: Any) -> None:
        main_task.cancel()

    # SIGINT/SIGTERM both cancel cleanly. add_signal_handler isn't
    # supported on Windows, but the gateway+CI targets are POSIX.
    for sig in (signal.SIGINT, signal.SIGTERM):
        with contextlib.suppress(NotImplementedError):
            loop.add_signal_handler(sig, _cancel)

    try:
        loop.run_until_complete(main_task)
    except asyncio.CancelledError:
        pass
    finally:
        loop.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
