"""scadable verify — validate a project without compiling."""

import ast
from pathlib import Path

import typer
from rich import print as rprint


def run_verify(target: str = "") -> None:
    errors: list[str] = []
    warnings: list[str] = []

    # 1. Check project structure
    rprint("\n[bold]── Checking project structure ────────────[/bold]")
    has_manifest = Path("scadable.toml").exists()
    has_fleet = Path("fleet.toml").exists()
    has_devices = Path("devices").is_dir()
    has_controllers = Path("controllers").is_dir()

    _check(has_manifest, "scadable.toml found", "scadable.toml missing", errors)
    _check(has_fleet, "fleet.toml found", "fleet.toml missing (optional)", warnings)
    _check(has_devices, "devices/ directory found", "devices/ directory missing", errors)
    _check(has_controllers, "controllers/ directory found", "controllers/ missing", warnings)

    # 2. Validate Python syntax
    rprint("\n[bold]── Validating Python syntax ──────────────[/bold]")
    py_files = list(Path(".").rglob("*.py"))
    py_files = [f for f in py_files if "__pycache__" not in str(f) and ".venv" not in str(f)]

    for f in py_files:
        try:
            ast.parse(f.read_text())
            rprint(f"  [green]✓[/green] {f}")
        except SyntaxError as e:
            errors.append(f"{f}:{e.lineno}: {e.msg}")
            rprint(f"  [red]✗[/red] {f}:{e.lineno}: {e.msg}")

    # 3. Check device files
    rprint("\n[bold]── Validating devices ────────────────────[/bold]")
    device_files = list(Path("devices").glob("*.py")) if has_devices else []
    for f in device_files:
        if f.name.startswith("_"):
            continue
        tree = ast.parse(f.read_text())
        classes = [n for n in ast.walk(tree) if isinstance(n, ast.ClassDef)]
        if not classes:
            warnings.append(f"{f}: no class defined")
            rprint(f"  [yellow]⚠[/yellow] {f}: no Device class found")
        else:
            for cls in classes:
                _validate_device_class(f, cls, errors, warnings)

    # 4. Check controller files
    rprint("\n[bold]── Validating controllers ────────────────[/bold]")
    ctrl_files = list(Path("controllers").glob("*.py")) if has_controllers else []
    for f in ctrl_files:
        if f.name.startswith("_"):
            continue
        tree = ast.parse(f.read_text())
        classes = [n for n in ast.walk(tree) if isinstance(n, ast.ClassDef)]
        if not classes:
            warnings.append(f"{f}: no class defined")
        else:
            for cls in classes:
                has_decorated = any(
                    isinstance(n, ast.FunctionDef) and n.decorator_list for n in ast.walk(cls)
                )
                if has_decorated:
                    rprint(f"  [green]✓[/green] {f}: {cls.name}")
                else:
                    warnings.append(f"{f}: {cls.name} has no decorated methods")
                    rprint(f"  [yellow]⚠[/yellow] {f}: {cls.name} has no @on.* triggers")

    # 5. Check model files
    model_dir = Path("models")
    if model_dir.is_dir():
        rprint("\n[bold]── Validating models ─────────────────────[/bold]")
        for f in model_dir.glob("*.py"):
            if f.name.startswith("_"):
                continue
            rprint(f"  [green]✓[/green] {f}")

    # 6. Memory estimate
    if target:
        rprint(f"\n[bold]── Memory estimate ({target}) ──────────────[/bold]")
        _memory_estimate(target, len(device_files), len(ctrl_files))

    # Summary
    rprint("\n[bold]── Result ───────────────────────────────[/bold]")
    if errors:
        rprint(f"  [red]{len(errors)} error(s)[/red], {len(warnings)} warning(s)")
        for e in errors:
            rprint(f"  [red]✗[/red] {e}")
        raise typer.Exit(1)
    elif warnings:
        rprint(f"  [green]✓ passed[/green] with {len(warnings)} warning(s)")
        for w in warnings:
            rprint(f"  [yellow]⚠[/yellow] {w}")
    else:
        rprint("  [green]✓ all checks passed[/green]")


def _check(condition: bool, pass_msg: str, fail_msg: str, collection: list[str]) -> None:
    if condition:
        rprint(f"  [green]✓[/green] {pass_msg}")
    else:
        collection.append(fail_msg)
        rprint(f"  [red]✗[/red] {fail_msg}")


def _validate_device_class(
    filepath: Path, cls: ast.ClassDef, errors: list[str], warnings: list[str]
) -> None:
    """Basic AST-level validation of a Device class."""
    has_id = False
    has_connection = False
    has_registers = False
    register_count = 0

    for node in cls.body:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    if target.id == "id":
                        has_id = True
                    elif target.id == "connection":
                        has_connection = True
                    elif target.id == "registers":
                        has_registers = True
                        if isinstance(node.value, ast.List):
                            register_count = len(node.value.elts)

    if has_id and has_connection and has_registers:
        rprint(f"  [green]✓[/green] {filepath}: {cls.name} ({register_count} registers)")
    else:
        missing = []
        if not has_id:
            missing.append("id")
        if not has_connection:
            missing.append("connection")
        if not has_registers:
            missing.append("registers")
        errors.append(f"{filepath}: {cls.name} missing {', '.join(missing)}")
        rprint(f"  [red]✗[/red] {filepath}: {cls.name} missing {', '.join(missing)}")


def _memory_estimate(target: str, num_devices: int, num_controllers: int) -> None:
    """Rough memory estimate for the target platform."""
    estimates = {
        "esp32": {"runtime": 48, "driver": 12, "expr": 15, "ram_total": 520, "flash_total": 4096},
        "linux": {"runtime": 48, "driver": 12, "expr": 15, "ram_total": 0, "flash_total": 0},
        "rtos": {"runtime": 32, "driver": 8, "expr": 10, "ram_total": 256, "flash_total": 1024},
    }
    est = estimates.get(target, estimates["linux"])

    ram_used = est["runtime"] + num_devices * est["driver"] + est["expr"]
    ram_total = est["ram_total"]

    if ram_total > 0:
        pct = ram_used / ram_total * 100
        rprint(f"  Runtime:     {est['runtime']}KB")
        rprint(f"  Drivers:     {num_devices * est['driver']}KB ({num_devices} devices)")
        rprint(f"  Expressions: {est['expr']}KB")
        rprint(f"  Controllers: ~{num_controllers}KB")
        rprint(f"  [bold]RAM total:    {ram_used}KB / {ram_total}KB ({pct:.0f}%)[/bold]")

        if pct > 80:
            rprint("  [red]⚠ RAM usage high — consider reducing devices[/red]")
        else:
            rprint("  [green]✓ RAM fits[/green]")
    else:
        rprint("  [green]✓ Linux target — no memory constraints[/green]")
