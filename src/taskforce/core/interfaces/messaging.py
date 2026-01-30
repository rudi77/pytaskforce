"""Protocol definitions for message bus integrations."""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any, Protocol

from taskforce.core.domain.messaging import MessageEnvelope


class MessageBusProtocol(Protocol):
    """Protocol for message bus implementations."""

    async def publish(
        self,
        topic: str,
        payload: dict[str, Any],
        *,
        headers: dict[str, Any] | None = None,
        message_id: str | None = None,
    ) -> MessageEnvelope:
        """Publish a message to a topic."""
        ...

    async def subscribe(self, topic: str) -> AsyncIterator[MessageEnvelope]:
        """Subscribe to a topic and yield incoming messages."""
        ...

    async def ack(self, message_id: str) -> None:
        """Acknowledge a message as processed."""
        ...

    async def nack(self, message_id: str, *, requeue: bool = True) -> None:
        """Reject a message, optionally re-queueing it."""
        ...
