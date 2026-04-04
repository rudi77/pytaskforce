"""Protocol for pending channel question tracking.

When an agent asks a question targeted at a specific communication channel
(e.g. Telegram, Teams) the question is stored until the recipient responds.
The gateway checks this store on every inbound message to resolve pending
questions before starting new agent sessions.
"""

from __future__ import annotations

from typing import Any, Protocol


class PendingChannelQuestionStoreProtocol(Protocol):
    """Track pending questions sent to external communication channels.

    A pending question represents a paused agent execution waiting for a
    response from a specific person on a specific channel.
    """

    async def register(
        self,
        *,
        session_id: str,
        channel: str,
        recipient_id: str,
        question: str,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """Register a pending question for a channel recipient.

        Args:
            session_id: The agent session that is paused.
            channel: Target channel (e.g. 'telegram', 'teams').
            recipient_id: Recipient user ID on that channel.
            question: The question text that was sent.
            metadata: Optional extra data (missing fields, etc.).
        """
        ...

    async def resolve(
        self,
        *,
        channel: str,
        sender_id: str,
        response: str,
    ) -> str | None:
        """Try to resolve a pending question with an inbound response.

        If there is a pending question for this (channel, sender_id) pair,
        stores the response and returns the associated session_id.
        Returns ``None`` if no pending question exists for this sender.

        Args:
            channel: Source channel of the inbound message.
            sender_id: Sender user ID on that channel.
            response: The response message text.

        Returns:
            The session_id of the paused agent, or None.
        """
        ...

    async def get_response(self, *, session_id: str) -> str | None:
        """Get the response for a pending question, if available.

        Returns the response text if the recipient has answered,
        or ``None`` if still waiting.

        Args:
            session_id: The agent session to check.

        Returns:
            Response text or None.
        """
        ...

    async def remove(self, *, session_id: str) -> None:
        """Remove a pending question entry (after the agent has resumed).

        Args:
            session_id: The agent session whose pending question to remove.
        """
        ...
