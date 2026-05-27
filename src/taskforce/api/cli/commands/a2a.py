"""A2A (Agent-to-Agent protocol) CLI commands."""

from __future__ import annotations

import asyncio
import json
from typing import Any

import typer
from rich.console import Console
from rich.table import Table

from taskforce.application.a2a_service import build_a2a_service
from taskforce.application.config_schema import A2aConfigSchema
from taskforce.core.domain.a2a import A2aAuth, A2aAuthType, A2aPeer, A2aTransport
from taskforce.infrastructure.a2a.peer_registry import FileA2aPeerRegistry

app = typer.Typer(help="Agent-to-Agent (A2A) protocol management")
peers_app = typer.Typer(help="Manage configured A2A peers")
app.add_typer(peers_app, name="peers")

console = Console()


def _load_a2a_config(profile_name: str) -> A2aConfigSchema | None:
    from taskforce.application.infrastructure_builder import InfrastructureBuilder

    builder = InfrastructureBuilder()
    profile = builder.load_profile(profile_name)
    raw = profile.get("a2a")
    if not raw:
        return None
    return A2aConfigSchema(**raw)


def _build_profile_handler(profile_name: str) -> Any:
    """Build an A2A mission handler that runs a Taskforce mission per call."""
    from taskforce.application.executor import AgentExecutor

    executor = AgentExecutor()

    async def _handler(mission: str, session_id: str | None) -> str:
        result = await executor.execute_mission(mission=mission, profile=profile_name)
        return getattr(result, "final_message", None) or str(result)

    return _handler


@app.command("start")
def start(
    ctx: typer.Context,
    profile: str = typer.Option(None, "--profile", "-p"),
    host: str | None = typer.Option(None, "--host"),
    port: int | None = typer.Option(None, "--port"),
) -> None:
    """Start the A2A server in the foreground."""
    global_opts = ctx.obj or {}
    profile = profile or global_opts.get("profile", "dev")
    config = _load_a2a_config(profile)
    if config is None:
        console.print(
            f"[yellow]Profile {profile!r} has no 'a2a' section; add one to enable A2A.[/yellow]"
        )
        raise typer.Exit(code=1)
    if host:
        config.server.host = host
    if port:
        config.server.port = port
    config.server.enabled = True

    service = build_a2a_service(config)
    if service is None:
        raise typer.Exit(code=1)
    if config.server.expose_profile:
        handler = _build_profile_handler(profile)
        service.register_profile_agent(
            handler,
            profile_name=profile,
            description=f"Taskforce profile {profile!r} exposed via A2A",
        )

    async def _run() -> None:
        await service.start()
        await service.runtime.server.wait_started(timeout=10.0)
        agent_name = config.server.agent_name or profile
        console.print(
            f"[green]A2A server listening on "
            f"{config.server.host}:{config.server.port} (agent: {agent_name!r})[/green]"
        )
        console.print(
            f"[dim]Agent card: http://{config.server.host}:{config.server.port}"
            f"/.well-known/agent-card.json[/dim]"
        )
        console.print("[dim]Press Ctrl+C to stop.[/dim]")
        try:
            while True:
                await asyncio.sleep(3600)
        finally:
            await service.stop()

    try:
        asyncio.run(_run())
    except KeyboardInterrupt:
        console.print("[yellow]Shutting down A2A server...[/yellow]")


@app.command("status")
def status(
    ctx: typer.Context,
    profile: str = typer.Option(None, "--profile", "-p"),
) -> None:
    """Show A2A server configuration and configured peers."""
    global_opts = ctx.obj or {}
    profile = profile or global_opts.get("profile", "dev")
    config = _load_a2a_config(profile)
    if config is None:
        console.print(f"[yellow]Profile {profile!r} has no A2A configuration.[/yellow]")
        return
    service = build_a2a_service(config)
    assert service is not None
    console.print(f"[bold]Profile:[/bold] {profile}")
    console.print(
        f"[bold]Server:[/bold] enabled={config.server.enabled} "
        f"host={config.server.host} port={config.server.port} "
        f"agent_name={config.server.agent_name or '(profile)'}"
    )
    console.print(
        f"[bold]Push:[/bold] enabled={config.push.enabled} "
        f"callback={config.push.public_callback_url or '(derived)'}"
    )
    _render_peers(service.list_peers())


@app.command("card")
def card(
    ctx: typer.Context,
    profile: str = typer.Option(None, "--profile", "-p"),
) -> None:
    """Print the AgentCard that this profile would publish over A2A."""
    from google.protobuf.json_format import MessageToJson

    from taskforce.infrastructure.a2a.agent_card_builder import build_agent_card

    global_opts = ctx.obj or {}
    profile = profile or global_opts.get("profile", "dev")
    config = _load_a2a_config(profile)
    if config is None:
        console.print(f"[yellow]Profile {profile!r} has no A2A configuration.[/yellow]")
        raise typer.Exit(code=1)
    from taskforce.application.a2a_service import _resolve_advertised_base_url
    from taskforce.application.infrastructure_builder import InfrastructureBuilder

    builder = InfrastructureBuilder()
    profile_dict = builder.load_profile(profile)
    tools = [t for t in profile_dict.get("tools", []) if isinstance(t, str)]
    base_url = _resolve_advertised_base_url(config.server)
    card_proto = build_agent_card(
        profile_name=profile,
        description=str(profile_dict.get("description", "")),
        base_url=base_url,
        server_config=config.server,
        tools=tools,
    )
    console.print_json(MessageToJson(card_proto, preserving_proto_field_name=True))


