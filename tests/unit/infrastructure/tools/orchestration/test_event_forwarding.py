"""Tests for sub-agent event forwarding helper.

These tests verify that sub-agent ``StreamEvent``s are forwarded to the
parent's ``asyncio.Queue`` annotated with ``agent_path``,
``parent_session_id`` and ``source_agent`` so the management UI can render
nested tool calls.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator

import pytest

from taskforce.core.domain.enums import EventType, ExecutionStatus
from taskforce.core.domain.models import StreamEvent
from taskforce.infrastructure.tools.orchestration._event_forwarding import (
    run_sub_agent_with_forwarding,
)


class _FakeAgent:
    """Minimal stub that mimics ``Agent.execute_stream``."""

    def __init__(self, events: list[StreamEvent]) -> None:
        self._events = events
        self._sub_agent_event_sink: asyncio.Queue[StreamEvent] | None = None
        self._agent_path: list[str] = []

    async def execute_stream(
        self, mission: str, session_id: str
    ) -> AsyncIterator[StreamEvent]:
        for event in self._events:
            yield event


@pytest.mark.asyncio
async def test_forwards_tool_events_with_annotations() -> None:
    sink: asyncio.Queue[StreamEvent] = asyncio.Queue()
    agent = _FakeAgent(
        [
            StreamEvent(
                event_type=EventType.TOOL_CALL,
                data={"tool": "python", "id": "t1", "args": {}},
            ),
            StreamEvent(
                event_type=EventType.TOOL_RESULT,
                data={"tool": "python", "id": "t1", "success": True, "output": "42"},
            ),
            # FINAL_ANSWER must NOT be forwarded — parent-stream
            # consumers would otherwise splice the sub-agent's text
            # into the parent's assistant reply.
            StreamEvent(
                event_type=EventType.FINAL_ANSWER,
                data={"content": "done"},
            ),
            # COMPLETE belongs to the sub-agent lifecycle and is also
            # not forwarded.
            StreamEvent(
                event_type=EventType.COMPLETE,
                data={
                    "status": ExecutionStatus.COMPLETED.value,
                    "final_message": "done",
                },
            ),
        ]
    )

    outcome = await run_sub_agent_with_forwarding(
        agent,
        mission="m",
        session_id="root--sub_coding_abcd",
        parent_session_id="root",
        parent_event_sink=sink,
        parent_agent_path=[],
        specialist="coding_worker",
    )

    forwarded: list[StreamEvent] = []
    while not sink.empty():
        forwarded.append(sink.get_nowait())

    # Only tool-trace events are forwarded; FINAL_ANSWER and COMPLETE are
    # consumed locally and surfaced via the sub-agent tool's return value.
    assert [e.event_type for e in forwarded] == [
        EventType.TOOL_CALL,
        EventType.TOOL_RESULT,
    ]
    for event in forwarded:
        assert event.data["agent_path"] == ["coding_worker"]
        assert event.data["parent_session_id"] == "root"
        assert event.data["source_agent"] == "coding_worker"

    # Sub-agent attributes wired up so nested sub-agents can forward through.
    assert agent._sub_agent_event_sink is sink
    assert agent._agent_path == ["coding_worker"]

    assert outcome.success
    assert outcome.status == ExecutionStatus.COMPLETED.value
    assert outcome.final_message == "done"


@pytest.mark.asyncio
async def test_does_not_forward_text_or_terminal_events() -> None:
    """Sub-agent text/terminal events stay internal to avoid corrupting
    the parent's assistant reply or triggering parent-level error /
    interrupt handling."""

    sink: asyncio.Queue[StreamEvent] = asyncio.Queue()
    agent = _FakeAgent(
        [
            StreamEvent(event_type=EventType.LLM_TOKEN, data={"content": "hi"}),
            StreamEvent(event_type=EventType.FINAL_ANSWER, data={"content": "done"}),
            StreamEvent(event_type=EventType.ASK_USER, data={"question": "?"}),
            StreamEvent(event_type=EventType.ERROR, data={"error": "boom"}),
            StreamEvent(event_type=EventType.INTERRUPTED, data={}),
            # STEP_START + TOKEN_USAGE *are* forwarded so the trace UI
            # and cost-aggregation continue to work.
            StreamEvent(event_type=EventType.STEP_START, data={"step": 1}),
            StreamEvent(
                event_type=EventType.TOKEN_USAGE,
                data={"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
            ),
        ]
    )

    await run_sub_agent_with_forwarding(
        agent,
        mission="m",
        session_id="s",
        parent_session_id="root",
        parent_event_sink=sink,
        parent_agent_path=[],
        specialist="worker",
    )

    forwarded: list[StreamEvent] = []
    while not sink.empty():
        forwarded.append(sink.get_nowait())

    assert [e.event_type for e in forwarded] == [
        EventType.STEP_START,
        EventType.TOKEN_USAGE,
    ]


@pytest.mark.asyncio
async def test_no_sink_collects_outcome_without_forwarding() -> None:
    """When the parent did not install a sink, events are simply consumed."""
    agent = _FakeAgent(
        [
            StreamEvent(
                event_type=EventType.FINAL_ANSWER,
                data={"content": "ok"},
            ),
            StreamEvent(
                event_type=EventType.COMPLETE,
                data={
                    "status": ExecutionStatus.COMPLETED.value,
                    "final_message": "ok",
                },
            ),
        ]
    )

    outcome = await run_sub_agent_with_forwarding(
        agent,
        mission="m",
        session_id="s",
        parent_session_id="root",
        parent_event_sink=None,
        parent_agent_path=[],
        specialist=None,
    )

    assert outcome.final_message == "ok"
    assert outcome.success


@pytest.mark.asyncio
async def test_extends_parent_agent_path_for_nested_specialists() -> None:
    """A sub-sub-agent's path appends to the parent's path."""
    sink: asyncio.Queue[StreamEvent] = asyncio.Queue()
    agent = _FakeAgent(
        [
            StreamEvent(
                event_type=EventType.TOOL_CALL,
                data={"tool": "edit", "id": "t1", "args": {}},
            ),
        ]
    )

    await run_sub_agent_with_forwarding(
        agent,
        mission="m",
        session_id="s",
        parent_session_id="root--sub_planner",
        parent_event_sink=sink,
        parent_agent_path=["planner"],
        specialist="worker",
    )

    forwarded = sink.get_nowait()
    assert forwarded.data["agent_path"] == ["planner", "worker"]
    assert forwarded.data["source_agent"] == "worker"


@pytest.mark.asyncio
async def test_existing_annotations_are_preserved() -> None:
    """Events already carrying agent_path (from deeper nesting) are not overwritten."""
    sink: asyncio.Queue[StreamEvent] = asyncio.Queue()
    agent = _FakeAgent(
        [
            StreamEvent(
                event_type=EventType.TOOL_CALL,
                data={
                    "tool": "python",
                    "id": "t1",
                    "agent_path": ["worker", "deep_specialist"],
                    "parent_session_id": "worker-session",
                    "source_agent": "deep_specialist",
                },
            ),
        ]
    )

    await run_sub_agent_with_forwarding(
        agent,
        mission="m",
        session_id="s",
        parent_session_id="root",
        parent_event_sink=sink,
        parent_agent_path=[],
        specialist="worker",
    )

    forwarded = sink.get_nowait()
    # Pre-existing annotations from a deeper sub-agent are preserved.
    assert forwarded.data["agent_path"] == ["worker", "deep_specialist"]
    assert forwarded.data["source_agent"] == "deep_specialist"
