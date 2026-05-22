"""End-to-end integration test for the ACP message bus.

Boots two real ``AcpRuntime`` instances on loopback ports and verifies
that ``AcpMessageBus.publish(topic, payload)`` on the publisher peer is
delivered to ``AcpMessageBus.subscribe(topic)`` on the subscriber peer
over actual ACP HTTP runs.

The unit tests in ``tests/unit/infrastructure/acp/test_acp_message_bus.py``
cover the same logic with mocks; this test exercises the network path.
"""

from __future__ import annotations

import asyncio
import socket
from contextlib import closing

import pytest

pytest.importorskip("acp_sdk")

from taskforce.core.domain.acp import AcpPeer  # noqa: E402
from taskforce.infrastructure.acp.acp_message_bus import AcpMessageBus  # noqa: E402
from taskforce.infrastructure.acp.runtime import AcpRuntime  # noqa: E402


def _free_port() -> int:
    with closing(socket.socket(socket.AF_INET, socket.SOCK_STREAM)) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


@pytest.mark.spec("acp.message_bus_publish_crosses_acp_network_to_subscriber")
@pytest.mark.asyncio
@pytest.mark.timeout(60)
async def test_publish_crosses_acp_network_to_subscriber() -> None:
    port_a = _free_port()
    port_b = _free_port()

    runtime_a = AcpRuntime(host="127.0.0.1", port=port_a)
    runtime_b = AcpRuntime(host="127.0.0.1", port=port_b)

    runtime_a.peers.register(
        AcpPeer(
            name="subscriber",
            base_url=f"http://127.0.0.1:{port_b}",
            agent="bus_demo_events",  # overridden per-call by the bus
        )
    )

    bus_a = AcpMessageBus(runtime_a, publish_peers=["subscriber"])
    bus_b = AcpMessageBus(runtime_b)

    # Register the inbox handler on B BEFORE starting its server. The
    # `subscribe()` method is an async generator that registers lazily
    # on first iteration, which is *too late* once the server is
    # running — `AcpServer.register_agent` rejects new agents while
    # uvicorn is serving. The framework's
    # `application/acp_service.py::build_message_bus` uses the same
    # `_ensure_registered` pre-start pattern, mirrored here.
    topic_queue: asyncio.Queue = bus_b._queues.setdefault(  # noqa: SLF001 - matches framework setup path
        "demo_events", asyncio.Queue()
    )
    bus_b._ensure_registered("demo_events", topic_queue)  # noqa: SLF001

    await runtime_a.start()
    await runtime_b.start()

    try:
        # Now safe to iterate; registration already happened above.
        iterator_b = bus_b.subscribe("demo_events")

        async def collect() -> object:
            async for envelope in iterator_b:
                return envelope
            return None

        consumer = asyncio.create_task(collect())
        # Tiny yield so the consumer is parked on queue.get() before publish.
        await asyncio.sleep(0)

        published = await bus_a.publish("demo_events", {"hello": "world"})
        received = await asyncio.wait_for(consumer, timeout=10.0)

        assert received is not None
        assert received.payload == {"hello": "world"}
        assert received.topic == "demo_events"
        # message_id is generated fresh on the wire (the subscriber parses
        # the envelope from the run payload) so it should match.
        assert received.message_id == published.message_id
    finally:
        await runtime_a.stop()
        await runtime_b.stop()
