"""Unit tests for planning helper utility functions."""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from taskforce.core.domain.enums import EventType
from taskforce.core.domain.models import StreamEvent
from taskforce.core.domain.planning import (
    DEFAULT_PLAN,
    ExecutionInit,
    ResumeContext,
    _initialize_execution_context,
    _is_no_progress_tool_output,
)


def test_detects_no_progress_markers() -> None:
    assert _is_no_progress_tool_output("rg: 0 matches in 10 files")
    assert _is_no_progress_tool_output("No files found")
    assert _is_no_progress_tool_output("tool failed: not found")


def test_ignores_regular_informative_output() -> None:
    assert not _is_no_progress_tool_output("Updated src/taskforce/api/cli/commands/chat.py")
    assert not _is_no_progress_tool_output("Found 4 matches in 2 files")


# ---------------------------------------------------------------------------
# _initialize_execution_context
# ---------------------------------------------------------------------------


def _make_agent(
    *,
    resume: ResumeContext | None = None,
    state: dict[str, Any] | None = None,
    plan_events: list[Any] | None = None,
) -> MagicMock:
    """Build a minimal agent mock for _initialize_execution_context tests."""
    agent = MagicMock()
    agent._base_system_prompt = "base"
    agent._planner = None
    agent.state_manager.load_state = AsyncMock(return_value=state or {})
    agent.skill_manager = None
    agent.load_memory_context = AsyncMock(return_value=None)
    agent.state_store.save = AsyncMock(return_value=None)

    agent.context = MagicMock()
    agent.context.restore = MagicMock()
    agent.context.initialize = MagicMock()
    return agent


@pytest.mark.asyncio
async def test_initialize_execution_context_fresh_no_plan() -> None:
    """Fresh execution without plan generation yields only an ExecutionInit
    carrying DEFAULT_PLAN and no resume."""
    agent = _make_agent(state={})
    logger = MagicMock()

    items = [
        item
        async for item in _initialize_execution_context(
            agent,
            mission="do stuff",
            session_id="sess-1",
            logger=logger,
            generate_plan=False,
        )
    ]

    assert len(items) == 1
    init = items[0]
    assert isinstance(init, ExecutionInit)
    assert init.resume is None
    assert init.plan is DEFAULT_PLAN
    assert init.state == {}
    agent.context.initialize.assert_called_once_with("do stuff", {}, "base")
    agent.context.restore.assert_not_called()


@pytest.mark.asyncio
async def test_initialize_execution_context_resume_path() -> None:
    """When state carries a resume marker, context.restore is called and the
    ExecutionInit echoes the resumed plan/step/phase."""
    resume_messages = [{"role": "user", "content": "old"}]
    state: dict[str, Any] = {
        "pending_question": {"question": "which?", "missing": []},
        "paused_messages": resume_messages,
        "paused_step": 3,
        "paused_plan": ["a", "b", "c"],
        "paused_plan_step_idx": 2,
        "paused_plan_iteration": 1,
        "paused_phase": "reflect",
        "paused_tool_call_id": "call-1",
    }
    agent = _make_agent(state=state)
    logger = MagicMock()

    items = [
        item
        async for item in _initialize_execution_context(
            agent,
            mission="answer text",
            session_id="sess-2",
            logger=logger,
            generate_plan=True,  # ignored on resume path
        )
    ]

    assert len(items) == 1
    init = items[0]
    assert isinstance(init, ExecutionInit)
    assert init.resume is not None
    assert init.resume.step == 3
    assert init.resume.plan == ["a", "b", "c"]
    assert init.resume.phase == "reflect"
    assert init.plan == ["a", "b", "c"]
    agent.context.restore.assert_called_once()
    agent.context.initialize.assert_not_called()


@pytest.mark.asyncio
async def test_initialize_execution_context_fresh_with_plan_gen(monkeypatch: Any) -> None:
    """Plan-generation StreamEvents are yielded live and the final
    ExecutionInit carries the generated plan."""
    agent = _make_agent(state={})
    logger = MagicMock()

    plan_event = StreamEvent(event_type=EventType.PLAN_UPDATED, data={"action": "create_plan"})
    generated_plan = ["step 1", "step 2"]

    async def fake_plan_gen(*args: Any, **kwargs: Any):
        yield generated_plan
        yield plan_event

    import taskforce.core.domain.planning.state as state_module

    monkeypatch.setattr(state_module, "_generate_and_register_plan", fake_plan_gen)

    items = [
        item
        async for item in _initialize_execution_context(
            agent,
            mission="build it",
            session_id="sess-3",
            logger=logger,
            generate_plan=True,
            max_plan_steps=5,
        )
    ]

    # StreamEvent first, then ExecutionInit sentinel
    assert len(items) == 2
    assert items[0] is plan_event
    init = items[1]
    assert isinstance(init, ExecutionInit)
    assert init.resume is None
    assert init.plan == generated_plan
    agent.context.initialize.assert_called_once()
