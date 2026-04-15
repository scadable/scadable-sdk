"""scadable compile — compile device definitions into gateway artifacts."""

from __future__ import annotations

from pathlib import Path

import typer
from rich import print as rprint
from rich.table import Table


def run_compile(
    target: str = "linux",
    output: str = "out",
    verbose: bool = False,
) -> None:
    """Compile the current project into deployable artifacts."""
    from scadable.compiler import compile_project

    project_root = Path.cwd()
    output_dir = project_root / output

    rprint(f"\n[bold]── Compiling project ({target}) ──────────[/bold]")
    rprint(f"  Root: {project_root}")
    rprint(f"  Output: {output_dir}")

    result = compile_project(
        project_root=project_root,
        target=target,
        output_dir=output_dir,
        verbose=verbose,
    )

    # ── Devices table ────────────────────────────────
    if result.devices:
        rprint("\n[bold]── Devices ──────────────────────────────[/bold]")
        tbl = Table(show_header=True, header_style="bold")
        tbl.add_column("ID")
        tbl.add_column("Name")
        tbl.add_column("Protocol")
        tbl.add_column("Poll")
        tbl.add_column("Registers", justify="right")

        for dev in result.devices:
            conn = dev.get("connection") or {}
            poll = dev.get("poll_ms")
            poll_str = f"{poll}ms" if poll else "-"
            tbl.add_row(
                dev["id"],
                dev.get("name", ""),
                conn.get("protocol", "?"),
                poll_str,
                str(len(dev.get("registers", []))),
            )
        rprint(tbl)

    # ── Controllers table ────────────────────────────
    if result.controllers:
        rprint("\n[bold]── Controllers ──────────────────────────[/bold]")
        tbl = Table(show_header=True, header_style="bold")
        tbl.add_column("ID")
        tbl.add_column("Class")
        tbl.add_column("Triggers", justify="right")
        tbl.add_column("Types")

        for ctrl in result.controllers:
            triggers = ctrl.get("triggers", [])
            types = sorted({t["type"] for t in triggers})
            tbl.add_row(
                ctrl["id"],
                ctrl["class_name"],
                str(len(triggers)),
                ", ".join(types),
            )
        rprint(tbl)

    # ── Memory estimate ──────────────────────────────
    if result.memory:
        rprint(f"\n[bold]── Memory estimate ({target}) ──────────[/bold]")
        mem = result.memory
        rprint(f"  Runtime:     {mem['runtime_kb']}KB")
        rprint(f"  Devices:     {mem['devices_kb']}KB ({len(result.devices)} devices)")
        rprint(f"  Registers:   {mem['registers_kb']}KB")
        rprint(f"  Controllers: {mem['controllers_kb']}KB ({len(result.controllers)} controllers)")
        rprint(f"  [bold]Total:       {mem['total_kb']}KB[/bold]")

        limit = mem.get("ram_limit_kb", 0)
        if limit > 0:
            pct = mem["total_kb"] / limit * 100
            rprint(f"  RAM limit:   {limit}KB ({pct:.0f}% used)")
            if pct > 80:
                rprint("  [red]RAM usage high — consider reducing devices[/red]")
            else:
                rprint("  [green]RAM fits[/green]")
        else:
            rprint("  [green]Linux target — no memory constraints[/green]")

    # ── Warnings ─────────────────────────────────────
    if result.warnings:
        rprint(f"\n[bold]── Warnings ({len(result.warnings)}) ────────────────[/bold]")
        for w in result.warnings:
            rprint(f"  [yellow]![/yellow] {w}")

    # ── Errors ───────────────────────────────────────
    if result.errors:
        rprint(f"\n[bold]── Errors ({len(result.errors)}) ──────────────────[/bold]")
        for e in result.errors:
            rprint(f"  [red]x[/red] {e}")
        rprint("\n[red]Compilation failed.[/red]")
        raise typer.Exit(1)

    # ── Output ───────────────────────────────────────
    rprint("\n[bold]── Output ──────────────────────────────[/bold]")
    if result.manifest_path:
        rprint(f"  [green]manifest[/green]  {result.manifest_path}")
    if result.bundle_path:
        size_kb = result.bundle_path.stat().st_size / 1024
        rprint(f"  [green]bundle[/green]    {result.bundle_path} ({size_kb:.1f}KB)")

    # List driver configs
    drivers_dir = output_dir / "drivers"
    if drivers_dir.is_dir():
        for f in sorted(drivers_dir.iterdir()):
            rprint(f"  [green]driver[/green]    {f}")

    rprint("\n[green]Compilation complete.[/green]")
