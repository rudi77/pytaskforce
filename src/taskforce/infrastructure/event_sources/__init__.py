"""Event source infrastructure for external event ingestion.

Importing this package auto-registers every framework-bundled source in
the global :class:`taskforce.application.event_source_registry.EventSourceRegistry`
so the butler daemon (and any other host) can build sources by name
without referencing concrete classes.

Sources added by agent packages register themselves the same way from
their own ``__init__`` modules.
"""

from __future__ import annotations

from taskforce.application.event_source_registry import register_event_source
from taskforce.infrastructure.event_sources.calendar_source import CalendarEventSource
from taskforce.infrastructure.event_sources.file_watcher_source import (
    FileWatcherEventSource,
)
from taskforce.infrastructure.event_sources.github_webhook_source import (
    GitHubWebhookEventSource,
)
from taskforce.infrastructure.event_sources.imap_email_source import (
    IMAPEmailEventSource,
)
from taskforce.infrastructure.event_sources.polling_base import PollingEventSource
from taskforce.infrastructure.event_sources.webhook_source import WebhookEventSource

# Auto-register on import. ``replace=True`` keeps re-imports (e.g. test
# reloads, multiple worker processes in the same interpreter) safe.
register_event_source("calendar", CalendarEventSource.from_config, replace=True)
register_event_source("file_watcher", FileWatcherEventSource.from_config, replace=True)
register_event_source("github", GitHubWebhookEventSource.from_config, replace=True)
register_event_source("imap_email", IMAPEmailEventSource.from_config, replace=True)
register_event_source("webhook", WebhookEventSource.from_config, replace=True)


__all__ = [
    "CalendarEventSource",
    "FileWatcherEventSource",
    "GitHubWebhookEventSource",
    "IMAPEmailEventSource",
    "PollingEventSource",
    "WebhookEventSource",
]
