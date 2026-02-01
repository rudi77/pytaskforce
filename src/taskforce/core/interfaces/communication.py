"""Protocol definitions for communication gateway integrations."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any, Protocol


class CommunicationGatewayProtocol(Protocol):
    """Protocol for outbound messaging providers."""

    async def send_message(
        self,
        *,
        provider: str,
        conversation_id: str,
        message: str,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """Send a message to an external communication provider."""
        ...


class ConversationStoreProtocol(Protocol):
    """Protocol for mapping provider conversations to sessions and history."""

    async def get_session_id(self, provider: str, conversation_id: str) -> str | None:
        """Return the mapped session ID for the provider conversation."""
        ...

    async def set_session_id(
        self,
        provider: str,
        conversation_id: str,
        session_id: str,
    ) -> None:
        """Persist the session ID mapping for a provider conversation."""
        ...

    async def load_history(
        self,
        provider: str,
        conversation_id: str,
    ) -> list[dict[str, Any]]:
        """Load stored conversation history for a provider conversation."""
        ...

    async def save_history(
        self,
        provider: str,
        conversation_id: str,
        history: Sequence[dict[str, Any]],
    ) -> None:
        """Persist conversation history for a provider conversation."""
        ...
