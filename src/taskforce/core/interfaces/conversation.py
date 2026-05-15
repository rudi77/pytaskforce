"""
Conversation Management Protocol

Defines the contract for conversation lifecycle management in the persistent
agent architecture (ADR-016). Conversations replace sessions as the primary
unit of dialogue organisation.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Protocol


@dataclass(frozen=True)
class ConversationInfo:
    """Metadata for an active conversation."""

    conversation_id: str
    channel: str
    started_at: datetime
    last_activity: datetime
    message_count: int
    topic: str | None = None
    project_id: str | None = None


@dataclass(frozen=True)
class ConversationSummary:
    """Summary of an archived conversation."""

    conversation_id: str
    topic: str
    summary: str
    started_at: datetime
    archived_at: datetime
    message_count: int


class ConversationManagerProtocol(Protocol):
    """Manages conversation lifecycle for the persistent agent.

    Conversations are lightweight dialogue units that replace sessions.
    They can be segmented by topic (hybrid: agent-suggested or user-explicit)
    and archived automatically after inactivity.
    """

    async def get_or_create(
        self,
        channel: str,
        sender_id: str | None = None,
        project_id: str | None = None,
    ) -> str:
        """Get the active conversation for a channel/sender, or create a new one.

        Args:
            channel: Communication channel (e.g. "telegram", "cli", "rest").
            sender_id: Optional sender identifier for multi-user channels.
            project_id: Optional project id to associate with the new
                conversation (only applied when a new conversation is
                created — existing conversations keep their original
                project association).

        Returns:
            The conversation_id of the active (or newly created) conversation.
        """
        ...

    async def create_new(
        self,
        channel: str,
        sender_id: str | None = None,
        project_id: str | None = None,
    ) -> str:
        """Explicitly create a new conversation (e.g. via ``/new``).

        Archives the currently active conversation for the given
        channel/sender (if any) before creating a fresh one.

        Args:
            channel: Communication channel.
            sender_id: Optional sender identifier.
            project_id: Optional project id to associate with the new
                conversation. When set, the agent's working_dir for
                this conversation resolves to the project's path.

        Returns:
            The conversation_id of the new conversation.
        """
        ...

    async def append_message(
        self,
        conversation_id: str,
        message: dict[str, Any],
    ) -> None:
        """Append a message to a conversation's history.

        Args:
            conversation_id: Target conversation.
            message: Message dict with at least ``role`` and ``content`` keys.
        """
        ...

    async def get_messages(
        self,
        conversation_id: str,
        limit: int | None = None,
    ) -> list[dict[str, Any]]:
        """Retrieve messages from a conversation.

        Args:
            conversation_id: Target conversation.
            limit: Maximum number of most-recent messages to return.
                   ``None`` returns all messages.

        Returns:
            List of message dicts, ordered chronologically.
        """
        ...

    async def archive(
        self,
        conversation_id: str,
        summary: str | None = None,
    ) -> None:
        """Archive a conversation.

        Args:
            conversation_id: Conversation to archive.
            summary: Optional LLM-generated summary. If ``None``, the
                     implementation may generate one or store without summary.
        """
        ...

    async def replace_messages(
        self,
        conversation_id: str,
        messages: list[dict[str, Any]],
    ) -> None:
        """Atomically replace the entire message log of a conversation.

        Used by the ``compact`` flow to swap N earlier messages for a single
        summary message while keeping the conversation_id stable. Implementations
        must update ``message_count`` and ``last_activity`` metadata so the
        active-conversation listing stays consistent.

        Args:
            conversation_id: Target conversation.
            messages: Full new message log (replaces existing messages).
        """
        ...

    async def list_active(self) -> list[ConversationInfo]:
        """List all active (non-archived) conversations.

        Returns:
            List of ``ConversationInfo`` ordered by last activity (newest first).
        """
        ...

    async def list_archived(self, limit: int = 20) -> list[ConversationSummary]:
        """List archived conversations.

        Args:
            limit: Maximum number of summaries to return.

        Returns:
            List of ``ConversationSummary`` ordered by archive date (newest first).
        """
        ...
