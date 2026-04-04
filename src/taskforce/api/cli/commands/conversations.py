"""Conversations command — Manage persistent agent conversations (ADR-016)."""

import asyncio

import typer
from rich.console import Console
from rich.table import Table

app = typer.Typer(help="Conversation management (persistent agent)")
console = Console()


def _get_conversation_manager():
    """Lazily build a ConversationManager backed by file storage."""
    import os

    from taskforce.application.conversation_manager import ConversationManager
    from taskforce.infrastructure.persistence.file_conversation_store import (
        FileConversationStore,
    )

    work_dir = os.getenv("TASKFORCE_WORK_DIR", ".taskforce")
    store = FileConversationStore(work_dir=work_dir)
    return ConversationManager(store)


@app.command("list")
def list_conversations(
    archived: bool = typer.Option(
        False, "--archived", "-a", help="Show archived conversations instead of active"
    ),
    limit: int = typer.Option(20, "--limit", "-n", help="Max items to show"),
):
    """List active or archived conversations."""

    async def _list():
        mgr = _get_conversation_manager()

        if archived:
            items = await mgr.list_archived(limit=limit)
            table = Table(title="Archived Conversations")
            table.add_column("ID", style="cyan", no_wrap=True)
            table.add_column("Topic", style="white")
            table.add_column("Messages", justify="right")
            table.add_column("Archived", style="dim")
            for s in items:
                table.add_row(
                    s.conversation_id,
                    s.topic or "—",
                    str(s.message_count),
                    s.archived_at.strftime("%Y-%m-%d %H:%M"),
                )
        else:
            items = await mgr.list_active()
            table = Table(title="Active Conversations")
            table.add_column("ID", style="cyan", no_wrap=True)
            table.add_column("Channel", style="green")
            table.add_column("Topic", style="white")
            table.add_column("Messages", justify="right")
            table.add_column("Last Activity", style="dim")
            for c in items[:limit]:
                table.add_row(
                    c.conversation_id,
                    c.channel,
                    c.topic or "—",
                    str(c.message_count),
                    c.last_activity.strftime("%Y-%m-%d %H:%M"),
                )

        if not items:
            console.print("[dim]No conversations found.[/dim]")
        else:
            console.print(table)

    asyncio.run(_list())


@app.command("show")
def show_conversation(
    conversation_id: str = typer.Argument(..., help="Conversation ID"),
    limit: int = typer.Option(50, "--limit", "-n", help="Max messages to show"),
):
    """Show messages in a conversation."""

    async def _show():
        mgr = _get_conversation_manager()
        messages = await mgr.get_messages(conversation_id, limit=limit)

        if not messages:
            console.print(f"[red]No messages found for '{conversation_id}'[/red]")
            raise typer.Exit(1)

        console.print(f"\n[bold]Conversation:[/bold] {conversation_id}")
        console.print(f"[bold]Messages:[/bold] {len(messages)}\n")

        for msg in messages:
            role = msg.get("role", "unknown")
            content = msg.get("content", "")
            if role == "user":
                console.print(f"[bold blue]User:[/bold blue] {content}")
            elif role == "assistant":
                console.print(f"[bold green]Assistant:[/bold green] {content}")
            else:
                console.print(f"[dim]{role}:[/dim] {content}")

    asyncio.run(_show())


@app.command("archive")
def archive_conversation(
    conversation_id: str = typer.Argument(..., help="Conversation ID to archive"),
    summary: str | None = typer.Option(None, "--summary", "-s", help="Archive summary"),
):
    """Archive a conversation."""

    async def _archive():
        mgr = _get_conversation_manager()
        await mgr.archive(conversation_id, summary=summary)
        console.print(f"[green]Conversation '{conversation_id}' archived.[/green]")

    asyncio.run(_archive())
