"""Base class for polling event sources.

Provides a shared polling loop that subclasses customize
with their specific poll logic.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable

import structlog

from taskforce.core.domain.agent_event import AgentEvent

logger = structlog.get_logger(__name__)


class PollingEventSource:
    """Base for event sources that poll an external system at a regular interval.

    Subclasses implement ``_poll_once`` to fetch events from their external
    system and return a list of AgentEvents to publish.
    """

    def __init__(
        self,
        source_name: str,
        poll_interval_seconds: float = 300.0,
        event_callback: Callable[[AgentEvent], Awaitable[None]] | None = None,
    ) -> None:
        self._source_name = source_name
        self._poll_interval = poll_interval_seconds
        self._event_callback = event_callback
        self._task: asyncio.Task[None] | None = None
        self._running = False

    @property
    def source_name(self) -> str:
        """Unique name identifying this event source."""
        return self._source_name

    @property
    def is_running(self) -> bool:
        """Whether the polling loop is active."""
        return self._running

    async def start(self) -> None:
        """Start the polling loop."""
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(
            self._poll_loop(), name=f"event-source-{self._source_name}"
        )
        logger.info(
            "event_source.started",
            source=self._source_name,
            interval_s=self._poll_interval,
        )

    async def stop(self) -> None:
        """Stop the polling loop."""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
        logger.info("event_source.stopped", source=self._source_name)

    async def _poll_loop(self) -> None:
        """Run the polling loop, calling _poll_once each interval."""
        try:
            while self._running:
                try:
                    events = await self._poll_once()
                    for event in events:
                        if self._event_callback:
                            await self._event_callback(event)
                except asyncio.CancelledError:
                    raise
                except Exception as exc:
                    logger.warning(
                        "event_source.poll_error",
                        source=self._source_name,
                        error=str(exc),
                    )
                await asyncio.sleep(self._poll_interval)
        except asyncio.CancelledError:
            pass

    async def _poll_once(self) -> list[AgentEvent]:
        """Override in subclass to poll the external system.

        Returns:
            List of AgentEvents detected in this poll cycle.
        """
        raise NotImplementedError
