"""
Agent Request Model

Domain model for queued requests in the persistent agent architecture
(ADR-016). All inbound messages — whether from Telegram, CLI, REST, or
internal events — are normalized into ``AgentRequest`` objects and placed
on the central request queue.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4


@dataclass(frozen=True)
class AgentRequest:
    """A queued request from any channel.

    Attributes:
        request_id: Unique identifier (auto-generated UUID hex).
        channel: Source channel (``"telegram"``, ``"cli"``, ``"rest"``,
                 ``"event"``, etc.).
        message: User message or event description.
        conversation_id: Optional conversation this request belongs to.
            ``None`` means the agent/queue should resolve or create one.
        sender_id: Optional sender identifier (for reply routing).
        session_id: Stable session ID for agent state persistence.
            When ``None``, the processor falls back to ``request_id``.
        metadata: Channel-specific or event-specific extra data.
        created_at: Timestamp of request creation (UTC).
    """

    channel: str
    message: str
    request_id: str = field(default_factory=lambda: uuid4().hex)
    conversation_id: str | None = None
    sender_id: str | None = None
    session_id: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
