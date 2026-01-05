"""Commands command - List and manage custom slash commands."""

import typer
from rich.console import Console
from rich.table import Table

from taskforce.application.slash_command_registry import SlashCommandRegistry
from taskforce.infrastructure.slash_commands.command_loader import FileSlashCommandLoader

app = typer.Typer(help="Manage custom slash commands")
console = Console()


@app.command("list")
def list_commands(
    all_commands: bool = typer.Option(
        False, "--all", "-a", help="Include built-in commands"
    ),
) -> None:
    """List available slash commands."""
    registry = SlashCommandRegistry()
    commands = registry.list_commands(include_builtin=all_commands)

    if not commands:
        console.print("[yellow]No custom commands found.[/yellow]")
        console.print(
            "\nAdd .md files to .taskforce/commands/ or ~/.taskforce/commands/"
        )
        return

    table = Table(title="Available Commands")
    table.add_column("Command", style="cyan")
    table.add_column("Description")
    table.add_column("Type", style="yellow")
    table.add_column("Source", style="dim")

    for cmd in commands:
        table.add_row(
            f"/{cmd['name']}",
            cmd["description"],
            cmd["type"],
            cmd["source"],
        )

    console.print(table)


@app.command("show")
def show_command(
    name: str = typer.Argument(..., help="Command name (without /)"),
) -> None:
    """Show details of a specific command."""
    registry = SlashCommandRegistry()
    command_def, _ = registry.resolve_command(f"/{name}")

    if not command_def:
        console.print(f"[red]Command not found: /{name}[/red]")
        raise typer.Exit(1)

    console.print(f"[bold cyan]Command:[/bold cyan] /{command_def.name}")
    console.print(f"[bold]Type:[/bold] {command_def.command_type.value}")
    console.print(f"[bold]Source:[/bold] {command_def.source}")
    console.print(f"[bold]Path:[/bold] {command_def.source_path}")
    console.print(f"[bold]Description:[/bold] {command_def.description}")

    if command_def.agent_config:
        console.print("\n[bold]Agent Configuration:[/bold]")
        if command_def.agent_config.get("profile"):
            console.print(f"  Profile: {command_def.agent_config['profile']}")
        if command_def.agent_config.get("tools"):
            console.print(f"  Tools: {', '.join(command_def.agent_config['tools'])}")
        if command_def.agent_config.get("mcp_servers"):
            console.print(
                f"  MCP Servers: {len(command_def.agent_config['mcp_servers'])}"
            )

    console.print("\n[bold]Template:[/bold]")
    console.print(command_def.prompt_template)


@app.command("paths")
def show_paths() -> None:
    """Show directories searched for commands."""
    loader = FileSlashCommandLoader()
    paths = loader.get_search_paths()

    console.print("[bold]Command Search Paths (in priority order):[/bold]")
    for i, path in enumerate(reversed(paths), 1):
        console.print(f"  {i}. {path}")
