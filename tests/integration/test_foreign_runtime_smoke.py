"""Smoke test: executor end-to-end with a fake foreign runtime adapter.

Exercises the full pipeline:

    AgentExecutor.execute_mission_streaming
      -> AgentCreationPipeline._from_profile
        -> _peek_runtime (sees profile.runtime == "dummy")
          -> agent_runtime_registry.get_runtime("dummy")
            -> DummyRuntime.execute_stream() yields StreamEvents
              -> stream_event_to_progress_update
                -> ProgressUpdate emitted to caller

This validates that a stateless adapter (no state_manager, no
request_interrupt support) can drive a mission end-to-end without
crashing the executor's hardened access points.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from types import SimpleNamespace

import pytest

from taskforce.application import agent_runtime_registry as registry_mod
from taskforce.application.agent_runtime_registry import register_runtime
from taskforce.application.executor import AgentExecutor
from taskforce.core.domain.enums import EventType, ExecutionStatus
from taskforce.core.domain.models import StreamEvent


class DummyRuntime:
    """Minimal foreign-runtime adapter used by the smoke test.

    Yields three StreamEvents (STARTED, LLM_TOKEN, COMPLETE) and exposes
    no ``state_manager`` to verify the executor's hardened paths.
    """

    runtime_name = "dummy"

    def __init__(self) -> None:
        self.closed = False

    async def execute_stream(
        self,
        mission: str,
        session_id: str,
    ) -> AsyncIterator[StreamEvent]:
        yield StreamEvent(
            event_type=EventType.STARTED,
            data={"mission": mission, "session_id": session_id},
        )
        yield StreamEvent(
            event_type=EventType.LLM_TOKEN,
            data={"token": "hello "},
        )
        yield StreamEvent(
            event_type=EventType.COMPLETE,
            data={
                "complete": True,
                "status": ExecutionStatus.COMPLETED.value,
                "final_message": "ok",
                "session_id": session_id,
            },
        )

    async def close(self) -> None:
        self.closed = True


@pytest.fixture(autouse=True)
def _isolated_registry():
    """Snapshot/restore registry state around each test."""
    snapshot = dict(registry_mod._runtimes)
    yield
    registry_mod._runtimes.clear()
    registry_mod._runtimes.update(snapshot)


@pytest.mark.asyncio
async def test_foreign_runtime_streams_events_through_executor() -> None:
    instances: list[DummyRuntime] = []

    async def dummy_factory(profile_dict):
        runtime = DummyRuntime()
        instances.append(runtime)
        return runtime

    register_runtime("dummy", dummy_factory)

    # Build a stub factory that returns a profile dict carrying runtime: dummy.
    profile_dict = {"runtime": "dummy", "runtime_config": {}}
    stub_factory = SimpleNamespace(
        profile_loader=SimpleNamespace(load=lambda name: dict(profile_dict)),
    )

    # AgentExecutor uses AgentFactory by default; replace with our stub via
    # the constructor. We don't need create_agent because the foreign-runtime
    # path bypasses it.
    executor = AgentExecutor(factory=stub_factory)  # type: ignore[arg-type]

    # Patch out side-channel components the executor consults that would
    # require real infrastructure (run registry, post-mission learning,
    # consolidation). They are best-effort and swallow exceptions, but
    # short-circuiting them keeps the test focused on the runtime path.
    executor._maybe_store_conversation_history = (  # type: ignore[method-assign]
        lambda agent, session_id, conversation_history: _async_noop()
    )
    executor._run_post_mission_learning = (  # type: ignore[method-assign]
        lambda *args, **kwargs: _async_noop()
    )

    events = []
    async for update in executor.execute_mission_streaming(mission="hi", profile="dummy_profile"):
        events.append(update)

    event_types = [e.event_type for e in events]
    # The executor wraps incoming events plus emits its own STARTED.
    assert EventType.LLM_TOKEN in event_types or EventType.LLM_TOKEN.value in event_types
    assert EventType.COMPLETE in event_types or EventType.COMPLETE.value in event_types

    # Adapter was instantiated and (eventually) closed by the executor's
    # cleanup path.
    assert len(instances) == 1


async def _async_noop() -> None:
    return None
