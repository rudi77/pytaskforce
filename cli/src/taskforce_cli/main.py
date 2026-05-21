"""Taskforce CLI entry point - wires framework + agent packages."""

import typer
from rich.console import Console

# Framework commands (always available)
from taskforce.api.cli.commands import (
    acp,
    chat,
    config,
    daemon,
    goals,
    memory,
    missions,
    run,
    runtimes,
    skills,
    tools,
)
from taskforce.api.cli.env_loader import load_dotenv_if_present

# CLI-package-local commands
from taskforce_cli.commands import serve, up

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
app.add_typer(missions.app, name="missions", help="Mission templates and runtime control")
app.add_typer(goals.app, name="goals", help="Standing-goal management (proactive layer)")
app.add_typer(acp.app, name="acp", help="Agent Communication Protocol")
app.add_typer(runtimes.app, name="runtimes", help="Agent runtime management")
app.add_typer(daemon.app, name="daemon", help="Generic agent daemon management")
app.add_typer(serve.app, name="serve", help="Run Taskforce as a REST webservice")
app.add_typer(up.app, name="up", help="Start Taskforce + web UI (one command)")

# --- Agent commands (optional, loaded if packages installed) ---
#
# Discovery is driven by the ``taskforce.cli_apps`` entry-point group
# (see :mod:`taskforce.application.agent_plugin_registry`). The Butler
# no longer ships a CLI sub-app (Phase 4 / ADR-028) — use
# ``taskforce daemon start --profile butler`` instead. The legacy
# hardcoded fallback below covers any other agent package that doesn't
# yet declare a ``taskforce.cli_apps`` entry-point.

from taskforce.application.agent_plugin_registry import load_cli_apps as _load_cli_apps

_AGENT_CLI_HELP: dict[str, str] = {
    "epic": "Epic orchestration (multi-agent)",
    "rag": "RAG agent operations",
}

_registered_agent_cli: set[str] = set()

for _name, _cli_app in _load_cli_apps().items():
    app.add_typer(_cli_app, name=_name, help=_AGENT_CLI_HELP.get(_name, ""))
    _registered_agent_cli.add(_name)


def _register_fallback_cli(name: str, import_path: str) -> None:
    """Import a CLI app the legacy way and warn — used only if no entry-point."""
    if name in _registered_agent_cli:
        return
    try:
        module_path, _, attr = import_path.partition(":")
        mod = __import__(module_path, fromlist=[attr])
        cli_app = getattr(mod, attr)
    except (ImportError, AttributeError):
        return
    import structlog

    structlog.get_logger(__name__).warning(
        "hardcoded_agent_fallback",
        component="cli_apps",
        name=name,
        import_path=import_path,
        hint=f'declare [project.entry-points."taskforce.cli_apps"] in the {name} package pyproject.toml',
    )
    app.add_typer(cli_app, name=name, help=_AGENT_CLI_HELP.get(name, ""))
    _registered_agent_cli.add(name)


_register_fallback_cli("epic", "taskforce_coding_agent.cli:app")
_register_fallback_cli("rag", "taskforce_rag_agent.cli:app")


def _detect_default_profile() -> str:
    """Return the best default profile based on installed agent packages.

    Looks for a ``taskforce.config_dirs`` entry-point named ``butler``
    (registered by the ``taskforce-butler`` data package) and returns
    ``"butler"`` if present. Falls back to ``"dev"`` otherwise.

    Pre-ADR-028 this imported ``taskforce_butler`` directly — Butler is
    now a YAML-only data package without an importable surface beyond a
    bare ``__init__.py`` shim, so the discovery happens through the
    entry-point group instead.
    """
    from taskforce.application.agent_plugin_registry import load_config_dirs

    if "butler" in load_config_dirs():
        return "butler"
    return "dev"


@app.callback()
def main(
    ctx: typer.Context,
    profile: str = typer.Option(
        None,
        "--profile",
        "-p",
        envvar="TASKFORCE_PROFILE",
        help=(
            "Configuration profile. Falls back to the TASKFORCE_PROFILE env var, "
            "then 'butler' if installed, else 'dev'."
        ),
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
        ("taskforce-google-workspace", "taskforce_google_workspace"),
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
