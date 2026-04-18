"""Taskforce CLI entry point.

Delegates to the unified CLI in taskforce_cli if available,
otherwise provides framework-only commands.
"""

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
        memory,
        run,
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
    app.add_typer(acp.app, name="acp", help="Agent Communication Protocol")

    @app.callback()
    def main(
        ctx: typer.Context,
        profile: str = typer.Option(
            "dev", "--profile", "-p", help="Configuration profile"
        ),
        debug: bool = typer.Option(
            False, "--debug", "-d", help="Enable debug output"
        ),
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
