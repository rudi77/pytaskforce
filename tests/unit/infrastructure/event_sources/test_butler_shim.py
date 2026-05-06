"""Backward-compat: importing from the old butler path still works."""

from __future__ import annotations

import importlib
import warnings


def test_butler_calendar_shim_emits_deprecation_warning() -> None:
    """The shim re-exports the framework class but warns on import."""
    # Force reload so the import-time ``warnings.warn`` fires regardless
    # of what other tests have already cached.
    module_name = "taskforce_butler.infrastructure.event_sources.calendar_source"
    if module_name in importlib.sys.modules:
        del importlib.sys.modules[module_name]

    with warnings.catch_warnings(record=True) as captured:
        warnings.simplefilter("always")
        importlib.import_module(module_name)

    assert any(
        issubclass(w.category, DeprecationWarning) and "CalendarEventSource" in str(w.message)
        for w in captured
    )

    from taskforce.infrastructure.event_sources.calendar_source import (
        CalendarEventSource as Canonical,
    )
    from taskforce_butler.infrastructure.event_sources.calendar_source import (
        CalendarEventSource as Shim,
    )

    assert Shim is Canonical


def test_butler_webhook_shim_emits_deprecation_warning() -> None:
    module_name = "taskforce_butler.infrastructure.event_sources.webhook_source"
    if module_name in importlib.sys.modules:
        del importlib.sys.modules[module_name]

    with warnings.catch_warnings(record=True) as captured:
        warnings.simplefilter("always")
        importlib.import_module(module_name)

    assert any(
        issubclass(w.category, DeprecationWarning) and "WebhookEventSource" in str(w.message)
        for w in captured
    )

    from taskforce.infrastructure.event_sources.webhook_source import (
        WebhookEventSource as Canonical,
    )
    from taskforce_butler.infrastructure.event_sources.webhook_source import (
        WebhookEventSource as Shim,
    )

    assert Shim is Canonical
