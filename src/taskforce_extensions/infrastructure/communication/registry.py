"""Provider registry helpers for communication integrations."""

from __future__ import annotations

from taskforce.core.interfaces.communication import CommunicationProviderProtocol
from taskforce_extensions.infrastructure.communication.conversation_store import (
    FileConversationStore,
)
from taskforce_extensions.infrastructure.communication.providers import (
    OutboundSender,
    TeamsProvider,
    TelegramProvider,
)


def build_provider_registry(
    *,
    work_dir: str,
    outbound_senders: dict[str, OutboundSender] | None = None,
) -> dict[str, CommunicationProviderProtocol]:
    """Create provider registry with shared conversation storage."""
    conversation_store = FileConversationStore(work_dir=work_dir)
    outbound = outbound_senders or {}
    return {
        "telegram": TelegramProvider(
            conversation_store=conversation_store,
            outbound_sender=outbound.get("telegram"),
        ),
        "teams": TeamsProvider(
            conversation_store=conversation_store,
            outbound_sender=outbound.get("teams"),
        ),
    }
