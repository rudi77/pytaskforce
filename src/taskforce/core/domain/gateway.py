"""Domain models for the unified Communication Gateway.

All structured types that flow through the gateway: inbound messages,
outbound notifications, gateway responses, and configuration options.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class InboundMessage:
    """Normalized inbound message from any channel.

    Produced by an InboundAdapterProtocol or directly by the API route.

    Attributes:
        channel: Source channel identifier (e.g. 'rest', 'telegram', 'teams').
        conversation_id: Channel-specific conversation/chat identifier.
        message: The user's message text.
        sender_id: Optional user identifier from the channel.
        metadata: Channel-specific extras (update_id, activity type, etc.).
    """

    channel: str
    conversation_id: str
    message: str
    sender_id: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class GatewayOptions:
    """Execution options passed through the gateway to the agent.

    Attributes:
        profile: Agent profile to use (e.g. 'dev', 'coding_agent').
        session_id: Optional explicit session ID override.
        user_context: Optional RAG security context (user_id, org_id, scope).
        agent_id: Optional agent ID override.
        planning_strategy: Optional planning strategy override.
        planning_strategy_params: Optional planning strategy parameters.
        plugin_path: Optional plugin path for external agent tools.
    """

    profile: str = "dev"
    session_id: str | None = None
    user_context: dict[str, Any] | None = None
    agent_id: str | None = None
    planning_strategy: str | None = None
    planning_strategy_params: dict[str, Any] | None = None
    plugin_path: str | None = None


@dataclass(frozen=True)
class GatewayResponse:
    """Result of handling a message through the gateway.

    Attributes:
        session_id: The resolved Taskforce session ID.
        status: Execution status (completed, failed, paused, pending).
        reply: The agent's reply message.
        history: Full conversation history after this exchange.
    """

    session_id: str
    status: str
    reply: str
    history: list[dict[str, Any]] = field(default_factory=list)


@dataclass(frozen=True)
class NotificationRequest:
    """Request to send a proactive push notification.

    Used by the send_notification tool and by event-based triggers.

    Attributes:
        channel: Target channel (e.g. 'telegram', 'teams').
        recipient_id: Application-level user ID (resolved via RecipientRegistry).
        message: Notification message text.
        metadata: Channel-specific formatting options.
    """

    channel: str
    recipient_id: str
    message: str
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class NotificationResult:
    """Result of sending a push notification.

    Attributes:
        success: Whether the notification was delivered.
        channel: Which channel was used.
        recipient_id: Who was notified.
        error: Error message if delivery failed.
    """

    success: bool
    channel: str
    recipient_id: str
    error: str | None = None
