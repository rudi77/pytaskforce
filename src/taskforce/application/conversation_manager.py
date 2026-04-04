"""
Conversation Manager

Application-layer service that orchestrates conversation lifecycle for
the persistent agent (ADR-016). Wraps ``ConversationManagerProtocol``
with higher-level concerns: auto-archival of stale conversations,
topic labelling, and topic segmentation.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Any

import structlog

from taskforce.core.interfaces.conversation import (
    ConversationInfo,
    ConversationManagerProtocol,
    ConversationSummary,
)

if TYPE_CHECKING:
    from taskforce.application.topic_detector import TopicDetector
    from taskforce.core.interfaces.memory_store import MemoryStoreProtocol

logger = structlog.get_logger(__name__)


class ConversationManager:
    """High-level conversation lifecycle orchestration.

    Delegates storage to a ``ConversationManagerProtocol`` implementation
    and adds:

    * **Auto-archival** of conversations inactive beyond a configurable
      threshold.
    * **Topic segmentation** via an optional ``TopicDetector``.
    """

    def __init__(
        self,
        store: ConversationManagerProtocol,
        *,
        inactivity_threshold_hours: int = 24,
        topic_detector: TopicDetector | None = None,
        memory_store: MemoryStoreProtocol | None = None,
    ) -> None:
        self._store = store
        self._inactivity_threshold = timedelta(hours=inactivity_threshold_hours)
        self._topic_detector = topic_detector
        self._memory_store = memory_store

    # ------------------------------------------------------------------
    # Delegation with auto-archival
    # ------------------------------------------------------------------

    async def get_or_create(
        self,
        channel: str,
        sender_id: str | None = None,
    ) -> str:
        """Get active conversation or create a new one.

        Also triggers auto-archival of stale conversations.
        """
        await self._auto_archive_stale()
        return await self._store.get_or_create(channel, sender_id)

    async def create_new(
        self,
        channel: str,
        sender_id: str | None = None,
    ) -> str:
        """Explicitly start a new conversation (e.g. ``/new``)."""
        return await self._store.create_new(channel, sender_id)

    async def append_message(
        self,
        conversation_id: str,
        message: dict[str, Any],
    ) -> None:
        """Append a message to the conversation."""
        await self._store.append_message(conversation_id, message)

    async def get_messages(
        self,
        conversation_id: str,
        limit: int | None = None,
    ) -> list[dict[str, Any]]:
        """Retrieve messages from a conversation."""
        return await self._store.get_messages(conversation_id, limit)

    async def archive(
        self,
        conversation_id: str,
        summary: str | None = None,
    ) -> None:
        """Archive a conversation with an optional summary."""
        await self._store.archive(conversation_id, summary)

    async def list_active(self) -> list[ConversationInfo]:
        """List all active conversations."""
        return await self._store.list_active()

    async def list_archived(self, limit: int = 20) -> list[ConversationSummary]:
        """List archived conversations."""
        return await self._store.list_archived(limit)

    # ------------------------------------------------------------------
    # Topic segmentation
    # ------------------------------------------------------------------

    def set_topic_detector(self, detector: TopicDetector) -> None:
        """Inject a topic detector (e.g. after LLM provider is ready)."""
        self._topic_detector = detector

    def set_memory_store(self, memory_store: MemoryStoreProtocol) -> None:
        """Inject a memory store for working memory cleanup."""
        self._memory_store = memory_store

    async def detect_topic(
        self,
        conversation_id: str,
        user_message: str,
    ) -> str | None:
        """Run topic detection after a user message.

        Returns the topic context injection string if a topic change or
        resumption is detected, or ``None`` if no context is needed.
        """
        if self._topic_detector is None:
            return None

        # Get conversation object from the store.
        conv = await self._get_conversation_object(conversation_id)
        if conv is None:
            return None

        recent = await self.get_messages(conversation_id, limit=5)
        current_label = conv.active_topic.label if conv.active_topic else None

        change = await self._topic_detector.detect(
            message=user_message,
            current_label=current_label,
            recent_messages=recent,
        )

        if change is None:
            # No change — just extend the current topic.
            conv.extend_topic(conv.message_count)
            return None

        # Close the current topic with a summary if it existed.
        previous_topic = conv.active_topic
        if previous_topic is not None:
            segment_messages = await self._get_segment_messages(
                conversation_id, previous_topic
            )
            summary = await self._topic_detector.generate_summary(
                segment_messages, previous_topic.label
            )
            previous_topic.close(end_idx=conv.message_count, summary=summary)
            logger.info(
                "conversation.topic_closed",
                conversation_id=conversation_id,
                topic=previous_topic.label,
                summary=summary[:100] if summary else None,
            )
            # Clean up working memories associated with the closed topic.
            await self._cleanup_working_memories(previous_topic.topic_id)

        # Start new topic.
        new_seg = conv.start_topic(
            label=change.label,
            message_idx=conv.message_count,
            source="user",
        )
        logger.info(
            "conversation.topic_started",
            conversation_id=conversation_id,
            topic=change.label,
            confidence=change.confidence,
        )

        # Build context injection if this is a resumption after an event interruption.
        return self._build_topic_context(conv, previous_topic, new_seg)

    def _build_topic_context(
        self,
        conv: Any,
        previous_topic: Any,
        new_topic: Any,
    ) -> str | None:
        """Build a context injection string for topic transitions.

        Returns a brief context hint if the conversation was interrupted by
        an event, so the agent can smoothly resume the user's previous topic.
        """
        if previous_topic is None:
            return None

        # Only inject context for event/schedule interruptions.
        if previous_topic.source not in ("event", "schedule"):
            return None

        # Find the last user-initiated topic before the interruption.
        user_topic = conv.previous_user_topic()
        if user_topic is None or user_topic.summary is None:
            return None

        return (
            f"[Context: The previous topic was \"{user_topic.label}\". "
            f"It was interrupted by a {previous_topic.source} event. "
            f"Summary of the previous topic: {user_topic.summary}]"
        )

    async def _cleanup_working_memories(self, topic_id: str) -> None:
        """Delete working memories tagged with the given topic ID.

        Working memories (kind=WORKING) are temporary scratch-pad entries
        that exist only for the duration of a topic segment. When a topic
        is closed, its working memories are no longer needed.
        """
        if self._memory_store is None:
            return

        from taskforce.core.domain.memory import MemoryKind

        try:
            records = await self._memory_store.list(kind=MemoryKind.WORKING)
            deleted = 0
            for record in records:
                if topic_id in record.tags:
                    await self._memory_store.delete(record.id)
                    deleted += 1
            if deleted:
                logger.info(
                    "conversation.working_memories_cleaned",
                    topic_id=topic_id[:8],
                    deleted=deleted,
                )
        except Exception as exc:
            logger.warning(
                "conversation.working_memory_cleanup_failed",
                topic_id=topic_id[:8],
                error=str(exc),
            )

    async def _get_conversation_object(self, conversation_id: str) -> Any:
        """Retrieve the Conversation domain object from the store.

        Returns ``None`` if the store doesn't expose domain objects directly.
        """
        if hasattr(self._store, "get_conversation"):
            return await self._store.get_conversation(conversation_id)
        return None

    async def _get_segment_messages(
        self,
        conversation_id: str,
        segment: Any,
    ) -> list[dict[str, Any]]:
        """Retrieve messages belonging to a specific topic segment."""
        all_messages = await self.get_messages(conversation_id)
        start, end = segment.message_range
        return all_messages[start:end]

    # ------------------------------------------------------------------
    # Auto-archival
    # ------------------------------------------------------------------

    async def _auto_archive_stale(self) -> None:
        """Archive conversations that have been inactive beyond the threshold."""
        now = datetime.now(UTC)
        active = await self._store.list_active()
        for conv in active:
            if now - conv.last_activity > self._inactivity_threshold:
                logger.info(
                    "conversation.auto_archiving",
                    conversation_id=conv.conversation_id,
                    last_activity=conv.last_activity.isoformat(),
                )
                await self._store.archive(conv.conversation_id)
