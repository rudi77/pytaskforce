"""Missions command - Mission management, templates, and runtime control."""

import os
from pathlib import Path

import httpx
import typer
from rich.console import Console
from rich.table import Table

app = typer.Typer(help="Mission management")
console = Console()


def _api_base_url() -> str:
    """Resolve the API base URL for runtime mission commands.

    Looks at ``TASKFORCE_API_URL``; falls back to ``http://127.0.0.1:8000``
    so the local default works without explicit configuration.
    """
    return os.environ.get("TASKFORCE_API_URL", "http://127.0.0.1:8000").rstrip("/")


@app.command("list")
def list_missions():
    """List available mission templates."""
    missions_dir = Path("missions")

    if not missions_dir.exists():
        console.print("[yellow]No missions directory found[/yellow]")
        console.print("[dim]Create missions/ directory with .txt mission templates[/dim]")
        return

    missions = list(missions_dir.glob("*.txt"))

    if not missions:
        console.print("[yellow]No mission templates found[/yellow]")
        return

    table = Table(title="Mission Templates")
    table.add_column("Name", style="cyan")
    table.add_column("Path", style="white")

    for mission_path in missions:
        mission_name = mission_path.stem
        table.add_row(mission_name, str(mission_path))

    console.print(table)


@app.command("show")
def show_mission(name: str = typer.Argument(..., help="Mission template name")):
    """Show mission template content."""
    mission_path = Path(f"missions/{name}.txt")

    if not mission_path.exists():
        console.print(f"[red]Mission template not found: {name}[/red]")
        raise typer.Exit(1)

    with open(mission_path, encoding="utf-8") as f:
        content = f.read()

    console.print(f"\n[bold]Mission:[/bold] {name}")
    console.print(f"[bold]Path:[/bold] {mission_path}\n")
    console.print(content)


@app.command("running")
def running_missions(
    api_url: str = typer.Option(
        None,
        "--api-url",
        help="API base URL (defaults to TASKFORCE_API_URL or http://127.0.0.1:8000).",
    ),
):
    """List queued and in-flight missions on a running daemon/API."""
    base = (api_url or _api_base_url()).rstrip("/")
    try:
        response = httpx.get(f"{base}/api/v1/missions", timeout=10.0)
    except httpx.RequestError as exc:
        console.print(f"[red]Failed to reach API at {base}:[/red] {exc}")
        raise typer.Exit(2) from exc

    if response.status_code == 503:
        console.print(
            "[yellow]API is up but no PersistentAgentService is registered. "
            "Start the butler daemon (or another embedding host) first.[/yellow]"
        )
        raise typer.Exit(1)
    if response.status_code != 200:
        console.print(f"[red]API returned {response.status_code}:[/red] {response.text}")
        raise typer.Exit(1)

    payload = response.json()
    missions = payload.get("missions", [])
    if not missions:
        console.print("[dim]No queued or in-flight missions.[/dim]")
        return

    table = Table(title="Active Missions")
    table.add_column("Request ID", style="cyan")
    table.add_column("Session ID", style="white")
    table.add_column("Status", style="green")
    table.add_column("Channel", style="magenta")
    table.add_column("Priority", justify="right")
    table.add_column("Message")
    for mission in missions:
        table.add_row(
            mission.get("request_id", ""),
            mission.get("session_id", ""),
            mission.get("status", ""),
            mission.get("channel", ""),
            str(mission.get("priority", "")),
            mission.get("message_preview", ""),
        )
    console.print(table)


@app.command("cancel")
def cancel_mission(
    request_id: str = typer.Argument(..., help="Mission request_id to cancel."),
    api_url: str = typer.Option(
        None,
        "--api-url",
        help="API base URL (defaults to TASKFORCE_API_URL or http://127.0.0.1:8000).",
    ),
):
    """Cancel a queued or in-flight mission by request_id.

    For queued missions this resolves the caller's Future with
    ``status=cancelled`` so the processor skips it. For in-flight
    missions it forwards a cooperative interrupt (ADR-019) to the
    running session — the agent finishes its current step and pauses
    at the next ReAct boundary with state persisted.
    """
    base = (api_url or _api_base_url()).rstrip("/")
    try:
        response = httpx.post(
            f"{base}/api/v1/missions/{request_id}/cancel",
            timeout=10.0,
        )
    except httpx.RequestError as exc:
        console.print(f"[red]Failed to reach API at {base}:[/red] {exc}")
        raise typer.Exit(2) from exc

    if response.status_code == 404:
        console.print(f"[red]No queued or in-flight mission with id {request_id!r}[/red]")
        raise typer.Exit(1)
    if response.status_code == 503:
        console.print(
            "[yellow]API is up but no PersistentAgentService is registered.[/yellow]"
        )
        raise typer.Exit(1)
    if response.status_code not in (200, 202):
        console.print(f"[red]API returned {response.status_code}:[/red] {response.text}")
        raise typer.Exit(1)

    body = response.json()
    status_value = body.get("status", "unknown")
    if status_value == "interrupt_requested":
        console.print(
            f"[green]Interrupt requested for in-flight mission "
            f"{request_id} (session {body.get('session_id')}).[/green] "
            "[dim]The agent finishes its current step before pausing.[/dim]"
        )
    elif status_value == "cancelled":
        console.print(f"[green]Cancelled queued mission {request_id}.[/green]")
    else:
        console.print(f"[yellow]{status_value}:[/yellow] {body}")

