"""Taskforce CLI entry point - wires framework + agent packages."""

import typer
from rich.console import Console

# Framework commands (always available)
from taskforce.api.cli.commands import (
    chat,
    config,
    memory,
    run,
    skills,
    tools,
)
from taskforce.api.cli.env_loader import load_dotenv_if_present

# CLI-package-local commands
from taskforce_cli.commands import serve

load_dotenv_if_present()

app = typer.Typer(
    name="taskforce",
    help="Taskforce - AI Agent Framework",
    add_completion=True,
    no_args_is_help=True,
    rich_markup_mode="rich",
)

console = Console()

# Register framework commands
app.add_typer(run.app, name="run", help="Execute missions")
app.add_typer(chat.app, name="chat", help="Interactive chat mode")
app.add_typer(tools.app, name="tools", help="Tool management")
app.add_typer(skills.app, name="skills", help="Skill management")
app.add_typer(config.app, name="config", help="Configuration management")
app.add_typer(memory.app, name="memory", help="Memory management")
app.add_typer(serve.app, name="serve", help="Run Taskforce as a REST webservice")

# --- Agent commands (optional, loaded if packages installed) ---

# Butler agent
try:
    from taskforce_butler.cli.commands import app as butler_app

    app.add_typer(butler_app, name="butler", help="Butler agent daemon")
except ImportError:
    pass

# Coding agent (epic orchestration)
try:
    from taskforce_coding_agent.cli import app as epic_app

    app.add_typer(epic_app, name="epic", help="Epic orchestration (multi-agent)")
except ImportError:
    pass

# RAG agent
try:
    from taskforce_rag_agent.cli import app as rag_app

    app.add_typer(rag_app, name="rag", help="RAG agent operations")
except ImportError:
    pass


def _detect_default_profile() -> str:
    """Return the best default profile based on installed agent packages.

    If ``taskforce_butler`` is installed the default is ``"butler"``
    (matching the current framework default). Otherwise fall back to
    ``"dev"``.
    """
    try:
        import taskforce_butler  # noqa: F401

        return "butler"
    except ImportError:
        return "dev"


@app.callback()
def main(
    ctx: typer.Context,
    profile: str = typer.Option(
        None,
        "--profile",
        "-p",
        help="Configuration profile (default: 'butler' if installed, else 'dev')",
    ),
    debug: bool = typer.Option(
        False,
        "--debug",
        "-d",
        help="Enable debug output",
    ),
):
    """Taskforce Agent CLI."""
    if profile is None:
        profile = _detect_default_profile()
    ctx.obj = {"profile": profile, "debug": debug}

    # Register agent config directories so the framework profile_loader
    # can find configs shipped by agent packages.
    from taskforce_cli.agent_discovery import register_agent_config_dirs

    register_agent_config_dirs()


@app.command()
def version():
    """Show Taskforce version."""
    from taskforce import __version__
    from taskforce.api.cli.output_formatter import TaskforceConsole

    tf_console = TaskforceConsole()
    tf_console.print_banner()
    console.print(f"[bold blue]Version:[/bold blue] [cyan]{__version__}[/cyan]")

    # Show installed agent packages
    _print_agent_packages()


def _print_agent_packages() -> None:
    """Print which optional agent packages are installed."""
    agents = [
        ("taskforce-butler", "taskforce_butler"),
        ("taskforce-coding-agent", "taskforce_coding_agent"),
        ("taskforce-rag-agent", "taskforce_rag_agent"),
    ]
    installed = []
    for display_name, import_name in agents:
        try:
            mod = __import__(import_name)
            ver = getattr(mod, "__version__", "installed")
            installed.append(f"{display_name} ({ver})")
        except ImportError:
            pass

    if installed:
        console.print(f"[bold blue]Agents:[/bold blue]  [cyan]{', '.join(installed)}[/cyan]")
    else:
        console.print("[dim]No agent packages installed[/dim]")


if __name__ == "__main__":
    app()
