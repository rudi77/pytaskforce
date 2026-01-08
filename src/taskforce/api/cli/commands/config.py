"""Config command - Configuration management."""

from pathlib import Path

import typer
import yaml
from rich.console import Console
from rich.table import Table

from taskforce.application.factory import get_base_path

app = typer.Typer(help="Configuration management")
console = Console()


@app.command("list")
def list_profiles():
    """List available configuration profiles."""
    config_dir = get_base_path() / "configs"

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
    config_path = get_base_path() / "configs" / f"{profile}.yaml"

    if not config_path.exists():
        console.print(f"[red]Profile not found: {profile}[/red]")
        raise typer.Exit(1)

    with open(config_path) as f:
        config = yaml.safe_load(f)

    console.print(f"\n[bold]Profile:[/bold] {profile}")
    console.print(f"[bold]Path:[/bold] {config_path}\n")
    console.print_json(data=config)


@app.command("models")
def list_models():
    """List available LLM providers and models."""
    config_path = get_base_path() / "configs" / "llm_config.yaml"

    if not config_path.exists():
        console.print("[red]LLM config not found: configs/llm_config.yaml[/red]")
        raise typer.Exit(1)

    with open(config_path) as f:
        llm_config = yaml.safe_load(f)

    default_model = llm_config.get("default_model", "main")

    # Display model aliases
    console.print("\n[bold cyan]Model Aliases[/bold cyan]")
    table = Table()
    table.add_column("Alias", style="green")
    table.add_column("Default Model", style="white")
    table.add_column("", style="dim")

    for alias, model in llm_config.get("models", {}).items():
        is_default = "(default)" if alias == default_model else ""
        table.add_row(alias, model, is_default)

    console.print(table)

    # Display providers
    console.print("\n[bold cyan]Available Providers[/bold cyan]")
    providers = llm_config.get("providers", {})

    for provider_name, provider_config in providers.items():
        # Determine status
        if provider_name == "azure":
            enabled = provider_config.get("enabled", False)
            status = "[green]enabled[/green]" if enabled else "[dim]disabled[/dim]"
        else:
            status = "[green]available[/green]"

        console.print(f"\n  [bold]{provider_name}[/bold]: {status}")

        # Show deployment/model mappings
        if provider_name == "azure" and "deployment_mapping" in provider_config:
            console.print("    [dim]Deployments:[/dim]")
            for alias, deployment in provider_config["deployment_mapping"].items():
                console.print(f"      {alias} -> {deployment}")

        if provider_name == "zai" and "model_mapping" in provider_config:
            console.print("    [dim]Models:[/dim]")
            for alias, model in provider_config["model_mapping"].items():
                console.print(f"      {alias} -> {model}")

    console.print()

