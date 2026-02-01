"""Provider registry helpers for communication integrations."""

from __future__ import annotations

import os

import structlog

from taskforce.core.interfaces.communication import CommunicationProviderProtocol
from taskforce_extensions.infrastructure.communication.conversation_store import (
    FileConversationStore,
)
from taskforce_extensions.infrastructure.communication.providers import (
    OutboundSender,
    TeamsProvider,
    TelegramProvider,
)
from taskforce_extensions.infrastructure.communication.telegram_sender import (
    build_telegram_sender,
)


def build_provider_registry(
    *,
    work_dir: str,
    outbound_senders: dict[str, OutboundSender] | None = None,
) -> dict[str, CommunicationProviderProtocol]:
    """Create provider registry with shared conversation storage."""
    conversation_store = FileConversationStore(work_dir=work_dir)
    outbound = dict(outbound_senders or {})
    logger = structlog.get_logger()
    telegram_token = os.getenv("TELEGRAM_BOT_TOKEN")
    if telegram_token and "telegram" not in outbound:
        outbound["telegram"] = build_telegram_sender(telegram_token)
        logger.info("telegram.sender.configured")
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
