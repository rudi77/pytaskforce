"""ACP (Agent Communication Protocol) CLI commands."""

from __future__ import annotations

import asyncio
from typing import Any

import typer
from rich.console import Console
from rich.table import Table

from taskforce.application.acp_service import build_acp_service
from taskforce.application.config_schema import AcpConfigSchema
from taskforce.core.domain.acp import AcpAuth, AcpAuthType, AcpPeer
from taskforce.infrastructure.acp.peer_registry import FilePeerRegistry

app = typer.Typer(help="Agent Communication Protocol management")
peers_app = typer.Typer(help="Manage configured ACP peers")
app.add_typer(peers_app, name="peers")

console = Console()


def _load_acp_config(profile_name: str) -> AcpConfigSchema | None:
    from taskforce.application.infrastructure_builder import InfrastructureBuilder

    builder = InfrastructureBuilder()
    profile = builder.load_profile(profile_name)
    raw = profile.get("acp")
    if not raw:
        return None
    return AcpConfigSchema(**raw)


@app.command("start")
def start(
    ctx: typer.Context,
    profile: str = typer.Option(None, "--profile", "-p"),
    host: str | None = typer.Option(None, "--host"),
    port: int | None = typer.Option(None, "--port"),
) -> None:
    """Start the ACP server in the foreground."""
    global_opts = ctx.obj or {}
    profile = profile or global_opts.get("profile", "dev")
    config = _load_acp_config(profile)
    if config is None:
        console.print(
            f"[yellow]Profile {profile!r} has no 'acp' section; " "add one to enable ACP.[/yellow]"
        )
        raise typer.Exit(code=1)
    if host:
        config.server.host = host
    if port:
        config.server.port = port
    config.server.enabled = True

    service = build_acp_service(config)
    if service is None:
        raise typer.Exit(code=1)

    async def _run() -> None:
        await service.start()
        console.print(
            f"[green]ACP server listening on " f"{config.server.host}:{config.server.port}[/green]"
        )
        try:
            while True:
                await asyncio.sleep(3600)
        finally:
            await service.stop()

    try:
        asyncio.run(_run())
    except KeyboardInterrupt:
        console.print("[yellow]Shutting down ACP server...[/yellow]")


@app.command("status")
def status(
    ctx: typer.Context,
    profile: str = typer.Option(None, "--profile", "-p"),
) -> None:
    """Show ACP server configuration and registered peers for a profile."""
    global_opts = ctx.obj or {}
    profile = profile or global_opts.get("profile", "dev")
    config = _load_acp_config(profile)
    if config is None:
        console.print(f"[yellow]Profile {profile!r} has no ACP configuration.[/yellow]")
        return
    service = build_acp_service(config)
    assert service is not None
    console.print(f"[bold]Profile:[/bold] {profile}")
    console.print(
        f"[bold]Server:[/bold] enabled={config.server.enabled} "
        f"host={config.server.host} port={config.server.port} "
        f"agent_name={config.server.agent_name or '(profile)'}"
    )
    console.print(
        f"[bold]Message bus:[/bold] transport={config.message_bus.transport} "
        f"publish_peers={config.message_bus.publish_peers} "
        f"subscribe_topics={config.message_bus.subscribe_topics}"
    )
    _render_peers(service.list_peers())


@peers_app.command("list")
def peers_list(
    ctx: typer.Context,
    profile: str | None = typer.Option(None, "--profile", "-p"),
) -> None:
    """List configured ACP peers (profile + on-disk registry merged)."""
    from_profile: list[AcpPeer] = []
    if profile or (ctx.obj or {}).get("profile"):
        cfg = _load_acp_config(profile or ctx.obj["profile"])
        if cfg is not None:
            service = build_acp_service(cfg)
            assert service is not None
            from_profile = service.list_peers()
    else:
        from_profile = FilePeerRegistry().list()
    _render_peers(from_profile)


@peers_app.command("add")
def peers_add(
    name: str = typer.Argument(...),
    base_url: str = typer.Option(..., "--base-url"),
    agent: str = typer.Option(..., "--agent"),
    description: str = typer.Option("", "--description"),
    token_env: str | None = typer.Option(None, "--token-env", help="ENV var holding bearer token"),
) -> None:
    """Add a peer to the on-disk registry (".taskforce/acp_peers.json")."""
    registry = FilePeerRegistry()
    auth = AcpAuth(
        type=AcpAuthType.BEARER if token_env else AcpAuthType.NONE,
        token_env=token_env,
    )
    registry.register(
        AcpPeer(
            name=name,
            base_url=base_url,
            agent=agent,
            description=description,
            auth=auth,
        )
    )
    console.print(f"[green]Registered peer {name!r} -> {base_url}[/green]")


@peers_app.command("remove")
def peers_remove(name: str = typer.Argument(...)) -> None:
    """Remove a peer from the on-disk registry."""
    registry = FilePeerRegistry()
    registry.remove(name)
    console.print(f"[green]Removed peer {name!r}[/green]")


@app.command("call")
def call(
    ctx: typer.Context,
    peer_name: str = typer.Argument(...),
    mission: str = typer.Argument(...),
    profile: str = typer.Option(None, "--profile", "-p"),
    stream: bool = typer.Option(False, "--stream"),
    session_id: str | None = typer.Option(None, "--session-id"),
) -> None:
    """Call a remote ACP agent by peer name."""
    global_opts = ctx.obj or {}
    profile = profile or global_opts.get("profile", "dev")
    config = _load_acp_config(profile)
    if config is None:
        config = AcpConfigSchema()
    service = build_acp_service(config)
    assert service is not None

    async def _invoke() -> None:
        peer = service.runtime.peers.get(peer_name)
        if peer is None:
            # Fall back to the on-disk registry outside the profile.
            fallback = FilePeerRegistry().get(peer_name)
            if fallback is None:
                console.print(f"[red]Unknown peer: {peer_name!r}[/red]")
                raise typer.Exit(code=1)
            service.runtime.peers.register(fallback)
        result: Any
        if stream:
            events: list[dict[str, Any]] = []
            async for event in service.runtime.client.run_stream(
                service.runtime.peers.get(peer_name),  # type: ignore[arg-type]
                mission,
                session_id=session_id,
            ):
                events.append(event)
                console.print(event)
            result = events
        else:
            result = await service.runtime.client.run_sync(
                service.runtime.peers.get(peer_name),  # type: ignore[arg-type]
                mission,
                session_id=session_id,
            )
            console.print(result)
        await service.stop()

    asyncio.run(_invoke())


def _render_peers(peers: list[AcpPeer]) -> None:
    if not peers:
        console.print("[yellow]No peers configured.[/yellow]")
        return
    table = Table(title="ACP Peers")
    table.add_column("Name", style="cyan")
    table.add_column("Agent", style="green")
    table.add_column("Base URL")
    table.add_column("Auth")
    for peer in peers:
        auth = peer.auth.type.value
        if peer.auth.type == AcpAuthType.BEARER:
            auth = f"bearer({peer.auth.token_env or '<inline>'})"
        table.add_row(peer.name, peer.agent, peer.base_url, auth)
    console.print(table)
