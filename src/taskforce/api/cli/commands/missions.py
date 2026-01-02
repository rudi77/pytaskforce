"""Missions command - Mission management and templates."""

from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

app = typer.Typer(help="Mission management")
console = Console()


@app.command("list")
def list_missions():
    """List available mission templates."""
    missions_dir = Path("missions")

    if not missions_dir.exists():
        console.print("[yellow]No missions directory found[/yellow]")
        console.print("[dim]Create missions/ directory with .txt mission templates[/dim]")
        return

    missions = list(missions_dir.glob("*.txt"))

    if not missions:
        console.print("[yellow]No mission templates found[/yellow]")
        return

    table = Table(title="Mission Templates")
    table.add_column("Name", style="cyan")
    table.add_column("Path", style="white")

    for mission_path in missions:
        mission_name = mission_path.stem
        table.add_row(mission_name, str(mission_path))

    console.print(table)


@app.command("show")
def show_mission(name: str = typer.Argument(..., help="Mission template name")):
    """Show mission template content."""
    mission_path = Path(f"missions/{name}.txt")

    if not mission_path.exists():
        console.print(f"[red]Mission template not found: {name}[/red]")
        raise typer.Exit(1)

    with open(mission_path) as f:
        content = f.read()

    console.print(f"\n[bold]Mission:[/bold] {name}")
    console.print(f"[bold]Path:[/bold] {mission_path}\n")
    console.print(content)

