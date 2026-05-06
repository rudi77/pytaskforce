"""Backward-compatibility shim — moved to ``taskforce.infrastructure.event_sources``.

See :mod:`taskforce.infrastructure.event_sources.webhook_source` for the
canonical implementation.
"""

from __future__ import annotations

import warnings

from taskforce.infrastructure.event_sources.webhook_source import (
    WebhookEventSource as _WebhookEventSource,
)

warnings.warn(
    "Importing WebhookEventSource from taskforce_butler is deprecated; "
    "use taskforce.infrastructure.event_sources.webhook_source instead.",
    DeprecationWarning,
    stacklevel=2,
)


WebhookEventSource = _WebhookEventSource

__all__ = ["WebhookEventSource"]
