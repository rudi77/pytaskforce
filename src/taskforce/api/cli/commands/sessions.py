"""Sessions command - Manage agent sessions."""

import asyncio

import typer
from rich.console import Console
from rich.table import Table

from taskforce.application.factory import AgentFactory

app = typer.Typer(help="Session management")
console = Console()


@app.command("list")
def list_sessions(
    ctx: typer.Context,
    profile: str | None = typer.Option(
        None,
        "--profile",
        "-p",
        help="Profile name (e.g., coding_agent, devops_agent, rag_agent)",
    ),
):
    """List all agent sessions."""
    global_opts = ctx.obj or {}
    profile = profile or global_opts.get("profile", "dev")

    async def _list_sessions():
        factory = AgentFactory()
        try:
            agent = await factory.create_agent(profile=profile)
        except FileNotFoundError as exc:
            console.print(f"[red]Profile not found: {profile}[/red]")
            raise typer.Exit(1) from exc

        try:
            sessions = await agent.state_manager.list_sessions()

            table = Table(title="Agent Sessions")
            table.add_column("Session ID", style="cyan")
            table.add_column("Status", style="white")

            for session_id in sessions:
                state = await agent.state_manager.load_state(session_id)
                status = state.get("status", "unknown") if state else "unknown"
                table.add_row(session_id, status)

            console.print(table)
        finally:
            await agent.close()

    asyncio.run(_list_sessions())


@app.command("show")
def show_session(
    ctx: typer.Context,
    session_id: str = typer.Argument(..., help="Session ID"),
    profile: str | None = typer.Option(
        None,
        "--profile",
        "-p",
        help="Profile name (e.g., coding_agent, devops_agent, rag_agent)",
    ),
):
    """Show session details."""
    global_opts = ctx.obj or {}
    profile = profile or global_opts.get("profile", "dev")

    async def _show_session():
        factory = AgentFactory()
        try:
            agent = await factory.create_agent(profile=profile)
        except FileNotFoundError as exc:
            console.print(f"[red]Profile not found: {profile}[/red]")
            raise typer.Exit(1) from exc

        try:
            state = await agent.state_manager.load_state(session_id)

            if not state:
                console.print(f"[red]Session '{session_id}' not found[/red]")
                raise typer.Exit(1)

            console.print(f"\n[bold]Session:[/bold] {session_id}")
            console.print(f"[bold]Mission:[/bold] {state.get('mission', 'N/A')}")
            console.print(f"[bold]Status:[/bold] {state.get('status', 'N/A')}")
            console.print_json(data=state)
        finally:
            await agent.close()

    asyncio.run(_show_session())
