"""Protocol definitions for communication provider integrations."""

from __future__ import annotations

from typing import Any, Protocol


class CommunicationProviderProtocol(Protocol):
    """Unified protocol for provider communication and history."""

    name: str

    async def get_session_id(self, conversation_id: str) -> str | None:
        """Return the mapped session ID for a provider conversation."""
        ...

    async def set_session_id(self, conversation_id: str, session_id: str) -> None:
        """Persist the session ID mapping for a provider conversation."""
        ...

    async def load_history(self, conversation_id: str) -> list[dict[str, Any]]:
        """Load stored conversation history for a provider conversation."""
        ...

    async def save_history(
        self,
        conversation_id: str,
        history: list[dict[str, Any]],
    ) -> None:
        """Persist conversation history for a provider conversation."""
        ...

    async def send_message(
        self,
        *,
        conversation_id: str,
        message: str,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """Send a message to an external communication provider."""
        ...
