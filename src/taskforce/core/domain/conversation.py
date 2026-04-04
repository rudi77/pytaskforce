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
class TopicSegment:
    """A topic segment within a conversation.

    Represents a contiguous block of messages about the same topic.
    When the user changes subject, the current segment is closed
    (summary generated) and a new one begins. Event interruptions
    create their own short-lived segments.

    Attributes:
        topic_id: Unique identifier for this segment (UUID hex).
        label: LLM-generated topic label (short, descriptive).
        started_at: When this topic segment began.
        ended_at: When this topic segment was closed (``None`` if active).
        message_range: ``(start_idx, end_idx)`` indices into the conversation
            message list (inclusive start, exclusive end).
        summary: LLM-generated summary, populated when the segment is closed.
        source: Origin of the segment — ``"user"`` for normal messages,
            ``"event"`` for event-triggered interruptions, ``"schedule"``
            for scheduled task results.
        priority: For topic resumption ordering (higher = more important).
    """

    label: str
    topic_id: str = field(default_factory=lambda: uuid4().hex)
    started_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    ended_at: datetime | None = None
    message_range: tuple[int, int] = (0, 0)
    summary: str | None = None
    source: str = "user"
    priority: int = 0

    def close(self, end_idx: int, summary: str | None = None) -> None:
        """Close this segment at the given message index."""
        self.ended_at = datetime.now(UTC)
        self.message_range = (self.message_range[0], end_idx)
        if summary is not None:
            self.summary = summary

    @property
    def is_active(self) -> bool:
        """Whether this segment is still open."""
        return self.ended_at is None


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
    topic_segments: list[TopicSegment] = field(default_factory=list)
    active_topic_id: str | None = None

    @property
    def active_topic(self) -> TopicSegment | None:
        """Return the currently active topic segment, if any."""
        if self.active_topic_id is None:
            return None
        for seg in self.topic_segments:
            if seg.topic_id == self.active_topic_id and seg.is_active:
                return seg
        return None

    def start_topic(
        self,
        label: str,
        message_idx: int,
        source: str = "user",
    ) -> TopicSegment:
        """Start a new topic segment, closing the current one if any."""
        current = self.active_topic
        if current is not None:
            current.close(end_idx=message_idx)

        segment = TopicSegment(
            label=label,
            message_range=(message_idx, message_idx),
            source=source,
        )
        self.topic_segments.append(segment)
        self.active_topic_id = segment.topic_id
        return segment

    def extend_topic(self, message_idx: int) -> None:
        """Extend the active topic segment to include a new message."""
        current = self.active_topic
        if current is not None:
            current.message_range = (current.message_range[0], message_idx + 1)

    def previous_user_topic(self) -> TopicSegment | None:
        """Find the most recent closed user-initiated topic (for resumption)."""
        for seg in reversed(self.topic_segments):
            if not seg.is_active and seg.source == "user":
                return seg
        return None

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
