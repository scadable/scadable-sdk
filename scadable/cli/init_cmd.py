"""scadable init — create a new project."""

from pathlib import Path

import typer
from rich import print as rprint

STORAGE_DEFAULTS = {
    "linux": "256MB",
    "esp32": "2MB",
    "rtos": "64KB",
}

FLEET_TARGETS = {
    "linux": "linux-arm64",
    "esp32": "esp32",
    "rtos": "rtos-cortexm",
}


def run_init(target: str, name: str) -> None:
    if target not in ("linux", "esp32", "rtos"):
        rprint(f"[red]Unknown target '{target}'. Use: linux, esp32, rtos[/red]")
        raise typer.Exit(1)

    project_dir = Path(name)
    if project_dir.exists():
        rprint(f"[red]Directory '{name}' already exists.[/red]")
        raise typer.Exit(1)

    # Create directory structure
    (project_dir / "devices").mkdir(parents=True)
    (project_dir / "controllers").mkdir()
    (project_dir / "models").mkdir()

    # scadable.toml
    (project_dir / "scadable.toml").write_text(f"""[project]
name = "{name}"
version = "0.1.0"
sdk = "0.1.0"

[target]
default = "{FLEET_TARGETS[target]}"
supported = ["{FLEET_TARGETS[target]}"]
""")

    # fleet.toml
    (project_dir / "fleet.toml").write_text(f"""[[gateway]]
id = "gw-1"
name = "{name} Gateway"
target = "{FLEET_TARGETS[target]}"

devices = []
controllers = []

[gateway.env]
# Add environment variables here
""")

    # storage.py
    storage_size = STORAGE_DEFAULTS[target]
    (project_dir / "storage.py").write_text(f'''"""Local storage configuration."""
from scadable.storage import data, files, state

sensor_data = data("{storage_size}")
device_config = state("1MB")
''')

    # routes.py
    (project_dir / "routes.py").write_text('''"""Cloud routes — uploads and notifications."""
from scadable import upload_route, notify

# Example:
# upload_route("photos", destination="s3", bucket="${BUCKET}", ttl="30d")
# notify("ops", slack="${SLACK_URL}", severity=["critical"])
''')

    rprint(f"[green]Created {name}/[/green]")
    rprint("  [dim]├── devices/[/dim]")
    rprint("  [dim]├── controllers/[/dim]")
    rprint("  [dim]├── models/[/dim]")
    rprint("  [dim]├── storage.py[/dim]")
    rprint("  [dim]├── routes.py[/dim]")
    rprint("  [dim]├── fleet.toml[/dim]")
    rprint("  [dim]└── scadable.toml[/dim]")
    rprint()
    rprint(f"Next: [bold]cd {name}[/bold]")
    rprint("      [bold]scadable add device modbus-tcp my-sensor[/bold]")
