"""Webhook event source for receiving external HTTP events.

Provides a FastAPI-compatible router that external systems can POST to,
converting incoming payloads into AgentEvents.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

import structlog

from taskforce.core.domain.agent_event import AgentEvent, AgentEventType

logger = structlog.get_logger(__name__)


class WebhookEventSource:
    """Receives external HTTP webhooks and publishes them as AgentEvents.

    Unlike polling sources, this is push-based: external systems POST
    payloads that get converted into events. The actual HTTP endpoint
    is registered via the butler daemon's FastAPI app.
    """

    def __init__(
        self,
        event_callback: Callable[[AgentEvent], Awaitable[None]] | None = None,
    ) -> None:
        self._source_name = "webhook"
        self._event_callback = event_callback
        self._running = False

    @property
    def source_name(self) -> str:
        """Source name identifier."""
        return self._source_name

    @property
    def is_running(self) -> bool:
        """Whether the source is accepting webhooks."""
        return self._running

    async def start(self) -> None:
        """Mark the source as active."""
        self._running = True
        logger.info("webhook_source.started")

    async def stop(self) -> None:
        """Mark the source as inactive."""
        self._running = False
        logger.info("webhook_source.stopped")

    async def handle_webhook(
        self,
        source_label: str,
        payload: dict[str, Any],
        metadata: dict[str, Any] | None = None,
    ) -> AgentEvent:
        """Process an incoming webhook payload into an AgentEvent.

        Called by the FastAPI route handler when a webhook is received.

        Args:
            source_label: Label identifying the webhook sender (e.g. "github", "jira").
            payload: The raw webhook payload.
            metadata: Additional metadata (headers, IP, etc.).

        Returns:
            The created AgentEvent.
        """
        event = AgentEvent(
            source=f"webhook.{source_label}",
            event_type=AgentEventType.WEBHOOK_RECEIVED,
            payload=payload,
            metadata=metadata or {},
        )

        logger.info(
            "webhook_source.event_received",
            source_label=source_label,
            event_id=event.event_id,
        )

        if self._event_callback:
            await self._event_callback(event)

        return event
