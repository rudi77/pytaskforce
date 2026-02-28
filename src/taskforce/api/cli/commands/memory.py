"""Memory management CLI commands.

Provides commands for inspecting captured experiences, triggering
memory consolidation, and viewing consolidation statistics.
"""

import asyncio

import typer
from rich.console import Console
from rich.table import Table

app = typer.Typer(help="Memory management")
console = Console()


@app.command("consolidate")
def consolidate(
    ctx: typer.Context,
    profile: str = typer.Option(None, "--profile", "-p", help="Configuration profile"),
    strategy: str = typer.Option(
        "batch", "--strategy", "-s", help="Consolidation strategy (immediate|batch)"
    ),
    max_sessions: int = typer.Option(20, "--max-sessions", help="Maximum sessions to process"),
    dry_run: bool = typer.Option(
        False, "--dry-run", help="Show what would be consolidated without running"
    ),
) -> None:
    """Trigger memory consolidation of captured experiences."""
    global_opts = ctx.obj or {}
    profile = profile or global_opts.get("profile", "dev")

    async def _consolidate() -> None:
        from taskforce.application.consolidation_service import (
            build_consolidation_components,
        )
        from taskforce.application.profile_loader import ProfileLoader
        from taskforce.infrastructure.memory.file_experience_store import (
            FileExperienceStore,
        )

        loader = ProfileLoader()
        config = loader.load_profile(profile)

        if dry_run:
            work_dir = config.get("consolidation", {}).get("work_dir", ".taskforce/experiences")
            store = FileExperienceStore(work_dir)
            experiences = await store.list_experiences(limit=max_sessions, unprocessed_only=True)
            console.print(f"[bold]Dry run:[/bold] {len(experiences)} unprocessed experiences found")
            for exp in experiences:
                console.print(
                    f"  - {exp.session_id[:12]}... " f"({exp.profile}) {exp.mission[:60]}"
                )
            return

        # Build LLM provider for consolidation
        from taskforce.application.infrastructure_builder import InfrastructureBuilder

        ib = InfrastructureBuilder()
        llm_provider = ib.build_llm_provider(config)

        tracker, service = build_consolidation_components(config, llm_provider)
        if service is None:
            console.print(
                "[yellow]Consolidation is not enabled in this profile.[/yellow]\n"
                "Add 'consolidation.enabled: true' to your profile YAML."
            )
            return

        console.print(f"[bold]Running {strategy} consolidation...[/bold]")
        result = await service.trigger_consolidation(strategy=strategy, max_sessions=max_sessions)

        table = Table(title="Consolidation Result")
        table.add_column("Metric", style="cyan")
        table.add_column("Value", style="white")
        table.add_row("Consolidation ID", result.consolidation_id[:12] + "...")
        table.add_row("Sessions processed", str(result.sessions_processed))
        table.add_row("Memories created", str(result.memories_created))
        table.add_row("Memories updated", str(result.memories_updated))
        table.add_row("Memories retired", str(result.memories_retired))
        table.add_row("Contradictions resolved", str(result.contradictions_resolved))
        table.add_row("Quality score", f"{result.quality_score:.2f}")
        table.add_row("Total tokens", str(result.total_tokens))
        console.print(table)

    asyncio.run(_consolidate())


@app.command("experiences")
def experiences(
    ctx: typer.Context,
    profile: str = typer.Option(None, "--profile", "-p", help="Configuration profile"),
    limit: int = typer.Option(20, "--limit", "-n", help="Maximum entries to show"),
    unprocessed: bool = typer.Option(
        False, "--unprocessed", "-u", help="Show only unprocessed experiences"
    ),
) -> None:
    """List captured session experiences."""
    global_opts = ctx.obj or {}
    profile = profile or global_opts.get("profile", "dev")

    async def _list() -> None:
        from taskforce.application.profile_loader import ProfileLoader
        from taskforce.infrastructure.memory.file_experience_store import (
            FileExperienceStore,
        )

        loader = ProfileLoader()
        config = loader.load_profile(profile)
        work_dir = config.get("consolidation", {}).get("work_dir", ".taskforce/experiences")

        store = FileExperienceStore(work_dir)
        exps = await store.list_experiences(limit=limit, unprocessed_only=unprocessed)

        if not exps:
            console.print("[dim]No experiences found.[/dim]")
            return

        table = Table(title=f"Session Experiences ({len(exps)} shown)")
        table.add_column("Session", style="cyan", max_width=14)
        table.add_column("Profile", style="green")
        table.add_column("Mission", style="white", max_width=50)
        table.add_column("Steps", style="yellow", justify="right")
        table.add_column("Tools", style="yellow", justify="right")
        table.add_column("Processed", style="dim")

        for exp in exps:
            table.add_row(
                exp.session_id[:12] + "...",
                exp.profile,
                exp.mission[:50],
                str(exp.total_steps),
                str(len(exp.tool_calls)),
                "yes" if exp.processed_by else "no",
            )

        console.print(table)

    asyncio.run(_list())


@app.command("stats")
def stats(
    ctx: typer.Context,
    profile: str = typer.Option(None, "--profile", "-p", help="Configuration profile"),
) -> None:
    """Show memory and consolidation statistics."""
    global_opts = ctx.obj or {}
    profile = profile or global_opts.get("profile", "dev")

    async def _stats() -> None:
        from taskforce.application.profile_loader import ProfileLoader
        from taskforce.infrastructure.memory.file_experience_store import (
            FileExperienceStore,
        )
        from taskforce.infrastructure.memory.file_memory_store import FileMemoryStore

        loader = ProfileLoader()
        config = loader.load_profile(profile)
        work_dir = config.get("consolidation", {}).get("work_dir", ".taskforce/experiences")
        memory_dir = config.get("persistence", {}).get("work_dir", ".taskforce")

        store = FileExperienceStore(work_dir)
        memory_store = FileMemoryStore(memory_dir)

        all_exps = await store.list_experiences(limit=1000)
        unprocessed = [e for e in all_exps if not e.processed_by]
        consolidations = await store.list_consolidations(limit=100)
        all_memories = await memory_store.list()

        from taskforce.core.domain.memory import MemoryKind

        consolidated = [m for m in all_memories if m.kind == MemoryKind.CONSOLIDATED]

        table = Table(title="Memory Statistics")
        table.add_column("Metric", style="cyan")
        table.add_column("Value", style="white")
        table.add_row("Total experiences", str(len(all_exps)))
        table.add_row("Unprocessed experiences", str(len(unprocessed)))
        table.add_row("Consolidation runs", str(len(consolidations)))
        table.add_row("Total memories", str(len(all_memories)))
        table.add_row("Consolidated memories", str(len(consolidated)))

        if consolidations:
            latest = consolidations[0]
            table.add_row(
                "Latest consolidation",
                f"{latest.consolidation_id[:12]}... " f"(quality: {latest.quality_score:.2f})",
            )

        console.print(table)

    asyncio.run(_stats())
