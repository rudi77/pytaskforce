"""Gateway registry builder for communication channel adapters.

Creates and wires all channel components (inbound adapters, outbound senders,
conversation store, recipient registry) from environment configuration.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field

import structlog

from taskforce.core.interfaces.gateway import (
    ConversationStoreProtocol,
    InboundAdapterProtocol,
    OutboundSenderProtocol,
    RecipientRegistryProtocol,
)
from taskforce.infrastructure.communication.gateway_conversation_store import (
    FileConversationStore,
)
from taskforce.infrastructure.communication.inbound_adapters import (
    TeamsInboundAdapter,
    TelegramInboundAdapter,
)
from taskforce.infrastructure.communication.outbound_senders import (
    TeamsOutboundSender,
    TelegramOutboundSender,
)
from taskforce.infrastructure.communication.recipient_registry import (
    FileRecipientRegistry,
)


@dataclass
class GatewayComponents:
    """All wired components needed by CommunicationGateway.

    Attributes:
        conversation_store: Shared conversation persistence.
        recipient_registry: Push notification recipient persistence.
        outbound_senders: Channel name -> sender mapping.
        inbound_adapters: Channel name -> adapter mapping.
    """

    conversation_store: ConversationStoreProtocol
    recipient_registry: RecipientRegistryProtocol
    outbound_senders: dict[str, OutboundSenderProtocol] = field(default_factory=dict)
    inbound_adapters: dict[str, InboundAdapterProtocol] = field(default_factory=dict)


def build_gateway_components(
    *,
    work_dir: str = ".taskforce",
    extra_senders: dict[str, OutboundSenderProtocol] | None = None,
    extra_adapters: dict[str, InboundAdapterProtocol] | None = None,
) -> GatewayComponents:
    """Build all gateway infrastructure components from environment config.

    Reads environment variables to auto-configure available channels:
    - ``TELEGRAM_BOT_TOKEN``: enables Telegram inbound + outbound
    - ``TEAMS_APP_ID`` / ``TEAMS_APP_PASSWORD``: enables Teams outbound

    Args:
        work_dir: Base directory for file-based stores.
        extra_senders: Additional outbound senders to register.
        extra_adapters: Additional inbound adapters to register.

    Returns:
        Fully wired GatewayComponents ready for CommunicationGateway.
    """
    logger = structlog.get_logger()

    conversation_store = FileConversationStore(work_dir=work_dir)
    recipient_registry = FileRecipientRegistry(work_dir=work_dir)

    senders: dict[str, OutboundSenderProtocol] = dict(extra_senders or {})
    adapters: dict[str, InboundAdapterProtocol] = dict(extra_adapters or {})

    # --- Telegram ---
    telegram_token = os.getenv("TELEGRAM_BOT_TOKEN")
    if telegram_token:
        if "telegram" not in senders:
            senders["telegram"] = TelegramOutboundSender(telegram_token)
            logger.info("gateway.telegram.sender_configured")
        if "telegram" not in adapters:
            adapters["telegram"] = TelegramInboundAdapter(telegram_token)
            logger.info("gateway.telegram.adapter_configured")
    else:
        if "telegram" not in adapters:
            adapters["telegram"] = TelegramInboundAdapter()

    # --- Teams ---
    teams_app_id = os.getenv("TEAMS_APP_ID", "")
    teams_app_password = os.getenv("TEAMS_APP_PASSWORD", "")
    if teams_app_id:
        if "teams" not in senders:
            senders["teams"] = TeamsOutboundSender(teams_app_id, teams_app_password)
            logger.info("gateway.teams.sender_configured")
    if "teams" not in adapters:
        adapters["teams"] = TeamsInboundAdapter()

    return GatewayComponents(
        conversation_store=conversation_store,
        recipient_registry=recipient_registry,
        outbound_senders=senders,
        inbound_adapters=adapters,
    )
