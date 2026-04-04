"""RAG Agent CLI commands."""

import typer

app = typer.Typer(help="RAG agent - document search and retrieval")


@app.command("search")
def rag_search(
    ctx: typer.Context,
    query: str = typer.Argument(..., help="Search query"),
    profile: str = typer.Option("rag_agent", "--profile", "-p", help="RAG agent profile"),
) -> None:
    """Run a RAG search mission."""
    import asyncio

    from taskforce.application.executor import AgentExecutor

    async def _run() -> None:
        executor = AgentExecutor()
        result = await executor.execute_mission(
            mission=query,
            profile=profile,
        )
        typer.echo(result.final_message)

    asyncio.run(_run())
