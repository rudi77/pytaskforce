"""Provider adapters for external communication systems."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

import structlog

from taskforce.core.interfaces.communication import CommunicationProviderProtocol
from taskforce_extensions.infrastructure.communication.conversation_store import (
    FileConversationStore,
    InMemoryConversationStore,
)

OutboundSender = Callable[[str, str, dict[str, Any] | None], Awaitable[None]]


class BaseCommunicationProvider(CommunicationProviderProtocol):
    """Base provider that wires conversation storage and outbound sending."""

    def __init__(
        self,
        name: str,
        *,
        conversation_store: FileConversationStore | InMemoryConversationStore,
        outbound_sender: OutboundSender | None = None,
    ) -> None:
        self.name = name
        self._store = conversation_store
        self._outbound_sender = outbound_sender
        self._logger = structlog.get_logger().bind(provider=name)

    async def get_session_id(self, conversation_id: str) -> str | None:
        return await self._store.get_session_id(self.name, conversation_id)

    async def set_session_id(self, conversation_id: str, session_id: str) -> None:
        await self._store.set_session_id(self.name, conversation_id, session_id)

    async def load_history(self, conversation_id: str) -> list[dict[str, Any]]:
        return await self._store.load_history(self.name, conversation_id)

    async def save_history(
        self,
        conversation_id: str,
        history: list[dict[str, Any]],
    ) -> None:
        await self._store.save_history(self.name, conversation_id, history)

    async def send_message(
        self,
        *,
        conversation_id: str,
        message: str,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        if not self._outbound_sender:
            self._logger.info(
                "communication.outbound.not_configured",
                conversation_id=conversation_id,
            )
            return
        await self._outbound_sender(conversation_id, message, metadata)


class TelegramProvider(BaseCommunicationProvider):
    """Telegram provider adapter (inbound/outbound hooks configured externally)."""

    def __init__(
        self,
        *,
        conversation_store: FileConversationStore | InMemoryConversationStore,
        outbound_sender: OutboundSender | None = None,
    ) -> None:
        super().__init__(
            "telegram",
            conversation_store=conversation_store,
            outbound_sender=outbound_sender,
        )


class TeamsProvider(BaseCommunicationProvider):
    """Microsoft Teams provider adapter (inbound/outbound hooks configured externally)."""

    def __init__(
        self,
        *,
        conversation_store: FileConversationStore | InMemoryConversationStore,
        outbound_sender: OutboundSender | None = None,
    ) -> None:
        super().__init__(
            "teams",
            conversation_store=conversation_store,
            outbound_sender=outbound_sender,
        )
