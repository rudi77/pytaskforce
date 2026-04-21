"""Unit tests for the PollingEventSource base class."""

from __future__ import annotations

import asyncio

import pytest

from taskforce.core.domain.agent_event import AgentEvent, AgentEventType
from taskforce.infrastructure.event_sources.polling_base import PollingEventSource


class _StubSource(PollingEventSource):
    def __init__(self, *args, events_per_poll: list[list[AgentEvent]], **kwargs):
        super().__init__(*args, **kwargs)
        self._batches = events_per_poll
        self.poll_count = 0

    async def _poll_once(self) -> list[AgentEvent]:
        idx = self.poll_count
        self.poll_count += 1
        if idx < len(self._batches):
            return self._batches[idx]
        return []


class _CrashingSource(PollingEventSource):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.poll_count = 0

    async def _poll_once(self) -> list[AgentEvent]:
        self.poll_count += 1
        raise RuntimeError("external system down")


def _event(source: str = "stub") -> AgentEvent:
    return AgentEvent(source=source, event_type=AgentEventType.CUSTOM)


class TestPollingEventSource:
    async def test_start_is_idempotent(self) -> None:
        src = _StubSource("stub", poll_interval_seconds=10, events_per_poll=[])
        try:
            await src.start()
            await src.start()  # second call is a no-op
            assert src.is_running is True
        finally:
            await src.stop()

    async def test_not_running_before_start(self) -> None:
        src = _StubSource("stub", poll_interval_seconds=10, events_per_poll=[])
        assert src.is_running is False

    async def test_poll_once_not_implemented_by_default(self) -> None:
        src = PollingEventSource("bare", poll_interval_seconds=10)
        with pytest.raises(NotImplementedError):
            await src._poll_once()

    async def test_events_are_forwarded_to_callback(self) -> None:
        received: list[AgentEvent] = []

        async def on_event(event: AgentEvent) -> None:
            received.append(event)

        evt = _event()
        src = _StubSource(
            "stub",
            poll_interval_seconds=0.01,
            event_callback=on_event,
            events_per_poll=[[evt]],
        )
        await src.start()
        try:
            # Wait for at least one poll cycle to complete.
            for _ in range(50):
                if received:
                    break
                await asyncio.sleep(0.01)
        finally:
            await src.stop()
        assert received == [evt]

    async def test_poll_errors_are_swallowed_and_loop_continues(self) -> None:
        src = _CrashingSource("boom", poll_interval_seconds=0.01)
        await src.start()
        try:
            # Let the loop iterate a few times to ensure it doesn't die on error.
            for _ in range(20):
                if src.poll_count >= 2:
                    break
                await asyncio.sleep(0.01)
        finally:
            await src.stop()
        assert src.poll_count >= 2
        assert src.is_running is False

    async def test_stop_cancels_running_task(self) -> None:
        src = _StubSource("stub", poll_interval_seconds=10, events_per_poll=[])
        await src.start()
        await src.stop()
        assert src.is_running is False

    def test_source_name_property(self) -> None:
        src = _StubSource("my-source", events_per_poll=[])
        assert src.source_name == "my-source"
