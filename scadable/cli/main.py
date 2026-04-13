"""Scadable CLI — scaffold, validate, and compile device logic."""

import typer

app = typer.Typer(
    name="scadable",
    help="Scadable Edge SDK — write device logic in Python, compile to native.",
    no_args_is_help=True,
)


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
):
    """Validate the current project."""
    from .verify_cmd import run_verify
    run_verify(target)


@app.command()
def version():
    """Show SDK version."""
    from scadable import __version__
    typer.echo(f"scadable-sdk {__version__}")


if __name__ == "__main__":
    app()
