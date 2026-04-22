"""Wiki (long-term memory) CLI commands.

Backwards-compatible module name — the commands exposed are now
``taskforce wiki list`` and ``taskforce wiki show <name>``.
"""

import asyncio

import typer
from rich.console import Console
from rich.markdown import Markdown
from rich.table import Table

app = typer.Typer(help="Wiki (long-term memory) management")
console = Console()


def _load_store(profile: str):
    from taskforce.application.infrastructure_builder import InfrastructureBuilder
    from taskforce.application.profile_loader import ProfileLoader
    from taskforce.application.tool_builder import ToolBuilder

    config = ProfileLoader().load(profile)
    wiki_dir = ToolBuilder.resolve_wiki_store_dir(config)
    # `build_wiki_store` accepts the work_dir form, but we already have the
    # resolved wiki root — construct FileWikiStore directly.
    from taskforce.infrastructure.memory.file_wiki_store import FileWikiStore

    _ = InfrastructureBuilder  # keep reference for symmetry with other commands
    return FileWikiStore(wiki_dir)


@app.command("list")
def list_pages(
    ctx: typer.Context,
    profile: str = typer.Option(None, "--profile", "-p", help="Configuration profile"),
    limit: int = typer.Option(50, "--limit", "-n", help="Maximum pages to show"),
) -> None:
    """List wiki pages."""
    profile = profile or (ctx.obj or {}).get("profile", "dev")

    async def _run() -> None:
        store = _load_store(profile)
        pages = await store.list_pages()
        if not pages:
            console.print("[dim]Wiki is empty.[/dim]")
            return
        table = Table(title=f"Wiki pages — {len(pages)} total")
        table.add_column("Name", style="cyan")
        table.add_column("Title", style="white")
        table.add_column("Kind", style="green")
        table.add_column("Updated", style="dim")
        for page in pages[:limit]:
            table.add_row(
                page.name,
                page.title,
                page.kind,
                page.updated_at.isoformat()[:19],
            )
        console.print(table)

    asyncio.run(_run())


@app.command("show")
def show_page(
    ctx: typer.Context,
    name: str = typer.Argument(help="Page path (e.g. entities/steuerberater-mueller)"),
    profile: str = typer.Option(None, "--profile", "-p", help="Configuration profile"),
) -> None:
    """Print a wiki page's contents."""
    profile = profile or (ctx.obj or {}).get("profile", "dev")

    async def _run() -> None:
        store = _load_store(profile)
        page = await store.get_page(name)
        if page is None:
            console.print(f"[red]Page not found:[/red] {name}")
            raise typer.Exit(code=1)
        console.rule(f"[bold]{page.title}[/bold] ({page.name})")
        console.print(Markdown(page.body))

    asyncio.run(_run())


@app.command("lint")
def lint(
    ctx: typer.Context,
    profile: str = typer.Option(None, "--profile", "-p", help="Configuration profile"),
) -> None:
    """Run wiki health checks (orphans, duplicate titles, broken links)."""
    profile = profile or (ctx.obj or {}).get("profile", "dev")

    async def _run() -> None:
        from taskforce.application.wiki_lint_service import lint_wiki

        store = _load_store(profile)
        report = await lint_wiki(store)
        if report.is_clean:
            console.print("[green]Wiki is clean — no issues found.[/green]")
            return
        for issue in report.issues:
            console.print(f"- [{issue.kind}] {issue.message}")

    asyncio.run(_run())
