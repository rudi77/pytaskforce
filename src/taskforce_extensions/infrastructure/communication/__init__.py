"""Communication infrastructure adapters."""

from taskforce_extensions.infrastructure.communication.conversation_store import (
    FileConversationStore,
    InMemoryConversationStore,
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

__all__ = [
    "BaseCommunicationProvider",
    "FileConversationStore",
    "InMemoryConversationStore",
    "TeamsProvider",
    "TelegramProvider",
    "build_provider_registry",
    "build_telegram_sender",
]
