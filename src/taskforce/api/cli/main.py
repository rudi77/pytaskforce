"""Taskforce CLI entry point.

Delegates to the unified CLI in taskforce_cli if available,
otherwise provides framework-only commands.
"""

from taskforce.api.cli.env_loader import load_dotenv_if_present

load_dotenv_if_present()

try:
    # Use the unified CLI that integrates framework + agent packages
    from taskforce_cli.main import app  # noqa: F401
except ImportError:
    # Fallback: framework-only CLI (no agent commands)
    import typer
    from rich.console import Console

    from taskforce.api.cli.commands import (
        acp,
        chat,
        config,
        goals,
        memory,
        missions,
        run,
        runtimes,
        skills,
        tools,
    )

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

    @app.callback()
    def main(
        ctx: typer.Context,
        profile: str = typer.Option(
            "dev",
            "--profile",
            "-p",
            envvar="TASKFORCE_PROFILE",
            help="Configuration profile (env: TASKFORCE_PROFILE)",
        ),
        debug: bool = typer.Option(False, "--debug", "-d", help="Enable debug output"),
    ):
        """Taskforce Agent CLI."""
        ctx.obj = {"profile": profile, "debug": debug}

    @app.command()
    def version():
        """Show Taskforce version."""
        from taskforce import __version__

        console.print(f"Taskforce v{__version__}")


if __name__ == "__main__":
    app()
