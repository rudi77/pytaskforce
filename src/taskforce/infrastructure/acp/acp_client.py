"""Outbound ACP client implementation."""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

import structlog

from taskforce.core.domain.acp import AcpAgentManifest, AcpAuthType, AcpPeer
from taskforce.infrastructure.acp._sdk import load_client, load_models

logger = structlog.get_logger(__name__)


class AcpClient:
    """ACP client built on ``acp_sdk.client.Client`` with a per-peer pool.

    ``acp-sdk`` sessions are managed via the ``client.session(session)``
    context manager; callers provide an opaque ``session_id`` which we map
    to a cached session-scoped sub-client. When no ``session_id`` is
    provided, the base (stateless) client is used.
    """

    def __init__(self) -> None:
        # base client per peer (stateless)
        self._pool: dict[str, Any] = {}
        # session-scoped clients per (peer_name, session_id)
        self._session_pool: dict[tuple[str, str], Any] = {}
        # keeps the async ctx managers alive
        self._session_ctx: dict[tuple[str, str], Any] = {}

    async def run_sync(
        self,
        peer: AcpPeer,
        mission: str,
        *,
        session_id: str | None = None,
    ) -> dict[str, Any]:
        client = await self._session_client(peer, session_id)
        logger.debug("acp.client.run_sync", peer=peer.name, agent=peer.agent, session=session_id)
        run = await client.run_sync(mission, agent=peer.agent)
        return _run_to_dict(run, peer)

    async def run_stream(
        self,
        peer: AcpPeer,
        mission: str,
        *,
        session_id: str | None = None,
    ) -> AsyncIterator[dict[str, Any]]:
        client = await self._session_client(peer, session_id)
        logger.debug("acp.client.run_stream", peer=peer.name, agent=peer.agent)
        async for event in client.run_stream(mission, agent=peer.agent):
            yield _event_to_dict(event, peer)

    async def list_agents(self, peer: AcpPeer) -> list[AcpAgentManifest]:
        client = await self._client_for(peer)
        manifests: list[AcpAgentManifest] = []
        async for agent in client.agents():
            manifests.append(
                AcpAgentManifest(
                    name=getattr(agent, "name", ""),
                    description=getattr(agent, "description", "") or "",
                    metadata=dict(getattr(agent, "metadata", {}) or {}),
                )
            )
        return manifests

    async def close(self) -> None:
        # Close session-scoped contexts first.
        for key, ctx in list(self._session_ctx.items()):
            aexit = getattr(ctx, "__aexit__", None)
            if aexit is not None:
                try:
                    await aexit(None, None, None)
                except Exception:  # pragma: no cover - best-effort cleanup
                    pass
            self._session_ctx.pop(key, None)
            self._session_pool.pop(key, None)
        for client in list(self._pool.values()):
            aexit = getattr(client, "__aexit__", None)
            if aexit is not None:
                try:
                    await aexit(None, None, None)
                except Exception:  # pragma: no cover
                    pass
        self._pool.clear()

    # -- internal -----------------------------------------------------------

    async def _client_for(self, peer: AcpPeer) -> Any:
        if peer.name in self._pool:
            return self._pool[peer.name]
        if peer.auth.type == AcpAuthType.MTLS:
            raise NotImplementedError(
                "mTLS authentication is declared in AcpAuthType but not yet "
                "implemented; use bearer auth or a reverse-proxy sidecar."
            )
        if peer.auth.type == AcpAuthType.BEARER and peer.base_url.startswith("http://"):
            logger.warning(
                "acp.client.insecure_bearer",
                peer=peer.name,
                hint="Bearer tokens over plain HTTP are readable on the wire; use HTTPS.",
            )
        client_cls = load_client()
        kwargs: dict[str, Any] = {"base_url": peer.base_url}
        if peer.auth.type == AcpAuthType.BEARER and peer.auth.token:
            kwargs["headers"] = {"Authorization": f"Bearer {peer.auth.token}"}
        client = client_cls(**kwargs)
        aenter = getattr(client, "__aenter__", None)
        if aenter is not None:
            client = await aenter()
        self._pool[peer.name] = client
        return client

    async def _session_client(self, peer: AcpPeer, session_id: str | None) -> Any:
        base = await self._client_for(peer)
        if not session_id:
            return base
        key = (peer.name, session_id)
        cached = self._session_pool.get(key)
        if cached is not None:
            return cached
        models = load_models()
        session_cls = getattr(models, "Session", None)
        session_obj = session_cls(id=session_id) if session_cls is not None else None
        ctx = base.session(session_obj)
        scoped = await ctx.__aenter__()
        self._session_ctx[key] = ctx
        self._session_pool[key] = scoped
        return scoped


def _run_to_dict(run: Any, peer: AcpPeer) -> dict[str, Any]:
    output = getattr(run, "output", None) or []
    text = _collect_text(output)
    return {
        "peer": peer.name,
        "agent": peer.agent,
        "run_id": str(getattr(run, "run_id", "")),
        "status": str(getattr(run, "status", "completed")),
        "output_text": text,
        "raw": _safe_dump(run),
    }


def _event_to_dict(event: Any, peer: AcpPeer) -> dict[str, Any]:
    return {
        "peer": peer.name,
        "agent": peer.agent,
        "type": type(event).__name__,
        "raw": _safe_dump(event),
    }


def _collect_text(messages: list[Any]) -> str:
    chunks: list[str] = []
    for message in messages:
        parts = getattr(message, "parts", []) or []
        for part in parts:
            content = getattr(part, "content", None)
            if isinstance(content, str):
                chunks.append(content)
    return "\n".join(chunks)


def _safe_dump(obj: Any) -> Any:
    dump = getattr(obj, "model_dump", None)
    if callable(dump):
        try:
            return dump(mode="json")
        except Exception:  # pragma: no cover
            try:
                return dump()
            except Exception:
                return repr(obj)
    return repr(obj)
