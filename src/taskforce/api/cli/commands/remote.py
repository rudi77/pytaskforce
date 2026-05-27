"""Cross-protocol remote-agent CLI (``taskforce remote ...``).

The Hybrid discovery facade — unifies ACP and A2A peer enumeration
into a single read-only view. Invocation paths stay protocol-specific
(``taskforce acp call`` / ``taskforce a2a call``); this surface only
discovers and lists.
"""

from __future__ import annotations

import asyncio
import json

import typer
from rich.console import Console
from rich.table import Table

from taskforce.application.remote_agent_discovery_service import (
    RemoteAgentDiscoveryService,
)

app = typer.Typer(help="Cross-protocol remote-agent discovery (ACP + A2A)")
console = Console()


@app.command("peers")
def peers(
    probe: bool = typer.Option(
        False, "--probe", help="Network-check each peer (slower, populates reachable + latency)"
    ),
) -> None:
    """List configured remote-agent peers across ACP and A2A."""
    service = RemoteAgentDiscoveryService()
    descriptors = service.list_peers(probe=probe)
    if not descriptors:
        console.print("[yellow]No remote-agent peers configured.[/yellow]")
        return
    table = Table(title="Remote Agents (ACP + A2A)")
    table.add_column("Name", style="cyan")
    table.add_column("Protocol", style="green")
    table.add_column("Base URL")
    table.add_column("Auth")
    table.add_column("Reachable")
    table.add_column("Latency")
    for d in descriptors:
        reachable = "" if d.reachable is None else ("✓" if d.reachable else "✗")
        latency = f"{d.latency_ms}ms" if d.latency_ms is not None else ""
        auth = ",".join(d.auth_schemes) or "none"
        table.add_row(d.name, d.protocol.value, d.base_url, auth, reachable, latency)
    console.print(table)


@app.command("discover")
def discover(base_url: str = typer.Argument(...)) -> None:
    """Probe a URL — ACP-or-A2A auto-detection.

    Tries ``/.well-known/agent-card.json`` first (A2A spec), falls
    back to ACP ``/agents`` listing.
    """
    service = RemoteAgentDiscoveryService()
    result = asyncio.run(service.discover(base_url))
    if result is None:
        console.print(f"[yellow]No ACP or A2A endpoint found at {base_url!r}.[/yellow]")
        raise typer.Exit(code=1)
    payload = {
        "name": result.name,
        "protocol": result.protocol.value,
        "base_url": result.base_url,
        "agent": result.agent,
        "description": result.description,
        "capabilities": list(result.capabilities),
        "auth_schemes": list(result.auth_schemes),
        "reachable": result.reachable,
        "latency_ms": result.latency_ms,
    }
    console.print_json(json.dumps(payload, default=str))
