"""Coding Agent CLI commands."""

import typer

app = typer.Typer(help="Coding agent - multi-agent orchestration")


@app.command("run")
def epic_run(
    ctx: typer.Context,
    mission: str = typer.Argument(..., help="Mission description for epic orchestration"),
    rounds: int = typer.Option(3, "--rounds", "-r", help="Number of refinement rounds"),
    profile: str = typer.Option("coding_agent", "--profile", "-p", help="Coding agent profile"),
) -> None:
    """Run an epic orchestration mission with planner/worker/reviewer agents."""
    import asyncio

    from taskforce.application.executor import AgentExecutor

    async def _run() -> None:
        executor = AgentExecutor()
        result = await executor.execute_mission(
            mission=mission,
            profile=profile,
        )
        typer.echo(f"Status: {result.status}")
        typer.echo(result.final_message)

    asyncio.run(_run())
