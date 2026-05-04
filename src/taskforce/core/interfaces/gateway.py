"""Protocol definitions for the unified Communication Gateway.

Separates concerns that were previously mixed in CommunicationProviderProtocol:
- OutboundSenderProtocol: sending messages to external channels
- InboundAdapterProtocol: normalizing raw channel payloads
- ConversationStoreProtocol: session mapping and history persistence
- RecipientRegistryProtocol: managing push-notification recipients
- RecipientResolverProtocol: mapping a channel-specific identity to a
  logical recipient (extension point for external auth/identity layers)
"""

from __future__ import annotations

from dataclasses import dataclass, field
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

    async def send_file(
        self,
        *,
        recipient_id: str,
        file_path: str,
        caption: str | None = None,
        attachment_type: str = "auto",
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """Deliver a file attachment to a recipient on this channel.

        Args:
            recipient_id: Channel-specific recipient (chat_id, conversation ref, etc.).
            file_path: Absolute local path to the file to upload.
            caption: Optional text shown alongside the file (channel-dependent).
            attachment_type: One of 'auto', 'document', 'photo', 'audio', 'voice'.
                'auto' selects a type based on the file extension.
            metadata: Optional channel-specific extras (parse_mode for caption, etc.).

        Raises:
            FileNotFoundError: If ``file_path`` does not exist.
            ConnectionError: If the upstream channel API is unreachable.
            NotImplementedError: If this channel does not support file uploads.
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

    async def delete_conversation(self, channel: str, conversation_id: str) -> None:
        """Remove the entire conversation record (history + session mapping).

        Used by reset commands (``/start``, ``/reset``) to ensure the next
        message starts with a fresh session ID.
        """
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


@dataclass(frozen=True)
class RecipientInfo:
    """Resolved recipient for an inbound message.

    The framework treats ``recipient_id`` opaquely — its meaning is
    decided by whatever ``RecipientResolverProtocol`` implementation
    produced it (a global user id, an externally-namespaced identity,
    an anonymous session token, etc.). The framework only uses it as
    the routing key.

    ``default_agent_id`` lets the resolver suggest which agent should
    handle the message when no explicit agent override is supplied via
    ``GatewayOptions``. The gateway falls back to the default routing
    behaviour when this is ``None``.

    ``attributes`` is an extension point for resolver-specific data
    (e.g. preferred language, role flags). The framework does not
    inspect these.
    """

    recipient_id: str
    default_agent_id: str | None = None
    attributes: dict[str, Any] = field(default_factory=dict)


class RecipientResolverProtocol(Protocol):
    """Resolve a channel-specific identity to a logical recipient.

    Implementations consume the channel name plus any channel-specific
    identity payload (e.g. ``{"sender_id": "..."}`` for a webhook,
    JWT claims for an HTTP request) and return a ``RecipientInfo`` or
    ``None`` if the identity cannot be mapped.

    The framework ships a pass-through default that treats
    ``channel_identity["sender_id"]`` as the recipient. External
    packages can install a richer resolver that, for example,
    consults an identity provider or a user database.
    """

    async def resolve(
        self,
        channel: str,
        channel_identity: dict[str, Any],
    ) -> RecipientInfo | None:
        """Map a channel identity to a logical recipient.

        Args:
            channel: Channel identifier (e.g. 'web', 'telegram').
            channel_identity: Channel-specific identity payload. The
                framework's pass-through resolver looks for a
                ``sender_id`` key; richer resolvers may use any keys
                their auth layer populates.

        Returns:
            ``RecipientInfo`` for a successful mapping, or ``None``
            when the identity cannot be resolved (the gateway treats
            this as an audited deny).
        """
        ...


class AgentLookupProtocol(Protocol):
    """Resolve an ``@agent_name`` mention to an agent id (ADR-022 §4).

    The gateway parses a leading ``@<name>`` token from inbound chat
    messages and asks an installed lookup to find the matching agent
    for the resolved recipient. The lookup is **tenant-scoped by
    construction**: implementations consult a registry instance that
    only contains the recipient's own tenant (Pattern A), so a request
    can never address another tenant's agent through this seam.

    The framework ships no default lookup; when none is installed the
    ``@<name>`` token is left as plain text in the message body and
    ``RecipientInfo.default_agent_id`` is used as before. Single-tenant
    builds therefore behave identically to today.
    """

    async def find_by_name(
        self,
        recipient: RecipientInfo,
        agent_name: str,
    ) -> str | None:
        """Look up ``agent_name`` in the recipient's tenant scope.

        Args:
            recipient: The recipient resolved from the inbound channel.
            agent_name: The name extracted from a leading ``@<name>``
                token (without the ``@`` and without surrounding
                whitespace). Implementations decide whether the lookup
                is case-sensitive.

        Returns:
            The agent id to route to, or ``None`` when the recipient
            has no agent by that name (the gateway treats this as an
            audited deny).
        """
        ...
