"""
Conversation Manager

Application-layer service that orchestrates conversation lifecycle for
the persistent agent (ADR-016). Wraps ``ConversationManagerProtocol``
with higher-level concerns: auto-archival of stale conversations and
topic labelling.
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
    * **Topic suggestion** hook (to be wired to an LLM call externally).
    """

    def __init__(
        self,
        store: ConversationManagerProtocol,
        *,
        inactivity_threshold_hours: int = 24,
    ) -> None:
        self._store = store
        self._inactivity_threshold = timedelta(hours=inactivity_threshold_hours)

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
