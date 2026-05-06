"""Protocol for external event sources that feed events into the framework."""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable


class EventSourceProtocol(Protocol):
    """Protocol for external event sources.

    Event sources ingest events from external systems (calendars, webhooks,
    file-system watchers, etc.) and publish them as AgentEvents.
    """

    @property
    def source_name(self) -> str:
        """Unique name identifying this event source."""
        ...

    @property
    def is_running(self) -> bool:
        """Whether the event source is currently active."""
        ...

    async def start(self) -> None:
        """Begin polling or listening for events."""
        ...

    async def stop(self) -> None:
        """Gracefully stop the event source."""
        ...


@runtime_checkable
class WebhookCapableEventSource(Protocol):
    """Optional capability — push-based sources that accept inbound HTTP.

    Implemented by event sources that should be reachable through the
    generic ``POST /api/v1/events/{source_name}`` endpoint. The default
    framework webhook source implements it; specialized sources
    (GitHubWebhookSource) override it to verify provider-specific
    signatures and emit normalized payloads.

    The protocol is ``runtime_checkable`` so the API route can use
    ``isinstance`` to filter the registry without forcing every source
    to inherit a concrete base class.
    """

    @property
    def source_name(self) -> str:
        ...

    async def handle_inbound(
        self,
        payload: dict[str, Any],
        headers: dict[str, str] | None = None,
    ) -> Any:
        """Translate an inbound HTTP payload into an ``AgentEvent``.

        Implementations are expected to verify provider-specific
        signatures (HMAC, JWT) themselves and raise to signal a 401.
        """
        ...
