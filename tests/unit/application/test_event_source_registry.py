"""Phase 2 — EventSourceRegistry registration / creation contract."""

from __future__ import annotations

from typing import Any

import pytest

from taskforce.application.event_source_registry import (
    EventSourceRegistry,
    get_event_source_registry,
)


class _FakeSource:
    def __init__(self, name: str = "fake", *, callback=None, extra: Any = None) -> None:
        self._name = name
        self.callback = callback
        self.extra = extra
        self._running = False

    @property
    def source_name(self) -> str:
        return self._name

    @property
    def is_running(self) -> bool:
        return self._running

    async def start(self) -> None:
        self._running = True

    async def stop(self) -> None:
        self._running = False

    @classmethod
    def from_config(cls, config, *, event_callback=None) -> "_FakeSource":
        return cls(
            name=config.get("source_name", "fake"),
            callback=event_callback,
            extra=config.get("extra"),
        )


def test_register_and_create_round_trip() -> None:
    registry = EventSourceRegistry()
    registry.register("fake", _FakeSource.from_config)

    source = registry.create("fake", {"source_name": "alpha", "extra": 1})

    assert source.source_name == "alpha"
    assert source.extra == 1


def test_register_duplicate_without_replace_raises() -> None:
    registry = EventSourceRegistry()
    registry.register("fake", _FakeSource.from_config)
    with pytest.raises(ValueError, match="already registered"):
        registry.register("fake", _FakeSource.from_config)


def test_register_replace_overrides() -> None:
    registry = EventSourceRegistry()
    registry.register("fake", _FakeSource.from_config)

    def alt_factory(config, *, event_callback=None):
        return _FakeSource(name="from-alt-factory")

    registry.register("fake", alt_factory, replace=True)
    assert registry.create("fake").source_name == "from-alt-factory"


def test_create_unknown_raises_keyerror_listing_known() -> None:
    registry = EventSourceRegistry()
    registry.register("fake", _FakeSource.from_config)

    with pytest.raises(KeyError) as exc:
        registry.create("missing")
    assert "missing" in str(exc.value)
    assert "fake" in str(exc.value)


def test_event_callback_is_forwarded_to_factory() -> None:
    registry = EventSourceRegistry()
    registry.register("fake", _FakeSource.from_config)

    sentinel = object()
    source = registry.create("fake", {}, event_callback=sentinel)

    assert source.callback is sentinel


def test_global_registry_is_singleton() -> None:
    a = get_event_source_registry()
    b = get_event_source_registry()
    assert a is b


def test_global_registry_has_framework_sources() -> None:
    """Importing the event_sources package auto-registers the bundled sources."""
    import taskforce.infrastructure.event_sources  # noqa: F401

    registry = get_event_source_registry()
    for expected in ("calendar", "file_watcher", "github", "imap_email", "webhook"):
        assert registry.is_registered(expected), f"{expected!r} not registered"
