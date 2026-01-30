"""In-memory message bus implementation for local coordination."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from typing import Any
from uuid import uuid4

from taskforce.core.domain.messaging import MessageEnvelope
from taskforce.core.interfaces.messaging import MessageBusProtocol


class InMemoryMessageBus(MessageBusProtocol):
    """Simple in-memory message bus for development and tests."""

    def __init__(self) -> None:
        self._topics: dict[str, asyncio.Queue[MessageEnvelope]] = {}
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
        queue = self._topics.setdefault(topic, asyncio.Queue())
        await queue.put(envelope)
        self._messages[envelope.message_id] = envelope
        return envelope

    async def subscribe(self, topic: str) -> AsyncIterator[MessageEnvelope]:
        queue = self._topics.setdefault(topic, asyncio.Queue())
        while True:
            envelope = await queue.get()
            yield envelope

    async def ack(self, message_id: str) -> None:
        self._messages.pop(message_id, None)

    async def nack(self, message_id: str, *, requeue: bool = True) -> None:
        envelope = self._messages.get(message_id)
        if not envelope:
            return
        if requeue:
            queue = self._topics.setdefault(envelope.topic, asyncio.Queue())
            await queue.put(envelope)
