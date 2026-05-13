"""Generic agent-daemon CLI command (`taskforce daemon ...`).

This command exposes :class:`taskforce.application.agent_daemon.AgentDaemon`
as a profile-driven entry-point, replacing the previous package-specific
``taskforce butler start`` (ADR-027).

Run ``taskforce daemon start --profile <name>`` for any agent profile
that ships in an installed agent package (butler, coding-agent, rag-agent
or any third-party plugin). The agent's ``status.json`` is written under
``{work_dir}/{profile}/status.json``.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

app = typer.Typer(help="Generic agent daemon management")
console = Console()


@app.command("start")
def daemon_start(
    ctx: typer.Context,
    profile: str = typer.Option(
        ...,
        "--profile",
        "-p",
        help="Profile name to load (e.g. butler, coding_agent, rag_agent).",
    ),
    role: str = typer.Option(
        "",
        "--role",
        "-r",
        help="Role overlay (e.g. accountant). Searched in agent-package configs/roles/.",
    ),
    work_dir: str = typer.Option(
        ".taskforce", "--work-dir", help="Working directory for state and logs."
    ),
    no_supervisor: bool = typer.Option(
        False,
        "--no-supervisor",
        help="Disable the watchdog/auto-restart supervisor (issue #156).",
    ),
    log_name: str = typer.Option(
        "",
        "--log-name",
        help="Log file name. Defaults to '<profile>.log'.",
    ),
) -> None:
    """Start an event-driven agent daemon for the given profile."""
    from taskforce.infrastructure.logging import configure_logging

    global_opts = ctx.obj or {}
    debug = global_opts.get("debug", False)

    resolved_log_name = log_name or f"{profile}.log"
    log_path = configure_logging(
        log_dir=f"{work_dir}/logs",
        log_name=resolved_log_name,
        debug=debug,
    )

    role_name = role or None
    role_info = f", role: {role_name}" if role_name else ""
    console.print(
        f"[bold green]Starting {profile} daemon[/bold green] (profile: {profile}{role_info})"
    )
    console.print(f"[dim]Logs: {log_path}[/dim]")
    asyncio.run(_run_daemon(profile, role_name, work_dir, supervised=not no_supervisor))


async def _run_daemon(
    profile: str,
    role: str | None = None,
    work_dir: str = ".taskforce",
    *,
    supervised: bool = True,
) -> None:
    """Initialise and run the agent daemon, optionally under the supervisor."""
    from taskforce.application.agent_daemon import AgentDaemon

    if not supervised:
        daemon = AgentDaemon(profile=profile, role=role, work_dir=work_dir)
        try:
            await daemon.start()
            console.print(
                f"[bold green]{profile} daemon is running.[/bold green] Press Ctrl+C to stop."
            )
            while daemon.is_running:
                await asyncio.sleep(1)
        except KeyboardInterrupt:
            console.print(f"\n[yellow]Shutting down {profile} daemon...[/yellow]")
        finally:
            await daemon.stop()
            console.print(f"[green]{profile} daemon stopped.[/green]")
        return

    from taskforce.application.daemon_supervisor import AgentDaemonSupervisor

    supervisor = AgentDaemonSupervisor(
        daemon_factory=lambda: AgentDaemon(profile=profile, role=role, work_dir=work_dir),
    )
    supervisor.install_signal_handlers()
    console.print(
        f"[bold green]{profile} daemon supervisor is running.[/bold green] Press Ctrl+C to stop."
    )
    try:
        await supervisor.run()
    except KeyboardInterrupt:
        # Belt-and-braces: on Windows ProactorEventLoop SIGINT can land
        # here instead of the loop.add_signal_handler path.
        supervisor.request_shutdown()
        await supervisor.run()
    console.print(f"[green]{profile} daemon stopped.[/green]")


@app.command("status")
def daemon_status(
    ctx: typer.Context,
    profile: str = typer.Option(
        ...,
        "--profile",
        "-p",
        help="Profile whose status.json to read.",
    ),
    work_dir: str = typer.Option(".taskforce", "--work-dir"),
) -> None:
    """Show the agent daemon's status.json contents for the given profile."""
    status_path = Path(work_dir) / profile / "status.json"
    if not status_path.is_file():
        console.print(f"[yellow]No status file found at {status_path}.[/yellow]")
        console.print(f"Is the {profile} daemon running?")
        raise typer.Exit(code=1)

    try:
        data = json.loads(status_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        console.print(f"[red]status.json is malformed: {exc}[/red]")
        raise typer.Exit(code=1) from exc

    table = Table(title=f"{profile} daemon status")
    table.add_column("Field", style="bold cyan")
    table.add_column("Value")
    for key, value in data.items():
        table.add_row(key, str(value))
    console.print(table)
