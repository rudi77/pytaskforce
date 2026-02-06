"""Protocol definitions for the unified Communication Gateway.

Separates concerns that were previously mixed in CommunicationProviderProtocol:
- OutboundSenderProtocol: sending messages to external channels
- InboundAdapterProtocol: normalizing raw channel payloads
- ConversationStoreProtocol: session mapping and history persistence
- RecipientRegistryProtocol: managing push-notification recipients
"""

from __future__ import annotations

from typing import Any, Protocol


class OutboundSenderProtocol(Protocol):
    """Send a message to an external communication channel.

    Each channel (Telegram, Teams, Slack, etc.) provides one implementation.
    Implementations must be stateless and async-safe.
    """

    @property
    def channel(self) -> str:
        """Channel identifier (e.g. 'telegram', 'teams')."""
        ...

    async def send(
        self,
        *,
        recipient_id: str,
        message: str,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """Deliver a message to a recipient on this channel.

        Args:
            recipient_id: Channel-specific recipient (chat_id, conversation ref, etc.).
            message: Plain-text or formatted message body.
            metadata: Optional channel-specific extras (parse_mode, card payload, etc.).

        Raises:
            ConnectionError: If the upstream channel API is unreachable.
        """
        ...


class InboundAdapterProtocol(Protocol):
    """Normalize raw webhook payloads from an external channel.

    Converts provider-specific JSON into a canonical InboundMessage.
    """

    @property
    def channel(self) -> str:
        """Channel identifier (e.g. 'telegram', 'teams')."""
        ...

    def extract_message(self, raw_payload: dict[str, Any]) -> dict[str, Any]:
        """Extract a normalized message dict from a raw webhook payload.

        Returns:
            Dictionary with keys: conversation_id, message, sender_id, metadata.

        Raises:
            ValueError: If the payload is malformed or missing required fields.
        """
        ...

    def verify_signature(
        self,
        *,
        raw_body: bytes,
        headers: dict[str, str],
    ) -> bool:
        """Verify that the webhook payload is authentic.

        Args:
            raw_body: The raw HTTP request body bytes.
            headers: HTTP headers from the webhook request.

        Returns:
            True if the signature is valid or verification is not configured.
        """
        ...


class ConversationStoreProtocol(Protocol):
    """Session mapping and conversation history persistence.

    This is channel-agnostic; the same store serves all channels.
    """

    async def get_session_id(self, channel: str, conversation_id: str) -> str | None:
        """Return the mapped Taskforce session ID, or None."""
        ...

    async def set_session_id(self, channel: str, conversation_id: str, session_id: str) -> None:
        """Persist a conversation-to-session mapping."""
        ...

    async def load_history(self, channel: str, conversation_id: str) -> list[dict[str, Any]]:
        """Load stored conversation history."""
        ...

    async def save_history(
        self, channel: str, conversation_id: str, history: list[dict[str, Any]]
    ) -> None:
        """Persist conversation history."""
        ...


class RecipientRegistryProtocol(Protocol):
    """Persistent store for push-notification recipient references.

    When a user first contacts the system via a channel, their
    channel-specific reference (Telegram chat_id, Teams ConversationReference,
    etc.) is stored here so the agent can proactively message them later.
    """

    async def register(
        self,
        *,
        channel: str,
        user_id: str,
        reference: dict[str, Any],
    ) -> None:
        """Store or update a recipient reference.

        Args:
            channel: Channel name (e.g. 'telegram').
            user_id: Application-level user identifier.
            reference: Channel-specific data needed to reach this user.
        """
        ...

    async def resolve(self, *, channel: str, user_id: str) -> dict[str, Any] | None:
        """Look up a stored recipient reference.

        Returns:
            The stored reference dict, or None if not registered.
        """
        ...

    async def list_recipients(self, channel: str) -> list[str]:
        """List all registered user IDs for a channel."""
        ...

    async def remove(self, *, channel: str, user_id: str) -> bool:
        """Remove a recipient. Returns True if it existed."""
        ...
