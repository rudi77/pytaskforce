"""Plugin registry for event sources.

Mirrors the pattern used by ``application/tool_registry.py`` and
``application/agent_registry.py``: a process-wide singleton holds
``name -> factory`` mappings, and any consumer (the butler daemon, the
REST events route, tests) instantiates an event source by name with a
config dict — no hard-coded if/elif chain.

A factory is any callable that takes a config dict plus an optional
``event_callback`` keyword and returns an object satisfying
:class:`taskforce.core.interfaces.event_source.EventSourceProtocol`.
Factories may be registered both by the framework's own
``infrastructure/event_sources/__init__.py`` (auto-registration) and by
agent packages such as ``taskforce_butler`` for sources that depend on
agent-specific credentials.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

import structlog

from taskforce.core.domain.agent_event import AgentEvent
from taskforce.core.interfaces.event_source import EventSourceProtocol

logger = structlog.get_logger(__name__)


EventCallback = Callable[[AgentEvent], Awaitable[None]]
EventSourceFactory = Callable[..., EventSourceProtocol]


class EventSourceRegistry:
    """Maps event-source type names to factory callables.

    Factories receive the source's config dict (everything from the YAML
    block except ``type``) and the optional ``event_callback`` the
    daemon will use to publish ``AgentEvent``s. They must return an
    object that implements :class:`EventSourceProtocol`.
    """

    def __init__(self) -> None:
        self._factories: dict[str, EventSourceFactory] = {}

    def register(
        self,
        name: str,
        factory: EventSourceFactory,
        *,
        replace: bool = False,
    ) -> None:
        """Register a factory under ``name``.

        Set ``replace=True`` to overwrite an existing entry — useful for
        tests that swap implementations. The default raises so a typo
        in an agent package does not silently shadow a framework source.
        """
        if not replace and name in self._factories:
            raise ValueError(
                f"Event source factory {name!r} is already registered. "
                "Pass replace=True to override."
            )
        self._factories[name] = factory
        logger.debug("event_source_registry.registered", name=name)

    def unregister(self, name: str) -> None:
        """Remove a factory; no-op if not registered."""
        self._factories.pop(name, None)

    def list(self) -> list[str]:
        """Return the names of every registered factory (sorted)."""
        return sorted(self._factories.keys())

    def is_registered(self, name: str) -> bool:
        return name in self._factories

    def create(
        self,
        name: str,
        config: dict[str, Any] | None = None,
        *,
        event_callback: EventCallback | None = None,
    ) -> EventSourceProtocol:
        """Build an event source from its registered factory.

        Raises ``KeyError`` when no factory exists for ``name`` so the
        butler daemon's YAML loader can produce a clear error pointing
        at the offending profile entry.
        """
        if name not in self._factories:
            raise KeyError(
                f"No event source factory registered for {name!r}. "
                f"Known factories: {self.list()}"
            )
        return self._factories[name](config or {}, event_callback=event_callback)


_GLOBAL_EVENT_SOURCE_REGISTRY = EventSourceRegistry()


def get_event_source_registry() -> EventSourceRegistry:
    """Return the process-wide ``EventSourceRegistry`` singleton."""
    return _GLOBAL_EVENT_SOURCE_REGISTRY


def register_event_source(
    name: str,
    factory: EventSourceFactory,
    *,
    replace: bool = False,
) -> None:
    """Convenience helper for module-level auto-registration.

    Example::

        from taskforce.application.event_source_registry import register_event_source
        from taskforce.infrastructure.event_sources.file_watcher_source import (
            FileWatcherEventSource,
        )

        register_event_source("file_watcher", FileWatcherEventSource.from_config)
    """
    _GLOBAL_EVENT_SOURCE_REGISTRY.register(name, factory, replace=replace)
