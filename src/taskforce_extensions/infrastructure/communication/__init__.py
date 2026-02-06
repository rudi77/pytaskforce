"""Communication infrastructure adapters.

Legacy adapters (providers, conversation_store, telegram_sender) are preserved
for backward compatibility. New code should use the gateway components.
"""

# --- Legacy exports (backward compatible) ---
from taskforce_extensions.infrastructure.communication.conversation_store import (
    FileConversationStore as LegacyFileConversationStore,
    InMemoryConversationStore as LegacyInMemoryConversationStore,
)
from taskforce_extensions.infrastructure.communication.providers import (
    BaseCommunicationProvider,
    TeamsProvider,
    TelegramProvider,
)
from taskforce_extensions.infrastructure.communication.registry import (
    build_provider_registry,
)
from taskforce_extensions.infrastructure.communication.telegram_sender import (
    build_telegram_sender,
)

# --- Gateway exports (new unified API) ---
from taskforce_extensions.infrastructure.communication.gateway_conversation_store import (
    FileConversationStore,
    InMemoryConversationStore,
)
from taskforce_extensions.infrastructure.communication.gateway_registry import (
    GatewayComponents,
    build_gateway_components,
)
from taskforce_extensions.infrastructure.communication.inbound_adapters import (
    TeamsInboundAdapter,
    TelegramInboundAdapter,
)
from taskforce_extensions.infrastructure.communication.outbound_senders import (
    TeamsOutboundSender,
    TelegramOutboundSender,
)
from taskforce_extensions.infrastructure.communication.recipient_registry import (
    FileRecipientRegistry,
    InMemoryRecipientRegistry,
)

__all__ = [
    # Legacy
    "BaseCommunicationProvider",
    "LegacyFileConversationStore",
    "LegacyInMemoryConversationStore",
    "TeamsProvider",
    "TelegramProvider",
    "build_provider_registry",
    "build_telegram_sender",
    # Gateway - Stores
    "FileConversationStore",
    "InMemoryConversationStore",
    "FileRecipientRegistry",
    "InMemoryRecipientRegistry",
    # Gateway - Channel adapters
    "TelegramOutboundSender",
    "TeamsOutboundSender",
    "TelegramInboundAdapter",
    "TeamsInboundAdapter",
    # Gateway - Wiring
    "GatewayComponents",
    "build_gateway_components",
]
