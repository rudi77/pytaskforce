"""Memory management CLI commands."""

import asyncio

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
    global_opts = ctx.obj or {}
    profile = profile or global_opts.get("profile", "dev")

    async def _list() -> None:
        from taskforce.application.infrastructure_builder import InfrastructureBuilder
        from taskforce.application.profile_loader import ProfileLoader
        from taskforce.application.tool_builder import ToolBuilder

        loader = ProfileLoader()
        config = loader.load(profile)
        memory_path = ToolBuilder.resolve_memory_store_dir(config)
        decay_enabled = bool(config.get("memory", {}).get("decay", {}).get("enabled", False))

        ib = InfrastructureBuilder()
        memory_store = ib.build_memory_store(memory_path, decay_enabled=decay_enabled)
        memories = await memory_store.list()

        if not memories:
            console.print("[dim]No memories found.[/dim]")
            return

        from rich.table import Table

        table = Table(title=f"Long-Term Memories ({min(limit, len(memories))} shown)")
        table.add_column("ID", style="cyan", max_width=14)
        table.add_column("Kind", style="green")
        table.add_column("Strength", style="yellow", justify="right")
        table.add_column("Content", style="white", max_width=60)

        for mem in memories[:limit]:
            mem_id = getattr(mem, "id", str(mem)[:12])
            kind = getattr(getattr(mem, "kind", None), "value", "unknown")
            eff = mem.effective_strength(decay_enabled=decay_enabled)
            content = getattr(mem, "content", str(mem))[:60]
            table.add_row(str(mem_id)[:12] + "...", str(kind), f"{eff:.2f}", content)

        console.print(table)

    asyncio.run(_list())


@app.command("consolidate")
def consolidate_memories(
    ctx: typer.Context,
    profile: str = typer.Option(None, "--profile", "-p", help="Configuration profile"),
    sessions: int = typer.Option(
        20, "--sessions", "-n", help="Maximum unprocessed sessions to consolidate"
    ),
    dry_run: bool = typer.Option(
        False, "--dry-run", help="Preview would-be changes without persisting"
    ),
    strategy: str = typer.Option(
        None, "--strategy", help="Override consolidation strategy (immediate|batch)"
    ),
) -> None:
    """Run memory consolidation manually.

    Processes unprocessed session experiences through the LLM consolidation
    pipeline.  Use ``--dry-run`` to preview the new memories before
    persisting them.
    """
    global_opts = ctx.obj or {}
    profile = profile or global_opts.get("profile", "dev")

    async def _run() -> None:
        from taskforce.application.consolidation_service import (
            build_consolidation_components,
        )
        from taskforce.application.infrastructure_builder import InfrastructureBuilder
        from taskforce.application.profile_loader import ProfileLoader

        loader = ProfileLoader()
        config = loader.load(profile)

        ib = InfrastructureBuilder()
        llm_provider = ib.build_llm_provider(config)
        tracker, service = build_consolidation_components(config, llm_provider)
        if service is None:
            console.print(
                "[yellow]Consolidation is not enabled for profile "
                f"'{profile}'.[/yellow] Set ``consolidation.enabled: true`` and "
                "``consolidation.auto_capture: true`` in the profile YAML."
            )
            raise typer.Exit(code=1)

        if dry_run:
            console.print("[bold yellow]DRY RUN[/bold yellow] — nothing will be persisted.\n")
        else:
            console.print(
                f"Running consolidation (profile=[cyan]{profile}[/cyan], "
                f"max sessions={sessions})..."
            )

        result = await service.trigger_consolidation(
            strategy=strategy,
            max_sessions=sessions,
            dry_run=dry_run,
        )

        if dry_run:
            _render_preview(result)
        else:
            _render_result(result, profile)

    asyncio.run(_run())


def _render_preview(result: object) -> None:
    from rich.table import Table

    preview = list(getattr(result, "preview_memories", []) or [])
    if not preview:
        console.print("[dim]Nothing to consolidate.[/dim]")
        return

    table = Table(title=f"Preview — {len(preview)} memories would be created")
    table.add_column("Kind", style="green")
    table.add_column("Tags", style="magenta")
    table.add_column("Content", style="white", max_width=72)

    for record in preview:
        kind = getattr(getattr(record, "kind", None), "value", "?")
        tags = ", ".join(getattr(record, "tags", []) or [])
        content = (getattr(record, "content", "") or "")[:72]
        table.add_row(kind, tags, content)

    console.print(table)
    console.print("\n[dim]Re-run without --dry-run to persist these memories.[/dim]")


def _render_result(result: object, profile: str) -> None:
    sessions_processed = getattr(result, "sessions_processed", 0)
    created = getattr(result, "memories_created", 0)
    updated = getattr(result, "memories_updated", 0)
    retired = getattr(result, "memories_retired", 0)
    quality = getattr(result, "quality_score", 0.0)

    if sessions_processed == 0:
        console.print("[dim]No unprocessed sessions found.[/dim]")
        return

    console.print(
        f"[green]Consolidation complete[/green] — "
        f"sessions: {sessions_processed}, created: {created}, "
        f"updated: {updated}, retired: {retired}, quality: {quality:.2f}"
    )
