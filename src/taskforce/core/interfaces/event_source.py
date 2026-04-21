"""Protocol for external event sources that feed events into the framework."""

from __future__ import annotations

from typing import Protocol


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
