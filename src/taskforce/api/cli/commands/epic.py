"""Epic command - planner/worker/judge orchestration."""

import asyncio

import typer
from rich.console import Console

from taskforce.application.epic_orchestrator import EpicOrchestrator

app = typer.Typer(help="Run epic-scale orchestration")
console = Console()


@app.command("run")
def run_epic(
    ctx: typer.Context,
    mission: str = typer.Argument(..., help="Epic mission description"),
    planner_profile: str = typer.Option("planner", help="Planner profile"),
    worker_profile: str = typer.Option("worker", help="Worker profile"),
    judge_profile: str = typer.Option("judge", help="Judge profile"),
    workers: int = typer.Option(3, help="Number of worker agents"),
    rounds: int = typer.Option(3, help="Maximum epic rounds to attempt"),
    sub_planner_scopes: list[str] = typer.Option(
        None,
        "--scope",
        help="Optional sub-planner scope (repeatable)",
    ),
    auto_commit: bool = typer.Option(
        False,
        help="Allow judge agent to commit changes using git",
    ),
    commit_message: str | None = typer.Option(
        None,
        help="Commit message for judge agent (optional)",
    ),
) -> None:
    """Execute a planner -> worker -> judge epic flow."""
    _ = ctx
    _print_start_banner(mission, planner_profile, worker_profile, judge_profile)
    result = _execute_epic(
        mission=mission,
        planner_profile=planner_profile,
        worker_profile=worker_profile,
        judge_profile=judge_profile,
        workers=workers,
        rounds=rounds,
        sub_planner_scopes=sub_planner_scopes or [],
        auto_commit=auto_commit,
        commit_message=commit_message,
    )
    _print_summary(result)


def _execute_epic(
    *,
    mission: str,
    planner_profile: str,
    worker_profile: str,
    judge_profile: str,
    workers: int,
    rounds: int,
    sub_planner_scopes: list[str],
    auto_commit: bool,
    commit_message: str | None,
) -> object:
    orchestrator = EpicOrchestrator()
    return asyncio.run(
        orchestrator.run_epic(
            mission,
            planner_profile=planner_profile,
            worker_profile=worker_profile,
            judge_profile=judge_profile,
            worker_count=workers,
            max_rounds=rounds,
            sub_planner_scopes=sub_planner_scopes,
            auto_commit=auto_commit,
            commit_message=commit_message,
        )
    )


def _print_start_banner(
    mission: str,
    planner_profile: str,
    worker_profile: str,
    judge_profile: str,
) -> None:
    console.print(f"[bold]Epic mission:[/bold] {mission}")
    console.print(
        f"Planner={planner_profile}, Worker={worker_profile}, Judge={judge_profile}"
    )


def _print_summary(result: object) -> None:
    console.print("\n[bold]Epic completed[/bold]")
    console.print(f"Status: {getattr(result, 'status', 'unknown')}")
    console.print(f"Tasks: {len(getattr(result, 'tasks', []))}")
    console.print("\n[bold]Judge summary:[/bold]")
    console.print(getattr(result, "judge_summary", None) or "No summary")
