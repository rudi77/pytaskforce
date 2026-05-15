"""
Conversation Manager

Application-layer service that orchestrates conversation lifecycle for
the persistent agent (ADR-016). Wraps ``ConversationManagerProtocol``
with higher-level concerns: auto-archival of stale conversations,
topic labelling, and topic segmentation.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import structlog

from taskforce.core.interfaces.conversation import (
    ConversationInfo,
    ConversationManagerProtocol,
    ConversationSummary,
)

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
        topic_detector: Any | None = None,
    ) -> None:
        self._store = store
        self._inactivity_threshold = timedelta(hours=inactivity_threshold_hours)
        self._topic_detector = topic_detector

    # ------------------------------------------------------------------
    # Delegation with auto-archival
    # ------------------------------------------------------------------

    async def get_or_create(
        self,
        channel: str,
        sender_id: str | None = None,
        project_id: str | None = None,
    ) -> str:
        """Get active conversation or create a new one.

        Also triggers auto-archival of stale conversations.
        """
        await self._auto_archive_stale()
        return await self._store.get_or_create(channel, sender_id, project_id)

    async def create_new(
        self,
        channel: str,
        sender_id: str | None = None,
        project_id: str | None = None,
    ) -> str:
        """Explicitly start a new conversation (e.g. ``/new``)."""
        return await self._store.create_new(channel, sender_id, project_id)

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

    async def delete(self, conversation_id: str) -> bool:
        """Hard-delete a conversation (irreversible).

        Returns ``True`` when the conversation existed and was removed,
        ``False`` when nothing matched.
        """
        return await self._store.delete(conversation_id)

    async def replace_messages(
        self,
        conversation_id: str,
        messages: list[dict[str, Any]],
    ) -> None:
        """Replace the full message log (used by ``compact``)."""
        await self._store.replace_messages(conversation_id, messages)

    # ------------------------------------------------------------------
    # Compaction
    # ------------------------------------------------------------------

    _COMPACT_SYSTEM_PROMPT = (
        "You are a precise conversation summarizer. The user gives you a "
        "transcript of an in-flight assistant conversation tagged with role "
        "labels ([user], [assistant], [tool], [system]). Produce a compact "
        "summary that another AI assistant could use to continue the work "
        "WITHOUT seeing the original messages. Preserve: the user's goals, "
        "key decisions made, intermediate findings, open questions, file "
        "paths or identifiers that were referenced, and any constraints. "
        "Drop pleasantries and verbose tool output. Aim for under 800 tokens. "
        "Reply with the summary only — no preamble, no headers."
    )

    async def compact(
        self,
        conversation_id: str,
        summarizer: Any,
        *,
        keep_last_n: int = 4,
    ) -> dict[str, Any]:
        """Replace older messages with a single LLM-generated summary.

        Mirrors Cowork's ``/compact`` slash-command behaviour: compresses the
        long tail of a conversation so the agent can keep working in the
        same conversation_id without context-window pressure.

        Args:
            conversation_id: Target conversation.
            summarizer: Async callable ``(messages: list[dict]) -> str`` that
                produces the summary text. Decoupled from any specific LLM
                provider so the manager stays infrastructure-agnostic and
                tests can pass a fake.
            keep_last_n: Number of trailing messages to keep verbatim. The
                rest are summarized into a single ``role="system"`` message
                prepended to the kept tail. Defaults to 4 (typical: last
                user/assistant pair × 2).

        Returns:
            Status dict:
                ``{"status": "compacted", "summarized": N, "kept": M,
                   "summary_preview": "..."}``
            or ``{"status": "skipped", "reason": "...", "messages": N}``
            when there's not enough to compress meaningfully.
        """
        messages = await self._store.get_messages(conversation_id)
        # +1 because the summary itself takes one slot — compacting a
        # conversation that's already only keep_last_n long is a no-op.
        if len(messages) <= keep_last_n + 1:
            return {
                "status": "skipped",
                "reason": "below_threshold",
                "messages": len(messages),
            }

        if keep_last_n > 0:
            to_summarize = messages[:-keep_last_n]
            kept = messages[-keep_last_n:]
        else:
            to_summarize = list(messages)
            kept = []

        summary_text = await summarizer(to_summarize)
        if not isinstance(summary_text, str) or not summary_text.strip():
            raise RuntimeError(
                "Summarizer returned empty content; refusing to compact "
                "(would silently destroy conversation history)."
            )

        summary_message: dict[str, Any] = {
            "role": "system",
            "content": (
                f"[Compacted summary of {len(to_summarize)} earlier messages]"
                f"\n\n{summary_text.strip()}"
            ),
        }
        new_messages: list[dict[str, Any]] = [summary_message, *kept]
        await self._store.replace_messages(conversation_id, new_messages)

        logger.info(
            "conversation.compacted",
            conversation_id=conversation_id,
            summarized=len(to_summarize),
            kept=len(kept),
            summary_chars=len(summary_text),
        )
        return {
            "status": "compacted",
            "summarized": len(to_summarize),
            "kept": len(kept),
            "summary_preview": summary_text.strip()[:200],
        }

    # Volatile per-message fields that the store fills in on append; these
    # must not be transferred to the forked conversation because they refer
    # to the source conversation's storage layout.
    _FORK_DROPPED_FIELDS: frozenset[str] = frozenset(
        {
            "message_id",
            "id",
            "timestamp",
            "created_at",
            "conversation_id",
            "sequence",
            "index",
        }
    )

    async def fork(
        self,
        source_id: str,
        *,
        up_to_index: int | None = None,
        channel: str = "rest",
    ) -> tuple[str, int]:
        """Create a new conversation seeded with messages from ``source_id``.

        ``up_to_index`` is exclusive; ``None`` copies the full transcript.
        Returns ``(new_conversation_id, messages_copied)``. Useful for
        replaying a conversation against a different profile or model
        without mutating the original.

        Tool-call linkage (``tool_calls``, ``tool_call_id``, ``name``) is
        preserved so a forked conversation continues to validate against
        provider APIs that require matched tool turns.
        """
        messages = await self._store.get_messages(source_id)
        if up_to_index is None:
            slice_ = messages
        else:
            slice_ = messages[: max(0, up_to_index)]
        new_id = await self._store.create_new(channel)
        for msg in slice_:
            payload = {
                k: v
                for k, v in msg.items()
                if k not in self._FORK_DROPPED_FIELDS
            }
            await self._store.append_message(new_id, payload)
        logger.info(
            "conversation.forked",
            source=source_id,
            target=new_id,
            messages_copied=len(slice_),
        )
        return new_id, len(slice_)

    async def list_active(self) -> list[ConversationInfo]:
        """List all active conversations."""
        return await self._store.list_active()

    async def list_archived(self, limit: int = 20) -> list[ConversationSummary]:
        """List archived conversations."""
        return await self._store.list_archived(limit)

    # ------------------------------------------------------------------
    # Topic segmentation
    # ------------------------------------------------------------------

    def set_topic_detector(self, detector: Any) -> None:
        """Inject a topic detector (e.g. after LLM provider is ready)."""
        self._topic_detector = detector

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
            # (Working-memory cleanup was removed with the old memory store.)

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
