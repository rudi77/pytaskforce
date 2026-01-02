"""Config command - Configuration management."""

from pathlib import Path

import typer
import yaml
from rich.console import Console
from rich.table import Table

app = typer.Typer(help="Configuration management")
console = Console()


@app.command("list")
def list_profiles():
    """List available configuration profiles."""
    config_dir = Path("configs")

    if not config_dir.exists():
        console.print("[red]Configuration directory not found: configs/[/red]")
        raise typer.Exit(1)

    profiles = list(config_dir.glob("*.yaml"))

    if not profiles:
        console.print("[yellow]No configuration profiles found[/yellow]")
        return

    table = Table(title="Configuration Profiles")
    table.add_column("Profile", style="cyan")
    table.add_column("Path", style="white")

    for profile_path in profiles:
        profile_name = profile_path.stem
        table.add_row(profile_name, str(profile_path))

    console.print(table)


@app.command("show")
def show_profile(profile: str = typer.Argument(..., help="Profile name")):
    """Show configuration profile details."""
    config_path = Path(f"configs/{profile}.yaml")

    if not config_path.exists():
        console.print(f"[red]Profile not found: {profile}[/red]")
        raise typer.Exit(1)

    with open(config_path) as f:
        config = yaml.safe_load(f)

    console.print(f"\n[bold]Profile:[/bold] {profile}")
    console.print(f"[bold]Path:[/bold] {config_path}\n")
    console.print_json(data=config)

