"""Backward-compatibility shim — moved to ``taskforce.infrastructure.event_sources``.

The class lives in the framework package now so non-butler profiles can
use it via the EventSourceRegistry. Importing from this old path still
works but emits a ``DeprecationWarning`` and resolves to the new
location.
"""

from __future__ import annotations

import warnings

from taskforce.infrastructure.event_sources.calendar_source import (
    CalendarEventSource as _CalendarEventSource,
)

warnings.warn(
    "Importing CalendarEventSource from taskforce_butler is deprecated; "
    "use taskforce.infrastructure.event_sources.calendar_source instead.",
    DeprecationWarning,
    stacklevel=2,
)


CalendarEventSource = _CalendarEventSource

__all__ = ["CalendarEventSource"]
