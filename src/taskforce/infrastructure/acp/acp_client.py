"""Outbound ACP client implementation."""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

import structlog

from taskforce.core.domain.acp import AcpAgentManifest, AcpAuthType, AcpPeer
from taskforce.infrastructure.acp._sdk import load_client, load_models

logger = structlog.get_logger(__name__)


class AcpClient:
    """ACP client built on ``acp_sdk.client.Client`` with a per-peer pool."""

    def __init__(self) -> None:
        self._pool: dict[str, Any] = {}

    async def run_sync(
        self,
        peer: AcpPeer,
        mission: str,
        *,
        session_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        client = await self._client_for(peer)
        input_messages = _build_input(mission)
        logger.debug("acp.client.run_sync", peer=peer.name, agent=peer.agent, session=session_id)
        run = await client.run_sync(
            agent=peer.agent,
            input=input_messages,
            session_id=session_id,
        )
        return _run_to_dict(run, peer)

    async def run_stream(
        self,
        peer: AcpPeer,
        mission: str,
        *,
        session_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> AsyncIterator[dict[str, Any]]:
        client = await self._client_for(peer)
        input_messages = _build_input(mission)
        logger.debug("acp.client.run_stream", peer=peer.name, agent=peer.agent)
        stream_method = getattr(client, "run_stream", None)
        if stream_method is None:
            # Fall back to sync call emitted as a single event.
            run = await client.run_sync(
                agent=peer.agent, input=input_messages, session_id=session_id
            )
            yield _run_to_dict(run, peer)
            return
        async for event in stream_method(
            agent=peer.agent, input=input_messages, session_id=session_id
        ):
            yield _event_to_dict(event, peer)

    async def list_agents(self, peer: AcpPeer) -> list[AcpAgentManifest]:
        client = await self._client_for(peer)
        agents_method = getattr(client, "agents", None)
        if agents_method is None:
            return []
        result = await agents_method()
        manifests: list[AcpAgentManifest] = []
        for agent in result:
            manifests.append(
                AcpAgentManifest(
                    name=getattr(agent, "name", ""),
                    description=getattr(agent, "description", "") or "",
                    metadata=dict(getattr(agent, "metadata", {}) or {}),
                )
            )
        return manifests

    async def close(self) -> None:
        for client in list(self._pool.values()):
            close = getattr(client, "close", None)
            if close is None:
                aexit = getattr(client, "__aexit__", None)
                if aexit is not None:
                    try:
                        await aexit(None, None, None)
                    except Exception:  # pragma: no cover - best-effort cleanup
                        pass
                continue
            result = close()
            if hasattr(result, "__await__"):
                try:
                    await result
                except Exception:  # pragma: no cover
                    pass
        self._pool.clear()

    async def _client_for(self, peer: AcpPeer) -> Any:
        if peer.name in self._pool:
            return self._pool[peer.name]
        client_cls = load_client()
        kwargs: dict[str, Any] = {"base_url": peer.base_url}
        if peer.auth.type == AcpAuthType.BEARER and peer.auth.token:
            kwargs["headers"] = {"Authorization": f"Bearer {peer.auth.token}"}
        client = client_cls(**kwargs)
        # acp-sdk ``Client`` is an async context manager.
        aenter = getattr(client, "__aenter__", None)
        if aenter is not None:
            client = await aenter()
        self._pool[peer.name] = client
        return client


def _build_input(mission: str) -> list[Any]:
    models = load_models()
    message_cls = models.Message
    part_cls = models.MessagePart
    return [
        message_cls(
            role="user",
            parts=[part_cls(content=mission, content_type="text/plain")],
        )
    ]


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
            return dump()
        except Exception:  # pragma: no cover
            return repr(obj)
    return repr(obj)
