"""Spec-coverage tests for the ReAct loop & planning strategies.

These drive a real ``Agent`` (or planning strategy) with a deterministic
mock LLM provider and assert the event-stream contract from
``docs/spec/react-loop.md``.

Spec: docs/spec/react-loop.md — tests tagged @pytest.mark.spec("react-loop.*").
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from taskforce.core.domain.agent import Agent
from taskforce.core.domain.enums import EventType, ExecutionStatus
from taskforce.core.domain.models import StreamEvent
from taskforce.core.domain.planning import _collect_result
from taskforce.core.domain.planning_strategy import PlanAndExecuteStrategy

_TERMINAL = {
    EventType.FINAL_ANSWER,
    EventType.ASK_USER,
    EventType.INTERRUPTED,
    EventType.ERROR,
}
_INTERMEDIATE = {
    EventType.STEP_START,
    EventType.LLM_TOKEN,
    EventType.LLM_STREAM_RESTART,
    EventType.TOOL_CALL,
    EventType.TOOL_RESULT,
    EventType.PLAN_UPDATED,
    EventType.TOKEN_USAGE,
}


def _make_agent(
    *,
    stream_factory,
    tools: list | None = None,
    max_steps: int = 10,
) -> Agent:
    """Build a real Agent wired to a mock streaming LLM provider."""
    state_manager = AsyncMock()
    state_manager.load_state.return_value = {"answers": {}}
    provider = AsyncMock()
    provider.complete_stream = MagicMock(side_effect=stream_factory)
    return Agent(
        state_manager=state_manager,
        llm_provider=provider,
        tools=tools or [],
        logger=MagicMock(),
        max_steps=max_steps,
    )


async def _final_answer_stream(**_kwargs: Any):
    """A single LLM turn that produces plain text → FINAL_ANSWER."""
    for chunk in ("Hello ", "world."):
        yield {"type": "token", "content": chunk}
    yield {
        "type": "done",
        "usage": {"prompt_tokens": 7, "completion_tokens": 3, "total_tokens": 10},
    }


async def _events(agent: Agent, mission: str, session_id: str) -> list[StreamEvent]:
    return [e async for e in agent.execute_stream(mission, session_id)]


# ---------------------------------------------------------------------------
# Event-stream ordering contract
# ---------------------------------------------------------------------------


@pytest.mark.spec("react-loop.event_order_started_to_complete")
@pytest.mark.asyncio
async def test_event_order_started_to_complete() -> None:
    """COMPLETE is last; every event before the terminal one is intermediate."""
    agent = _make_agent(stream_factory=lambda **kw: _final_answer_stream(**kw))
    events = await _events(agent, "Say hello", "s1")

    types = [e.event_type for e in events]
    assert types[-1] == EventType.COMPLETE, "COMPLETE must be the final event"

    terminal_idx = next(i for i, t in enumerate(types) if t in _TERMINAL)
    # Everything before the terminal event is an intermediate event.
    assert all(t in _INTERMEDIATE for t in types[:terminal_idx])
    # Exactly one terminal event, and it sits between intermediates and COMPLETE.
    assert sum(1 for t in types if t in _TERMINAL) == 1


@pytest.mark.spec("react-loop.terminal_event_precedes_complete")
@pytest.mark.asyncio
async def test_terminal_event_precedes_complete() -> None:
    """The single terminal event is emitted immediately before COMPLETE."""
    agent = _make_agent(stream_factory=lambda **kw: _final_answer_stream(**kw))
    events = await _events(agent, "Say hello", "s1")

    assert events[-1].event_type == EventType.COMPLETE
    assert events[-2].event_type == EventType.FINAL_ANSWER
    assert events[-2].event_type in _TERMINAL


@pytest.mark.spec("react-loop.token_usage_emitted_before_complete")
@pytest.mark.asyncio
async def test_token_usage_emitted_before_complete() -> None:
    """A TOKEN_USAGE event is emitted at least once, before COMPLETE."""
    agent = _make_agent(stream_factory=lambda **kw: _final_answer_stream(**kw))
    events = await _events(agent, "Say hello", "s1")

    types = [e.event_type for e in events]
    assert EventType.TOKEN_USAGE in types
    assert types.index(EventType.TOKEN_USAGE) < types.index(EventType.COMPLETE)


@pytest.mark.spec("react-loop.streaming_and_blocking_yield_equivalent_results")
@pytest.mark.asyncio
async def test_streaming_and_blocking_yield_equivalent_results() -> None:
    """``execute()`` and collecting ``execute_stream()`` agree on the result."""
    agent = _make_agent(stream_factory=lambda **kw: _final_answer_stream(**kw))

    blocking = await agent.execute("Say hello", "s-block")

    streamed = await _events(agent, "Say hello", "s-stream")
    complete = streamed[-1]
    assert complete.event_type == EventType.COMPLETE

    assert str(blocking.status) == str(ExecutionStatus.COMPLETED) or blocking.status in (
        ExecutionStatus.COMPLETED,
        "completed",
    )
    assert blocking.final_message == complete.data["final_message"] == "Hello world."


# ---------------------------------------------------------------------------
# max_steps termination
# ---------------------------------------------------------------------------


def _make_noop_tool() -> MagicMock:
    tool = MagicMock()
    tool.name = "noop"
    tool.description = "no-op tool"
    tool.parameters_schema = {"type": "object", "properties": {}}
    tool.execute = AsyncMock(return_value={"success": True, "output": "ok"})
    return tool


async def _always_tool_call_stream(**_kwargs: Any):
    """An LLM turn that always asks for a tool call → never produces an answer."""
    yield {
        "type": "tool_call_end",
        "index": 0,
        "id": "call_1",
        "name": "noop",
        "arguments": "{}",
    }
    yield {"type": "done", "usage": {}}


@pytest.mark.spec("react-loop.max_steps_terminates_with_error_kind")
@pytest.mark.asyncio
async def test_max_steps_terminates_with_error_kind() -> None:
    """Hitting max_steps without an answer emits ERROR tagged max_steps_reached."""
    agent = _make_agent(
        stream_factory=lambda **kw: _always_tool_call_stream(**kw),
        tools=[_make_noop_tool()],
        max_steps=2,
    )
    events = await _events(agent, "loop forever", "s1")

    error_events = [e for e in events if e.event_type == EventType.ERROR]
    assert error_events, "max_steps exhaustion must emit a terminal ERROR event"
    assert error_events[-1].data.get("error_kind") == "max_steps_reached"


@pytest.mark.spec("react-loop.max_steps_terminates_with_error_kind")
@pytest.mark.asyncio
async def test_max_steps_terminates_not_empty_completion() -> None:
    """Companion to the xfail above: max_steps never yields a clean empty stream.

    Asserts only the part of the invariant that currently holds — the loop
    stops at the cap with a terminal ERROR and a failed COMPLETE, never an
    empty/clean completion.
    """
    agent = _make_agent(
        stream_factory=lambda **kw: _always_tool_call_stream(**kw),
        tools=[_make_noop_tool()],
        max_steps=2,
    )
    events = await _events(agent, "loop forever", "s1")

    assert any(e.event_type == EventType.ERROR for e in events)
    complete = events[-1]
    assert complete.event_type == EventType.COMPLETE
    assert complete.data["status"] == ExecutionStatus.FAILED.value


# ---------------------------------------------------------------------------
# Terminal-status mapping (_collect_result)
# ---------------------------------------------------------------------------


async def _stream(events: list[StreamEvent]):
    for e in events:
        yield e


@pytest.mark.spec("react-loop.ask_user_pauses_execution_with_paused_status")
@pytest.mark.asyncio
async def test_ask_user_pauses_execution_with_paused_status() -> None:
    """An ASK_USER terminal event resolves to a `paused` ExecutionResult."""
    result = await _collect_result(
        "s1",
        _stream(
            [
                StreamEvent(event_type=EventType.STEP_START, data={"step": 1}),
                StreamEvent(
                    event_type=EventType.ASK_USER,
                    data={"question": "Which file?"},
                ),
            ]
        ),
    )
    assert result.status == ExecutionStatus.PAUSED
    assert result.status != ExecutionStatus.FAILED


@pytest.mark.spec("react-loop.interrupted_returns_paused_not_failed")
@pytest.mark.asyncio
async def test_interrupted_returns_paused_not_failed() -> None:
    """An INTERRUPTED terminal event resolves to `paused`, never `failed`."""
    result = await _collect_result(
        "s1",
        _stream(
            [
                StreamEvent(event_type=EventType.STEP_START, data={"step": 1}),
                StreamEvent(
                    event_type=EventType.INTERRUPTED,
                    data={"reason": "user_cancel", "step": 1},
                ),
            ]
        ),
    )
    assert result.status == ExecutionStatus.PAUSED
    assert result.status != ExecutionStatus.FAILED


# ---------------------------------------------------------------------------
# plan_and_execute steps sequentially
# ---------------------------------------------------------------------------


@pytest.mark.spec("react-loop.plan_and_execute_steps_sequentially")
@pytest.mark.asyncio
async def test_plan_and_execute_steps_sequentially() -> None:
    """PlanAndExecute builds a plan first, then executes its steps in order."""
    state_manager = AsyncMock()
    state_manager.load_state.return_value = {"answers": {}}

    async def step_stream(**_kwargs: Any):
        yield {"type": "token", "content": "step done"}
        yield {"type": "done", "usage": {}}

    provider = MagicMock()
    provider.complete = AsyncMock(
        return_value={"success": True, "content": '["Read the file", "Summarise it"]'}
    )
    provider.complete_stream = MagicMock(side_effect=lambda **kw: step_stream(**kw))

    agent = Agent(
        state_manager=state_manager,
        llm_provider=provider,
        tools=[],
        logger=MagicMock(),
        max_steps=10,
    )

    strategy = PlanAndExecuteStrategy(max_step_iterations=1, max_plan_steps=5)
    events = [e async for e in strategy.execute_stream(agent, "do work", "s1")]

    plan_events = [e for e in events if e.event_type == EventType.PLAN_UPDATED]
    # The plan is created up front …
    assert plan_events[0].data["action"] == "create_plan"
    # … then each step is marked done in plan order.
    done_steps = [
        int(e.data["step"]) for e in plan_events if e.data.get("action") == "mark_done"
    ]
    assert done_steps == [1, 2]

    # The per-step prompts were appended in order.
    step_prompts = [
        m["content"]
        for m in agent.context.messages
        if "Execute step" in str(m.get("content", ""))
    ]
    assert step_prompts[0].startswith("Execute step 1:")
    assert step_prompts[1].startswith("Execute step 2:")
