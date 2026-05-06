"""``taskforce goals ...`` — manage standing goals (proactive layer).

All subcommands talk to the running REST API
(``TASKFORCE_API_URL`` or ``http://127.0.0.1:8000``); the daemon owns
the canonical store, so going through HTTP keeps both clients in
sync.
"""

from __future__ import annotations

import os

import httpx
import typer
from rich.console import Console
from rich.table import Table

app = typer.Typer(help="Standing-goal management (proactive layer).")
console = Console()


def _api_base_url() -> str:
    return os.environ.get("TASKFORCE_API_URL", "http://127.0.0.1:8000").rstrip("/")


def _client() -> httpx.Client:
    return httpx.Client(base_url=_api_base_url(), timeout=10.0)


def _format_goal_row(goal: dict) -> tuple[str, ...]:
    last = goal.get("last_evaluated_at") or "—"
    enabled = "✓" if goal.get("enabled") else "·"
    return (
        goal.get("goal_id", "")[:8],
        enabled,
        goal.get("description", "")[:60],
        goal.get("frequency", ""),
        str(goal.get("priority", "")),
        str(last)[:19],
    )


@app.command("list")
def list_goals() -> None:
    """List every standing goal known to the daemon."""
    with _client() as client:
        response = client.get("/api/v1/standing-goals")
    if response.status_code != 200:
        console.print(f"[red]API returned {response.status_code}:[/red] {response.text}")
        raise typer.Exit(1)
    goals = response.json()
    if not goals:
        console.print("[dim]No standing goals configured.[/dim]")
        return
    table = Table(title="Standing Goals")
    table.add_column("ID")
    table.add_column("On")
    table.add_column("Description")
    table.add_column("Frequency")
    table.add_column("Prio", justify="right")
    table.add_column("Last evaluated")
    for goal in goals:
        table.add_row(*_format_goal_row(goal))
    console.print(table)


@app.command("show")
def show_goal(goal_id: str = typer.Argument(...)) -> None:
    """Show full details for one goal."""
    with _client() as client:
        response = client.get(f"/api/v1/standing-goals/{goal_id}")
    if response.status_code == 404:
        console.print(f"[red]No standing goal {goal_id!r}[/red]")
        raise typer.Exit(1)
    if response.status_code != 200:
        console.print(f"[red]API returned {response.status_code}:[/red] {response.text}")
        raise typer.Exit(1)
    goal = response.json()
    console.print_json(data=goal)


@app.command("add")
def add_goal(
    description: str = typer.Option(..., "--description", "-d", help="Short description."),
    prompt: str = typer.Option(
        ...,
        "--prompt",
        "-p",
        help="LLM evaluation prompt (asks 'should we act now?').",
    ),
    frequency: str = typer.Option(
        ...,
        "--frequency",
        "-f",
        help="Cron expression (5-field, e.g. '0 9 * * 1' for Mondays 9am).",
    ),
    priority: int = typer.Option(5, "--priority", help="Mission priority (lower = sooner)."),
    disabled: bool = typer.Option(False, "--disabled", help="Create disabled."),
) -> None:
    """Add a standing goal."""
    payload = {
        "description": description,
        "evaluation_prompt": prompt,
        "frequency": frequency,
        "priority": priority,
        "enabled": not disabled,
    }
    with _client() as client:
        response = client.post("/api/v1/standing-goals", json=payload)
    if response.status_code not in (200, 201):
        console.print(f"[red]API returned {response.status_code}:[/red] {response.text}")
        raise typer.Exit(1)
    goal = response.json()
    console.print(f"[green]Added standing goal {goal['goal_id']}[/green]")


@app.command("disable")
def disable_goal(goal_id: str = typer.Argument(...)) -> None:
    """Disable a goal without deleting it."""
    _patch_goal(goal_id, {"enabled": False}, success="disabled")


@app.command("enable")
def enable_goal(goal_id: str = typer.Argument(...)) -> None:
    """Enable a previously disabled goal."""
    _patch_goal(goal_id, {"enabled": True}, success="enabled")


@app.command("remove")
def remove_goal(goal_id: str = typer.Argument(...)) -> None:
    """Permanently remove a standing goal."""
    with _client() as client:
        response = client.delete(f"/api/v1/standing-goals/{goal_id}")
    if response.status_code == 404:
        console.print(f"[red]No standing goal {goal_id!r}[/red]")
        raise typer.Exit(1)
    if response.status_code not in (200, 204):
        console.print(f"[red]API returned {response.status_code}:[/red] {response.text}")
        raise typer.Exit(1)
    console.print(f"[green]Removed {goal_id}[/green]")


@app.command("run-now")
def run_now(goal_id: str = typer.Argument(...)) -> None:
    """Force an immediate LLM evaluation of one goal."""
    with _client() as client:
        response = client.post(f"/api/v1/standing-goals/{goal_id}/evaluate-now")
    if response.status_code == 404:
        console.print(f"[red]No standing goal {goal_id!r}[/red]")
        raise typer.Exit(1)
    if response.status_code == 503:
        console.print(
            "[yellow]No GoalEvaluatorService is registered. "
            "Start the butler daemon first.[/yellow]"
        )
        raise typer.Exit(1)
    if response.status_code not in (200, 202):
        console.print(f"[red]API returned {response.status_code}:[/red] {response.text}")
        raise typer.Exit(1)
    body = response.json()
    if body.get("acted"):
        console.print(
            f"[green]Submitted mission for {goal_id}.[/green] "
            f"[dim]{body.get('rationale', '')}[/dim]"
        )
    else:
        console.print(
            f"[yellow]No action for {goal_id}.[/yellow] "
            f"[dim]{body.get('rationale', '')}[/dim]"
        )


def _patch_goal(goal_id: str, patch: dict, *, success: str) -> None:
    with _client() as client:
        response = client.patch(f"/api/v1/standing-goals/{goal_id}", json=patch)
    if response.status_code == 404:
        console.print(f"[red]No standing goal {goal_id!r}[/red]")
        raise typer.Exit(1)
    if response.status_code != 200:
        console.print(f"[red]API returned {response.status_code}:[/red] {response.text}")
        raise typer.Exit(1)
    console.print(f"[green]{goal_id}: {success}[/green]")
