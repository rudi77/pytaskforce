"""
Conversation Domain Model

Represents a conversation — the lightweight replacement for sessions in
the persistent agent architecture (ADR-016). A conversation is a thematic
dialogue unit that can be active or archived.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from typing import Any
from uuid import uuid4


class ConversationStatus(str, Enum):
    """Lifecycle status of a conversation."""

    ACTIVE = "active"
    ARCHIVED = "archived"


@dataclass
class Conversation:
    """A single conversation (dialogue unit).

    Attributes:
        conversation_id: Unique identifier (auto-generated UUID hex).
        channel: Source channel (``"telegram"``, ``"cli"``, ``"rest"``).
        status: Active or archived.
        started_at: When the conversation was created (UTC).
        last_activity: Timestamp of the most recent message (UTC).
        message_count: Total messages in this conversation.
        topic: Optional LLM-generated topic label.
        summary: Optional LLM-generated summary (populated on archival).
        archived_at: When the conversation was archived (``None`` if active).
        sender_id: Optional sender identifier (for multi-user channels).
        metadata: Arbitrary extra data.
    """

    channel: str
    conversation_id: str = field(default_factory=lambda: uuid4().hex)
    status: ConversationStatus = ConversationStatus.ACTIVE
    started_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    last_activity: datetime = field(default_factory=lambda: datetime.now(UTC))
    message_count: int = 0
    topic: str | None = None
    summary: str | None = None
    archived_at: datetime | None = None
    sender_id: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def touch(self) -> None:
        """Update ``last_activity`` and increment ``message_count``."""
        self.last_activity = datetime.now(UTC)
        self.message_count += 1

    def archive(self, summary: str | None = None) -> None:
        """Mark this conversation as archived."""
        self.status = ConversationStatus.ARCHIVED
        self.archived_at = datetime.now(UTC)
        if summary is not None:
            self.summary = summary
