"""Memory management CLI commands.

Memory consolidation and experience tracking have been moved to agent packages.
This module provides a placeholder so that the CLI command group remains registered.
"""

import typer
from rich.console import Console

app = typer.Typer(help="Memory management")
console = Console()


@app.command("list")
def list_memories(
    ctx: typer.Context,
    profile: str = typer.Option(None, "--profile", "-p", help="Configuration profile"),
    limit: int = typer.Option(20, "--limit", "-n", help="Maximum entries to show"),
) -> None:
    """List stored long-term memories."""
    import asyncio

    global_opts = ctx.obj or {}
    profile = profile or global_opts.get("profile", "dev")

    async def _list() -> None:
        from taskforce.application.infrastructure_builder import InfrastructureBuilder
        from taskforce.application.profile_loader import ProfileLoader

        loader = ProfileLoader()
        config = loader.load(profile)
        memory_dir = config.get("persistence", {}).get("work_dir", ".taskforce")

        ib = InfrastructureBuilder()
        memory_store = ib.build_memory_store(memory_dir)
        memories = await memory_store.list()

        if not memories:
            console.print("[dim]No memories found.[/dim]")
            return

        from rich.table import Table

        table = Table(title=f"Long-Term Memories ({min(limit, len(memories))} shown)")
        table.add_column("ID", style="cyan", max_width=14)
        table.add_column("Kind", style="green")
        table.add_column("Content", style="white", max_width=60)

        for mem in memories[:limit]:
            mem_id = getattr(mem, "memory_id", str(mem)[:12])
            kind = getattr(mem, "kind", "unknown")
            content = getattr(mem, "content", str(mem))[:60]
            table.add_row(str(mem_id)[:12] + "...", str(kind), content)

        console.print(table)

    asyncio.run(_list())
