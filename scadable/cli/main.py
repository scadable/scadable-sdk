"""Scadable CLI — scaffold, validate, and compile device logic."""

import typer

from .sim_cmd import sim_app

app = typer.Typer(
    name="scadable",
    help="Scadable Edge SDK — write device logic in Python, compile to native.",
    no_args_is_help=True,
)
app.add_typer(sim_app, name="sim")


@app.command()
def init(
    target: str = typer.Argument(help="Target platform: linux, esp32, rtos"),
    name: str = typer.Argument(help="Project name"),
):
    """Create a new Scadable project."""
    from .init_cmd import run_init

    run_init(target, name)


@app.command()
def add(
    kind: str = typer.Argument(help="What to add: device, controller, model"),
    protocol_or_name: str = typer.Argument(help="Protocol (for device) or name"),
    name: str = typer.Argument(default="", help="Name (for device)"),
):
    """Add a device, controller, or model to the project."""
    from .add_cmd import run_add

    run_add(kind, protocol_or_name, name)


@app.command()
def verify(
    target: str = typer.Option("", help="Target platform for memory estimation"),
    json_output: bool = typer.Option(
        False,
        "--json",
        help="Emit a single JSON object on stdout instead of human-readable output.",
    ),
):
    """Validate the current project."""
    from .verify_cmd import run_verify

    run_verify(target, json_output=json_output)


@app.command()
def compile(
    target: str = typer.Option("linux", help="Target platform: linux, esp32"),
    output: str = typer.Option("out", help="Output directory"),
    verbose: bool = typer.Option(False, "-v", help="Verbose output"),
):
    """Compile device definitions into gateway-deployable artifacts."""
    from .compile_cmd import run_compile

    run_compile(target=target, output=output, verbose=verbose)


@app.command()
def version():
    """Show SDK version."""
    from scadable import __version__

    typer.echo(f"scadable-sdk {__version__}")


if __name__ == "__main__":
    app()
