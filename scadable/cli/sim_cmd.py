"""``scadable sim`` Typer subcommand group.

Today only one sim ships: ``scadable sim modbus``. Future sims (BLE,
OPC-UA, …) plug in the same way — add another ``@sim_app.command()``
that delegates to a module under ``scadable/sim/``.
"""

from __future__ import annotations

from pathlib import Path

import typer

sim_app = typer.Typer(
    name="sim",
    help="Run protocol simulators (for testing without real hardware).",
    no_args_is_help=True,
)


@sim_app.command("modbus")
def modbus(
    config: Path | None = typer.Option(
        None,
        "--config",
        "-c",
        help="YAML register-map config. Omit for an empty server on 127.0.0.1:1502.",
        exists=False,
    ),
    host: str | None = typer.Option(None, "--host", help="Override host from config."),
    port: int | None = typer.Option(None, "--port", help="Override port from config."),
) -> None:
    """Start a Modbus TCP simulator (pymodbus-backed).

    Requires the ``[sim]`` extra: ``pip install 'scadable-sdk[sim]'``.
    """
    # Lazy-import so ``scadable --help`` doesn't blow up when pymodbus
    # isn't installed.
    from scadable.sim.modbus_sim import main as sim_main

    argv: list[str] = []
    if config is not None:
        argv += ["--config", str(config)]
    if host is not None:
        argv += ["--host", host]
    if port is not None:
        argv += ["--port", str(port)]
    raise typer.Exit(sim_main(argv))
