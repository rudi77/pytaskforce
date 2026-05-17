"""Distributed ``MessageBusProtocol`` implementation that uses ACP as transport.

Mapping:

* ``publish(topic, payload)`` creates an ACP run on each configured publish
  peer, using ``bus_<topic>`` as the agent name.
* ``subscribe(topic)`` registers a local agent named ``bus_<topic>`` on the
  ACP runtime's server; incoming runs push envelopes into an ``asyncio.Queue``
  which the returned async iterator drains.
* ``ack`` / ``nack`` use ACP run status (acknowledged once delivered, requeued
  locally on nack).
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator
from typing import Any
from uuid import uuid4

import structlog

from taskforce.core.domain.acp import AcpAgentManifest
from taskforce.core.domain.messaging import MessageEnvelope
from taskforce.core.interfaces.messaging import MessageBusProtocol
from taskforce.infrastructure.acp.runtime import AcpRuntime

logger = structlog.get_logger(__name__)

TOPIC_AGENT_PREFIX = "bus_"


class AcpMessageBus(MessageBusProtocol):
    """Message bus implemented over ACP runs.

    Args:
        runtime: Running :class:`AcpRuntime`.
        publish_peers: Peer names that receive ``publish`` messages.
    """

    def __init__(
        self,
        runtime: AcpRuntime,
        *,
        publish_peers: list[str] | None = None,
    ) -> None:
        self._runtime = runtime
        self._publish_peers = list(publish_peers or [])
        self._queues: dict[str, asyncio.Queue[MessageEnvelope]] = {}
        self._messages: dict[str, MessageEnvelope] = {}

    async def publish(
        self,
        topic: str,
        payload: dict[str, Any],
        *,
        headers: dict[str, Any] | None = None,
        message_id: str | None = None,
    ) -> MessageEnvelope:
        envelope = MessageEnvelope(
            message_id=message_id or uuid4().hex,
            topic=topic,
            payload=payload,
            headers=headers or {},
        )
        self._messages[envelope.message_id] = envelope

        # Deliver locally first (loopback subscribers on this instance).
        local_queue = self._queues.get(topic)
        if local_queue is not None:
            await local_queue.put(envelope)

        if not self._publish_peers:
            return envelope

        mission = json.dumps(envelope.to_dict())
        agent_name = _topic_to_agent(topic)
        results = await asyncio.gather(
            *(
                self._send_to_peer(peer_name, agent_name, mission)
                for peer_name in self._publish_peers
            ),
            return_exceptions=True,
        )
        for peer_name, outcome in zip(self._publish_peers, results, strict=False):
            if isinstance(outcome, Exception):
                logger.warning(
                    "acp.bus.publish_peer_failed",
                    peer=peer_name,
                    topic=topic,
                    error=str(outcome),
                )
        return envelope

    async def subscribe(self, topic: str) -> AsyncIterator[MessageEnvelope]:
        # NOTE: ``_ensure_registered`` calls
        # ``AcpServer.register_agent``, which raises if the server is
        # already running. Because this method is an async generator,
        # the call below only executes on the *first iteration* — so
        # iterating ``subscribe(topic)`` for the first time after
        # ``runtime.start()`` will fail. The framework's
        # ``application/acp_service.py::build_message_bus`` works around
        # this by calling ``_ensure_registered`` directly for every
        # configured ``subscribe_topics`` entry before the runtime is
        # started. Callers driving the bus from their own code should
        # do the same.
        queue = self._queues.setdefault(topic, asyncio.Queue())
        self._ensure_registered(topic, queue)
        while True:
            envelope = await queue.get()
            yield envelope

    async def ack(self, message_id: str) -> None:
        self._messages.pop(message_id, None)

    async def nack(self, message_id: str, *, requeue: bool = True) -> None:
        envelope = self._messages.get(message_id)
        if not envelope or not requeue:
            return
        queue = self._queues.setdefault(envelope.topic, asyncio.Queue())
        await queue.put(envelope)

    def _ensure_registered(self, topic: str, queue: asyncio.Queue[MessageEnvelope]) -> None:
        agent_name = _topic_to_agent(topic)
        existing = {m.name for m in self._runtime.server.registered_manifests()}
        if agent_name in existing:
            return

        async def _handler(input_messages: list[Any], context: Any) -> Any:
            envelope = _parse_incoming(input_messages, topic)
            if envelope is not None:
                await queue.put(envelope)
            # Yield something so the ACP run has output.
            return _ok_message()

        manifest = AcpAgentManifest(
            name=agent_name,
            description=f"Message bus inbox for topic {topic!r}",
            metadata={"bus_topic": topic},
        )
        self._runtime.register_agent(manifest, _handler)

    async def _send_to_peer(self, peer_name: str, agent_name: str, mission: str) -> Any:
        peer = self._runtime.peers.get(peer_name)
        if peer is None:
            raise KeyError(f"Unknown publish peer: {peer_name!r}")
        # Override peer.agent for this call without mutating registry.
        from dataclasses import replace

        routed_peer = replace(peer, agent=agent_name)
        return await self._runtime.client.run_sync(routed_peer, mission)


def _topic_to_agent(topic: str) -> str:
    safe = topic.replace(".", "_").replace("/", "_")
    return f"{TOPIC_AGENT_PREFIX}{safe}"


def _parse_incoming(input_messages: list[Any], topic: str) -> MessageEnvelope | None:
    for message in input_messages:
        parts = getattr(message, "parts", []) or []
        for part in parts:
            content = getattr(part, "content", None)
            if not isinstance(content, str):
                continue
            try:
                data = json.loads(content)
            except json.JSONDecodeError:
                continue
            if isinstance(data, dict) and data.get("topic") == topic:
                try:
                    return MessageEnvelope.from_dict(data)
                except (KeyError, ValueError):
                    continue
    return None


def _ok_message() -> Any:
    from taskforce.infrastructure.acp._sdk import load_models

    models = load_models()
    message_cls = models.Message
    part_cls = models.MessagePart
    return message_cls(
        role="agent",
        parts=[part_cls(content="ack", content_type="text/plain")],
    )
