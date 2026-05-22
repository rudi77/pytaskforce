"""Tests for AcpAgentTool."""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from taskforce.core.domain.acp import AcpPeer
from taskforce.infrastructure.acp.peer_registry import InMemoryPeerRegistry
from taskforce.infrastructure.acp.runtime import AcpRuntime
from taskforce.infrastructure.tools.orchestration.acp_agent_tool import AcpAgentTool


class _FakeClient:
    def __init__(self) -> None:
        self.run_sync = AsyncMock(
            return_value={
                "run_id": "r1",
                "status": "completed",
                "output_text": "hello",
                "peer": "p1",
                "agent": "a1",
            }
        )

    async def run_stream(
        self, peer: AcpPeer, mission: str, **_: Any
    ) -> AsyncIterator[dict[str, Any]]:
        yield {"peer": peer.name, "agent": peer.agent, "type": "chunk", "raw": {}}
        yield {
            "peer": peer.name,
            "agent": peer.agent,
            "type": "final",
            "raw": {"output_text": "done"},
        }

    async def close(self) -> None:  # pragma: no cover - not exercised here
        return None


def _runtime() -> AcpRuntime:
    peers = InMemoryPeerRegistry([AcpPeer(name="p1", base_url="http://x", agent="a1")])
    # Server is never started in these tests; use a lightweight stand-in.
    fake_server = MagicMock()
    fake_server.is_running = False
    fake_server.registered_manifests.return_value = []
    return AcpRuntime(server=fake_server, client=_FakeClient(), peers=peers)


@pytest.mark.asyncio
async def test_call_acp_agent_sync_returns_payload() -> None:
    tool = AcpAgentTool(_runtime())
    result = await tool.execute(peer="p1", mission="do X")

    assert result["success"] is True
    assert result["peer"] == "p1"
    assert result["agent"] == "a1"
    assert result["output_text"] == "hello"


@pytest.mark.spec("acp.call_acp_agent_failure_returns_payload_not_raises")
@pytest.mark.asyncio
async def test_call_acp_agent_unknown_peer_returns_error_payload() -> None:
    tool = AcpAgentTool(_runtime())
    result = await tool.execute(peer="missing", mission="do X")

    assert result["success"] is False
    assert "Unknown ACP peer" in result["error"]


@pytest.mark.asyncio
async def test_call_acp_agent_stream_collects_events() -> None:
    tool = AcpAgentTool(_runtime())
    result = await tool.execute(peer="p1", mission="do X", stream=True)

    assert result["success"] is True
    assert result["stream"] is True
    assert len(result["events"]) == 2
    assert result["output_text"] == "done"


@pytest.mark.asyncio
async def test_call_acp_agent_enforces_runtime_tenant_policy() -> None:
    peers = InMemoryPeerRegistry(
        [AcpPeer(name="other", base_url="http://x", agent="a1", tenant_id="tenant_b")]
    )
    fake_server = MagicMock()
    fake_server.is_running = False
    client = _FakeClient()
    runtime = AcpRuntime(
        server=fake_server,
        client=client,
        peers=peers,
        tenant_id_provider=lambda: "tenant_a",
    )
    tool = AcpAgentTool(runtime)

    result = await tool.execute(peer="other", mission="do X")

    assert result["success"] is False
    client.run_sync.assert_not_called()
