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
    ) -> None:
        self._server: AcpServerProtocol = server or AcpServer(host=host, port=port)
        self._client: AcpClientProtocol = client or AcpClient()
        self._peers: AcpPeerRegistryProtocol = peers or InMemoryPeerRegistry()
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
    ) -> AcpRunHandle:
        peer = self._peers.get(peer_name)
        if peer is None:
            raise KeyError(f"Unknown ACP peer: {peer_name!r}")
        if stream:
            status = "streamed"
            run_id = ""
            async for event in self._client.run_stream(peer, mission, session_id=session_id):
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
                started_at=utc_now(),
            )
        result = await self._client.run_sync(peer, mission, session_id=session_id)
        return AcpRunHandle(
            run_id=str(result.get("run_id", "")),
            agent=peer.agent,
            peer=peer.name,
            status=str(result.get("status", "completed")),
            started_at=utc_now(),
        )
