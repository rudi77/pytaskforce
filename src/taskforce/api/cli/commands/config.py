"""Config command - Configuration management."""

import sys
from pathlib import Path

import typer
import yaml
from rich.console import Console
from rich.table import Table

app = typer.Typer(help="Configuration management")
console = Console()


def _get_config_dir() -> Path:
    """Get configuration directory, checking new location first, then old for compatibility."""
    # Try to find project root (similar to get_base_path in factory.py)
    # This is a CLI command, so we're likely running from project root
    project_root = Path.cwd()
    
    # Try new location first
    new_config_dir = project_root / "src" / "taskforce_extensions" / "configs"
    if new_config_dir.exists():
        return new_config_dir
    
    # Fall back to old location
    old_config_dir = project_root / "configs"
    if old_config_dir.exists():
        return old_config_dir
    
    # Default to new location even if it doesn't exist
    return new_config_dir


@app.command("list")
def list_profiles():
    """List available configuration profiles."""
    config_dir = _get_config_dir()

    if not config_dir.exists():
        console.print(f"[red]Configuration directory not found: {config_dir}[/red]")
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
    config_dir = _get_config_dir()
    config_path = config_dir / f"{profile}.yaml"

    if not config_path.exists():
        console.print(f"[red]Profile not found: {profile}[/red]")
        raise typer.Exit(1)

    with open(config_path) as f:
        config = yaml.safe_load(f)

    console.print(f"\n[bold]Profile:[/bold] {profile}")
    console.print(f"[bold]Path:[/bold] {config_path}\n")
    console.print_json(data=config)

