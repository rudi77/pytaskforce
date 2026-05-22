"""Tests for AcpMessageBus (local-loop + cross-peer publish)."""

from __future__ import annotations

import asyncio
import json
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from taskforce.core.domain.acp import AcpPeer
from taskforce.infrastructure.acp.acp_message_bus import (
    AcpMessageBus,
    _topic_to_agent,
)
from taskforce.infrastructure.acp.peer_registry import InMemoryPeerRegistry
from taskforce.infrastructure.acp.runtime import AcpRuntime


def _runtime(client_mock: Any) -> AcpRuntime:
    peers = InMemoryPeerRegistry([AcpPeer(name="peer_b", base_url="http://b", agent="dummy")])
    server = MagicMock()
    server.is_running = False
    server.registered_manifests.return_value = []

    registered: list[str] = []

    def register_agent(manifest, handler):  # noqa: ANN001
        registered.append(manifest.name)
        server.registered_manifests.return_value = [
            type("M", (), {"name": n})() for n in registered
        ]

    server.register_agent.side_effect = register_agent
    return AcpRuntime(server=server, client=client_mock, peers=peers)


def test_topic_to_agent_escapes_dots() -> None:
    assert _topic_to_agent("tasks.new") == "bus_tasks_new"
    assert _topic_to_agent("notifications/push") == "bus_notifications_push"


@pytest.mark.asyncio
async def test_publish_delivers_to_local_subscribers() -> None:
    client = MagicMock()
    bus = AcpMessageBus(_runtime(client))

    iterator = bus.subscribe("tasks.new")

    async def collect():
        async for envelope in iterator:
            return envelope
        return None

    consumer = asyncio.create_task(collect())
    await asyncio.sleep(0)  # let subscribe register its queue
    published = await bus.publish("tasks.new", {"hello": "world"})
    received = await asyncio.wait_for(consumer, timeout=1.0)

    assert received is not None
    assert received.message_id == published.message_id
    assert received.payload == {"hello": "world"}


@pytest.mark.spec("acp.message_bus_publish_fans_out_to_publish_peers")
@pytest.mark.asyncio
async def test_publish_forwards_to_remote_peers() -> None:
    client = MagicMock()
    client.run_sync = AsyncMock(return_value={"status": "completed"})
    bus = AcpMessageBus(_runtime(client), publish_peers=["peer_b"])

    await bus.publish("alerts", {"severity": "high"})

    client.run_sync.assert_awaited_once()
    args, kwargs = client.run_sync.call_args
    peer, mission = args
    assert peer.name == "peer_b"
    assert peer.agent == "bus_alerts"
    parsed = json.loads(mission)
    assert parsed["topic"] == "alerts"
    assert parsed["payload"] == {"severity": "high"}


@pytest.mark.asyncio
async def test_nack_requeues_envelope() -> None:
    bus = AcpMessageBus(_runtime(MagicMock()))
    envelope = await bus.publish("t", {"x": 1})
    await bus.nack(envelope.message_id, requeue=True)

    queue = bus._queues["t"]  # noqa: SLF001 - internal state check
    # Two items: the original publish delivery + the re-queued one.
    assert queue.qsize() == 1
