"""Tests for the AcpRuntime lifecycle facade."""

from __future__ import annotations

from datetime import timedelta
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from taskforce.core.domain.acp import AcpAgentManifest, AcpPeer
from taskforce.core.utils.time import utc_now
from taskforce.infrastructure.acp.peer_registry import InMemoryPeerRegistry
from taskforce.infrastructure.acp.runtime import AcpRuntime


def _runtime(client: Any | None = None) -> AcpRuntime:
    peers = InMemoryPeerRegistry([AcpPeer(name="p", base_url="http://x", agent="remote-agent")])
    server = MagicMock()
    server.is_running = False
    server.registered_manifests.return_value = []
    if client is None:
        client = MagicMock()
        client.run_sync = AsyncMock(
            return_value={
                "run_id": "r-1",
                "status": "completed",
                "output_text": "hi",
            }
        )
    return AcpRuntime(server=server, client=client, peers=peers)


@pytest.mark.asyncio
async def test_call_unknown_peer_raises() -> None:
    rt = _runtime()
    with pytest.raises(KeyError):
        await rt.call("missing", "do X")


@pytest.mark.asyncio
async def test_call_captures_started_at_before_run() -> None:
    """``AcpRunHandle.started_at`` must reflect call start, not completion."""

    async def slow_run_sync(*args: Any, **kwargs: Any) -> dict[str, Any]:
        import asyncio

        await asyncio.sleep(0.05)
        return {"run_id": "r-2", "status": "completed", "output_text": ""}

    client = MagicMock()
    client.run_sync = slow_run_sync
    rt = _runtime(client=client)

    before = utc_now()
    handle = await rt.call("p", "mission")
    after = utc_now()

    assert before <= handle.started_at <= after
    # The call slept ~50 ms; started_at must be measurably before ``after``.
    assert (after - handle.started_at) >= timedelta(milliseconds=40)


@pytest.mark.asyncio
async def test_call_returns_run_id_and_status() -> None:
    rt = _runtime()
    handle = await rt.call("p", "mission")
    assert handle.run_id == "r-1"
    assert handle.peer == "p"
    assert handle.agent == "remote-agent"
    assert handle.status == "completed"


def test_register_agent_delegates_to_server() -> None:
    rt = _runtime()
    manifest = AcpAgentManifest(name="local", description="")
    handler = AsyncMock()
    rt.register_agent(manifest, handler)
    rt.server.register_agent.assert_called_once_with(manifest, handler)  # type: ignore[attr-defined]


def test_registered_manifests_is_on_server_protocol() -> None:
    """``registered_manifests`` must be reachable without a type: ignore."""
    rt = _runtime()
    # Should not raise; returns whatever the server tracks (empty MagicMock).
    assert rt.server.registered_manifests() == []
