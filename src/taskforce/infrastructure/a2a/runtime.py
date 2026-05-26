"""Unified A2A runtime bundling client and peer registry.

The server façade is added in Phase 3 of the A2A integration; until
then, :attr:`server` returns ``None`` and ``register_agent``/``start``/
``stop`` are no-ops with respect to the server side. The client + peer
registry path is fully functional so ``call_a2a_agent`` works.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import structlog

from taskforce.core.domain.a2a import A2aPeer, A2aPushConfig, A2aTaskHandle
from taskforce.core.interfaces.a2a import (
    A2aClientProtocol,
    A2aPeerRegistryProtocol,
    A2aServerProtocol,
)
from taskforce.infrastructure.a2a.a2a_client import A2aClient
from taskforce.infrastructure.a2a.peer_registry import InMemoryA2aPeerRegistry

logger = structlog.get_logger(__name__)


class A2aRuntime:
    """Lifecycle facade for the embedded A2A server plus client pool.

    Mirrors :class:`taskforce.infrastructure.acp.runtime.AcpRuntime` —
    same cross-tenant authorisation hook (ADR-022 §6), same
    server/client/peers triad.
    """

    def __init__(
        self,
        *,
        server: A2aServerProtocol | None = None,
        client: A2aClientProtocol | None = None,
        peers: A2aPeerRegistryProtocol | None = None,
        tenant_id_provider: Callable[[], str] | None = None,
    ) -> None:
        self._server: A2aServerProtocol | None = server
        self._client: A2aClientProtocol = client or A2aClient()
        self._peers: A2aPeerRegistryProtocol = peers or InMemoryA2aPeerRegistry()
        self._tenant_id_provider = tenant_id_provider
        self._started = False

    @property
    def server(self) -> A2aServerProtocol | None:
        return self._server

    @property
    def client(self) -> A2aClientProtocol:
        return self._client

    @property
    def peers(self) -> A2aPeerRegistryProtocol:
        return self._peers

    def register_peer(self, peer: A2aPeer) -> None:
        self._peers.register(peer)

    async def start(self) -> None:
        if self._started:
            return
        if self._server is not None:
            await self._server.start()
        self._started = True
        logger.info("a2a.runtime.started")

    async def stop(self) -> None:
        if not self._started:
            return
        if self._server is not None:
            await self._server.stop()
        close = getattr(self._client, "close", None)
        if callable(close):
            try:
                await close()
            except Exception:  # pragma: no cover - best-effort cleanup
                logger.warning("a2a.runtime.client_close_failed", exc_info=True)
        self._started = False
        logger.info("a2a.runtime.stopped")

    async def call(
        self,
        peer_name: str,
        mission: str,
        *,
        session_id: str | None = None,
        stream: bool = False,
        tenant_id: str | None = None,
        push: A2aPushConfig | None = None,
    ) -> A2aTaskHandle:
        peer = self._peers.get(peer_name)
        if peer is None:
            raise KeyError(f"Unknown A2A peer: {peer_name!r}")
        self._enforce_tenant(peer, tenant_id)
        if stream:
            return await self._call_stream(peer, mission, session_id, push)
        return await self._client.run_sync(peer, mission, session_id=session_id, push=push)

    async def _call_stream(
        self,
        peer: A2aPeer,
        mission: str,
        session_id: str | None,
        push: A2aPushConfig | None,
    ) -> A2aTaskHandle:
        events: list[dict[str, Any]] = []
        last_text = ""
        async for event in self._client.run_stream(peer, mission, session_id=session_id, push=push):
            events.append(event)
            raw = event.get("raw") if isinstance(event, dict) else None
            text = _last_text_from_raw(raw)
            if text:
                last_text = text
        from taskforce.core.domain.a2a import A2aTaskState

        return A2aTaskHandle(
            task_id="",
            peer=peer.name,
            state=A2aTaskState.COMPLETED if events else A2aTaskState.UNKNOWN,
            output_text=last_text,
            history=tuple(events),
        )

    def _enforce_tenant(self, peer: A2aPeer, tenant_id: str | None) -> None:
        caller_tenant_id = tenant_id or self._current_tenant_id()
        if peer.tenant_id == caller_tenant_id:
            return
        if not peer.allow_cross_tenant:
            raise PermissionError(
                f"A2A peer {peer.name!r} is not reachable from tenant " f"{caller_tenant_id!r}"
            )
        from taskforce.application.infrastructure_overrides import (
            get_cross_tenant_a2a_authorizer,
        )

        authorizer = get_cross_tenant_a2a_authorizer()
        if authorizer is not None and not authorizer(caller_tenant_id, peer.tenant_id, peer):
            raise PermissionError(
                f"Cross-tenant A2A call to {peer.name!r} denied by "
                f"authorizer (caller tenant {caller_tenant_id!r}, peer "
                f"tenant {peer.tenant_id!r})"
            )

    def _current_tenant_id(self) -> str:
        if self._tenant_id_provider is None:
            return "default"
        return self._tenant_id_provider() or "default"


def _last_text_from_raw(raw: Any) -> str:
    if not isinstance(raw, dict):
        return ""
    status_update = raw.get("status_update") or raw.get("statusUpdate") or {}
    if isinstance(status_update, dict):
        message = status_update.get("message") or {}
        if isinstance(message, dict):
            parts = message.get("parts") or []
            chunks = [p.get("text") for p in parts if isinstance(p, dict) and p.get("text")]
            if chunks:
                return "\n".join(chunks)
    message = raw.get("message") or {}
    if isinstance(message, dict):
        parts = message.get("parts") or []
        chunks = [p.get("text") for p in parts if isinstance(p, dict) and p.get("text")]
        if chunks:
            return "\n".join(chunks)
    return ""
