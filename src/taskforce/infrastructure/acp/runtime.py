"""Unified ACP runtime bundling server, client and peer registry."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

import structlog

from taskforce.core.domain.acp import AcpAgentManifest, AcpPeer, AcpRunHandle
from taskforce.core.interfaces.acp import (
    AcpClientProtocol,
    AcpPeerRegistryProtocol,
    AcpServerProtocol,
)
from taskforce.core.utils.time import utc_now
from taskforce.infrastructure.acp.acp_client import AcpClient
from taskforce.infrastructure.acp.acp_server import AcpServer
from taskforce.infrastructure.acp.peer_registry import InMemoryPeerRegistry

logger = structlog.get_logger(__name__)

AgentHandler = Callable[[list[Any], Any], Awaitable[Any]]


class AcpRuntime:
    """Lifecycle facade for the embedded ACP server plus client pool."""

    def __init__(
        self,
        *,
        server: AcpServerProtocol | None = None,
        client: AcpClientProtocol | None = None,
        peers: AcpPeerRegistryProtocol | None = None,
        host: str = "0.0.0.0",
        port: int = 8800,
        tenant_id_provider: Callable[[], str] | None = None,
    ) -> None:
        self._server: AcpServerProtocol = server or AcpServer(host=host, port=port)
        self._client: AcpClientProtocol = client or AcpClient()
        self._peers: AcpPeerRegistryProtocol = peers or InMemoryPeerRegistry()
        self._tenant_id_provider = tenant_id_provider
        self._started = False

    @property
    def server(self) -> AcpServerProtocol:
        return self._server

    @property
    def client(self) -> AcpClientProtocol:
        return self._client

    @property
    def peers(self) -> AcpPeerRegistryProtocol:
        return self._peers

    def register_agent(self, manifest: AcpAgentManifest, handler: AgentHandler) -> None:
        """Proxy to ``server.register_agent`` for convenience."""
        self._server.register_agent(manifest, handler)

    def register_peer(self, peer: AcpPeer) -> None:
        self._peers.register(peer)

    async def start(self) -> None:
        if self._started:
            return
        await self._server.start()
        self._started = True
        logger.info("acp.runtime.started")

    async def stop(self) -> None:
        if not self._started:
            return
        await self._server.stop()
        close = getattr(self._client, "close", None)
        if callable(close):
            try:
                await close()
            except Exception:  # pragma: no cover
                logger.warning("acp.runtime.client_close_failed", exc_info=True)
        self._started = False
        logger.info("acp.runtime.stopped")

    async def call(
        self,
        peer_name: str,
        mission: str,
        *,
        session_id: str | None = None,
        stream: bool = False,
        tenant_id: str | None = None,
    ) -> AcpRunHandle:
        peer = self._peers.get(peer_name)
        if peer is None:
            raise KeyError(f"Unknown ACP peer: {peer_name!r}")
        caller_tenant_id = tenant_id or self._current_tenant_id()
        if peer.tenant_id != caller_tenant_id:
            if not peer.allow_cross_tenant:
                raise PermissionError(
                    f"ACP peer {peer_name!r} is not reachable from tenant "
                    f"{caller_tenant_id!r}"
                )
            # ADR-022 §6: cross-tenant calls require explicit authorisation
            # on every call. The framework asks an installed authorizer
            # whether THIS caller may use this peer right now; on no
            # authorizer the legacy "allow_cross_tenant flag is sufficient"
            # behaviour is preserved.
            from taskforce.application.infrastructure_overrides import (
                get_cross_tenant_acp_authorizer,
            )

            authorizer = get_cross_tenant_acp_authorizer()
            if authorizer is not None and not authorizer(
                caller_tenant_id, peer.tenant_id, peer
            ):
                raise PermissionError(
                    f"Cross-tenant ACP call to {peer_name!r} denied by "
                    f"authorizer (caller tenant {caller_tenant_id!r}, peer "
                    f"tenant {peer.tenant_id!r})"
                )
        started_at = utc_now()
        if stream:
            status = "streamed"
            run_id = ""
            events: list[dict[str, Any]] = []
            async for event in self._client.run_stream(peer, mission, session_id=session_id):
                events.append(event)
                run_id = (
                    str(event.get("raw", {}).get("run_id", run_id))
                    if isinstance(event.get("raw"), dict)
                    else run_id
                )
            return AcpRunHandle(
                run_id=run_id,
                agent=peer.agent,
                peer=peer.name,
                status=status,
                started_at=started_at,
                result={"events": events, "output_text": _last_text(events)},
            )
        result = await self._client.run_sync(peer, mission, session_id=session_id)
        return AcpRunHandle(
            run_id=str(result.get("run_id", "")),
            agent=peer.agent,
            peer=peer.name,
            status=str(result.get("status", "completed")),
            started_at=started_at,
            result=result,
        )

    def _current_tenant_id(self) -> str:
        """Return caller tenant from host integration, falling back to default."""
        if self._tenant_id_provider is None:
            return "default"
        return self._tenant_id_provider() or "default"


def _last_text(events: list[dict[str, Any]]) -> str:
    for event in reversed(events):
        raw = event.get("raw")
        if isinstance(raw, dict):
            text = raw.get("output_text")
            if isinstance(text, str) and text:
                return text
    return ""
