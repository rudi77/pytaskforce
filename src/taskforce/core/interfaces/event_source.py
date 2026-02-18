"""Event Source Protocol for external event ingestion.

Defines the contract for components that listen to external systems
(calendars, email, webhooks, file changes) and publish AgentEvents
to the internal message bus.
"""

from typing import Protocol


class EventSourceProtocol(Protocol):
    """Protocol for external event sources that feed into the butler.

    Event sources are long-running components that poll or listen for
    external events and publish them as AgentEvents on the message bus.

    Lifecycle:
        1. Source is created and configured
        2. start() begins polling/listening
        3. Events are published to the message bus as they occur
        4. stop() gracefully shuts down the source
    """

    @property
    def source_name(self) -> str:
        """Unique name identifying this event source (e.g. 'calendar', 'email').

        Returns:
            Source name string.
        """
        ...

    @property
    def is_running(self) -> bool:
        """Whether the event source is currently active.

        Returns:
            True if the source is running and producing events.
        """
        ...

    async def start(self) -> None:
        """Begin polling or listening for events.

        This method should start a background task that polls the external
        system and publishes AgentEvents to the message bus.
        """
        ...

    async def stop(self) -> None:
        """Gracefully stop the event source.

        Should cancel any pending polls and clean up resources.
        """
        ...
