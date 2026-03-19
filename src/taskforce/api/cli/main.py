"""Taskforce CLI entry point."""

import typer
from rich.console import Console

from taskforce.api.cli.commands import (
    butler,
    chat,
    config,
    conversations,
    memory,
    missions,
    run,
    skills,
    tools,
)

app = typer.Typer(
    name="taskforce",
    help="Taskforce - Personal AI Assistant (Butler)",
    add_completion=True,
    no_args_is_help=True,
    rich_markup_mode="rich",
)

console = Console()

# Register command groups
app.add_typer(run.app, name="run", help="Execute missions")
app.add_typer(chat.app, name="chat", help="Interactive chat mode")
app.add_typer(tools.app, name="tools", help="Tool management")
app.add_typer(skills.app, name="skills", help="Skill management")
app.add_typer(conversations.app, name="conversations", help="Conversation management")
app.add_typer(missions.app, name="missions", help="Mission management")
app.add_typer(config.app, name="config", help="Configuration management")
app.add_typer(butler.app, name="butler", help="Butler agent daemon")
app.add_typer(memory.app, name="memory", help="Memory management")


@app.callback()
def main(
    ctx: typer.Context,
    profile: str = typer.Option("butler", "--profile", "-p", help="Configuration profile"),
    debug: bool = typer.Option(
        False,
        "--debug",
        "-d",
        help="Enable debug output (shows agent thoughts, actions, observations)",
    ),
):
    """Taskforce Agent CLI."""
    # Store global options in context for subcommands
    ctx.obj = {"profile": profile, "debug": debug}


@app.command()
def version():
    """Show Taskforce version."""
    from taskforce import __version__
    from taskforce.api.cli.output_formatter import TaskforceConsole

    tf_console = TaskforceConsole()
    tf_console.print_banner()
    console.print(f"[bold blue]Version:[/bold blue] [cyan]{__version__}[/cyan]")


# ------------------------------------------------------------------
# Top-level convenience commands (delegate to butler subcommands)
# ------------------------------------------------------------------


@app.command("start")
def start(
    ctx: typer.Context,
    profile: str = typer.Option("butler", "--profile", "-p", help="Butler profile"),
    detach: bool = typer.Option(False, "--detach", "-d", help="Run in background"),
) -> None:
    """Start the butler daemon (shortcut for 'butler start')."""
    butler.butler_start(ctx, profile=profile, detach=detach)


@app.command("status")
def status(ctx: typer.Context) -> None:
    """Show butler daemon status (shortcut for 'butler status')."""
    butler.butler_status(ctx)


@app.command("stop")
def stop(ctx: typer.Context) -> None:
    """Stop the butler daemon gracefully."""
    import json
    from pathlib import Path

    status_path = Path(".taskforce/butler/status.json")
    if not status_path.exists():
        console.print("[yellow]Butler daemon is not running.[/yellow]")
        return

    # Signal stop by writing a stop request file
    stop_path = Path(".taskforce/butler/stop_requested")
    stop_path.parent.mkdir(parents=True, exist_ok=True)
    stop_path.write_text(json.dumps({"requested_at": str(__import__("datetime").datetime.now())}))
    console.print("[green]Stop signal sent to butler daemon.[/green]")


if __name__ == "__main__":
    app()
