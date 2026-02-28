"""Communication infrastructure adapters.

Gateway components for unified channel-based agent communication:
- OutboundSenders: deliver messages to Telegram, Teams, etc.
- InboundAdapters: normalize raw webhooks from providers
- ConversationStore: persist session mappings and chat history
- RecipientRegistry: track recipients for push notifications
- GatewayRegistry: auto-configure components from environment
"""

# --- Stores ---
from taskforce.infrastructure.communication.gateway_conversation_store import (
    FileConversationStore,
    InMemoryConversationStore,
)

# --- Wiring ---
from taskforce.infrastructure.communication.gateway_registry import (
    GatewayComponents,
    build_gateway_components,
)
from taskforce.infrastructure.communication.inbound_adapters import (
    TeamsInboundAdapter,
    TelegramInboundAdapter,
)

# --- Channel adapters ---
from taskforce.infrastructure.communication.outbound_senders import (
    TeamsOutboundSender,
    TelegramOutboundSender,
)
from taskforce.infrastructure.communication.recipient_registry import (
    FileRecipientRegistry,
    InMemoryRecipientRegistry,
)

__all__ = [
    # Stores
    "FileConversationStore",
    "InMemoryConversationStore",
    "FileRecipientRegistry",
    "InMemoryRecipientRegistry",
    # Channel adapters
    "TelegramOutboundSender",
    "TeamsOutboundSender",
    "TelegramInboundAdapter",
    "TeamsInboundAdapter",
    # Wiring
    "GatewayComponents",
    "build_gateway_components",
]
