"""Runtimes command — list available agent runtimes.

Surfaces the entries in :mod:`taskforce.application.agent_runtime_registry`
so users can see which agent backends (Taskforce native, Hermes, OpenClaw,
…) are installed and selectable via a profile's ``runtime:`` field.
"""

from __future__ import annotations

import typer
from rich.console import Console
from rich.table import Table

from taskforce.application.agent_runtime_registry import (
    DEFAULT_RUNTIME,
    list_runtimes,
)

app = typer.Typer(help="Agent runtime management")
console = Console()


@app.command("list")
def list_runtimes_cmd() -> None:
    """List all registered agent runtimes."""
    names = list_runtimes()

    table = Table(title="Available Agent Runtimes")
    table.add_column("Name", style="cyan", no_wrap=True)
    table.add_column("Default", style="green")
    table.add_column("Description", style="white")

    descriptions = {
        "taskforce": "Native Taskforce agent (ReAct + tools + planning strategies)",
        "hermes": "Hermes agent runtime (foreign adapter)",
        "openclaw": "OpenClaw agent runtime (foreign adapter)",
    }

    for name in names:
        is_default = "yes" if name == DEFAULT_RUNTIME else ""
        description = descriptions.get(name, "Foreign agent runtime adapter")
        table.add_row(name, is_default, description)

    console.print(table)
    console.print(
        f"\n[dim]Profiles select a runtime via [bold]runtime: <name>[/bold] "
        f"(default: {DEFAULT_RUNTIME}).[/dim]"
    )