@peers_app.command("list")
def peers_list(
    ctx: typer.Context,
    profile: str | None = typer.Option(None, "--profile", "-p"),
) -> None:
    """List configured A2A peers (profile + on-disk registry merged)."""
    from_profile: list[A2aPeer] = []
    if profile or (ctx.obj or {}).get("profile"):
        cfg = _load_a2a_config(profile or ctx.obj["profile"])
        if cfg is not None:
            service = build_a2a_service(cfg)
            assert service is not None
            from_profile = service.list_peers()
    else:
        from_profile = FileA2aPeerRegistry().list()
    _render_peers(from_profile)


@peers_app.command("add")
def peers_add(
    name: str = typer.Argument(...),
    base_url: str = typer.Option(..., "--base-url"),
    description: str = typer.Option("", "--description"),
    auth_type: str = typer.Option(
        "none", "--auth-type", help="none/bearer/api_key/oauth2/oidc/mtls"
    ),
    token_env: str | None = typer.Option(None, "--token-env"),
    provider: str | None = typer.Option(None, "--provider", help="OAuth2/OIDC provider id"),
    scopes: str | None = typer.Option(None, "--scopes", help="Comma-separated OAuth2 scopes"),
) -> None:
    """Add a peer to the on-disk registry (``.taskforce/a2a_peers.json``)."""
    registry = FileA2aPeerRegistry()
    auth = A2aAuth(
        type=A2aAuthType(auth_type),
        token_env=token_env,
        provider=provider,
        scopes=tuple(s.strip() for s in scopes.split(",")) if scopes else (),
    )
    registry.register(
        A2aPeer(
            name=name,
            base_url=base_url,
            description=description,
            auth=auth,
            preferred_transport=A2aTransport.JSON_RPC,
        )
    )
    console.print(f"[green]Registered A2A peer {name!r} -> {base_url}[/green]")


@peers_app.command("remove")
def peers_remove(name: str = typer.Argument(...)) -> None:
    """Remove a peer from the on-disk registry."""
    FileA2aPeerRegistry().remove(name)
    console.print(f"[green]Removed A2A peer {name!r}[/green]")


@peers_app.command("test")
def peers_test(name: str = typer.Argument(...)) -> None:
    """Probe a peer's ``/.well-known/agent-card.json``."""
    from taskforce.application.a2a_service import ping_peer

    result = asyncio.run(ping_peer(name))
    console.print(json.dumps(result, indent=2, default=str))


@app.command("call")
def call(
    ctx: typer.Context,
    peer_name: str = typer.Argument(...),
    mission: str = typer.Argument(...),
    profile: str = typer.Option(None, "--profile", "-p"),
    stream: bool = typer.Option(False, "--stream"),
    session_id: str | None = typer.Option(None, "--session-id"),
) -> None:
    """Call a remote A2A agent by peer name."""
    global_opts = ctx.obj or {}
    profile = profile or global_opts.get("profile", "dev")
    config = _load_a2a_config(profile)
    if config is None:
        config = A2aConfigSchema()
    service = build_a2a_service(config)
    assert service is not None

    async def _invoke() -> None:
        peer = service.runtime.peers.get(peer_name)
        if peer is None:
            fallback = FileA2aPeerRegistry().get(peer_name)
            if fallback is None:
                console.print(f"[red]Unknown peer: {peer_name!r}[/red]")
                raise typer.Exit(code=1)
            service.runtime.peers.register(fallback)
        peer = service.runtime.peers.get(peer_name)
        try:
            if stream:
                async for event in service.runtime.client.run_stream(
                    peer, mission, session_id=session_id
                ):
                    console.print(event)
            else:
                handle = await service.runtime.client.run_sync(peer, mission, session_id=session_id)
                console.print(
                    {
                        "state": handle.state.value,
                        "task_id": handle.task_id,
                        "output_text": handle.output_text,
                        "artifacts": [
                            {"name": a.name, "path": a.path, "size": a.size}
                            for a in handle.artifacts
                        ],
                    }
                )
        finally:
            await service.stop()

    asyncio.run(_invoke())


def _render_peers(peers: list[A2aPeer]) -> None:
    if not peers:
        console.print("[yellow]No A2A peers configured.[/yellow]")
        return
    table = Table(title="A2A Peers")
    table.add_column("Name", style="cyan")
    table.add_column("Base URL")
    table.add_column("Auth")
    table.add_column("Transport")
    for peer in peers:
        auth = peer.auth.type.value
        if peer.auth.type == A2aAuthType.OAUTH2 and peer.auth.provider:
            auth = f"oauth2({peer.auth.provider})"
        elif peer.auth.type == A2aAuthType.BEARER and peer.auth.token_env:
            auth = f"bearer({peer.auth.token_env})"
        elif peer.auth.type == A2aAuthType.API_KEY:
            auth = f"api_key({peer.auth.api_key_header or 'X-API-Key'})"
        table.add_row(peer.name, peer.base_url, auth, peer.preferred_transport.value)
    console.print(table)
