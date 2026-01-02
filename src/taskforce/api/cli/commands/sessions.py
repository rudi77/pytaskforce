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
    profile: str = typer.Option("dev", "--profile", "-p", help="Configuration profile")
):
    """List all agent sessions."""

    async def _list_sessions():
        factory = AgentFactory()
        agent = await factory.create_agent(profile=profile)

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
    session_id: str = typer.Argument(..., help="Session ID"),
    profile: str = typer.Option("dev", "--profile", "-p", help="Configuration profile"),
):
    """Show session details."""

    async def _show_session():
        factory = AgentFactory()
        agent = await factory.create_agent(profile=profile)

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

