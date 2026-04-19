"""Tests for cooperative interrupt handling in the ReAct loop.

Covers:
- Loop exits at the next iteration boundary when interrupt is requested.
- ``INTERRUPTED`` event is emitted with step + reason metadata.
- State is persisted with ``pending_interrupt`` + ``paused_messages`` markers.
- Interrupt flag is cleared after handling.
- ``_resume_from_pause`` restores messages and appends the new user turn.
"""

from __future__ import annotations

import asyncio
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from taskforce.core.domain.enums import EventType
from taskforce.core.domain.models import StreamEvent
from taskforce.core.domain.planning.interrupt import _handle_interrupt
from taskforce.core.domain.planning.state import _resume_from_pause
from taskforce.core.domain.planning import _react_loop


def _make_logger() -> MagicMock:
    logger = MagicMock()
    logger.info = MagicMock()
    logger.warning = MagicMock()
    logger.debug = MagicMock()
    logger.error = MagicMock()
    return logger


def _make_agent(interrupted: bool = False) -> MagicMock:
    """Mock agent with just enough surface area for _react_loop + interrupt."""
    agent = MagicMock()
    agent.max_steps = 10
    agent.max_parallel_tools = 1
    agent._openai_tools = []
    agent._planner = None
    agent.planner = None
    agent.tools = {}
    agent.skill_manager = None
    agent.state_manager = AsyncMock()
    agent.state_store = AsyncMock()
    agent.record_heartbeat = AsyncMock()
    agent.load_memory_context = AsyncMock()
    agent._build_system_prompt = MagicMock(return_value="system prompt")
    agent._truncate_output = MagicMock(side_effect=lambda x: x)

    _msgs: list[dict[str, Any]] = []
    context = MagicMock()
    context.messages = _msgs
    context.append_message = MagicMock(side_effect=lambda m: _msgs.append(m))
    context.prepare_for_llm = AsyncMock()
    agent.context = context

    # Interrupt surface — use a real asyncio.Event so the defensive
    # isinstance check in react_loop matches.
    event = asyncio.Event()
    if interrupted:
        event.set()
    agent._interrupt_event = event
    agent.is_interrupt_requested = MagicMock(side_effect=event.is_set)
    agent.clear_interrupt = MagicMock(side_effect=event.clear)

    return agent


class TestReactLoopInterrupt:
    @pytest.mark.asyncio
    async def test_loop_exits_when_interrupt_requested_before_first_step(self) -> None:
        """Interrupt flag set before the loop starts → immediate pause + INTERRUPTED event."""
        agent = _make_agent(interrupted=True)
        logger = _make_logger()

        messages: list[dict[str, Any]] = [
            {"role": "system", "content": "system prompt"},
            {"role": "user", "content": "long task"},
        ]
        agent.context.messages.extend(messages)
        state: dict[str, Any] = {}

        events: list[StreamEvent] = []
        async for evt in _react_loop(
            agent, "long task", "sess-interrupt", messages, state, 0, logger
        ):
            events.append(evt)

        # Exactly one INTERRUPTED event should be emitted, no LLM call happened.
        interrupt_events = [e for e in events if e.event_type == EventType.INTERRUPTED]
        assert len(interrupt_events) == 1
        assert interrupt_events[0].data["reason"] == "user_requested"
        assert interrupt_events[0].data["step"] == 0

        # State should be persisted by _handle_interrupt.
        assert "pending_interrupt" in state
        assert "paused_messages" in state
        assert state["paused_step"] == 0
        agent.state_store.save.assert_awaited()

        # Flag must be cleared so a later resume isn't immediately aborted.
        assert agent.is_interrupt_requested() is False
        agent.clear_interrupt.assert_called()


class TestHandleInterrupt:
    @pytest.mark.asyncio
    async def test_persists_full_state_snapshot(self) -> None:
        agent = _make_agent()
        # Seed the context with some prior messages to verify they're snapshotted.
        agent.context.messages.extend(
            [
                {"role": "system", "content": "sp"},
                {"role": "user", "content": "do X"},
                {"role": "assistant", "content": "thinking..."},
            ]
        )
        logger = _make_logger()
        state: dict[str, Any] = {}

        events: list[StreamEvent] = []
        async for e in _handle_interrupt(
            agent,
            session_id="s1",
            state=state,
            logger=logger,
            step=7,
            plan=["step 1", "step 2"],
            plan_step_idx=2,
            plan_iteration=1,
            paused_phase="act",
        ):
            events.append(e)

        assert len(events) == 1
        assert events[0].event_type == EventType.INTERRUPTED
        assert state["paused_step"] == 7
        assert state["paused_plan"] == ["step 1", "step 2"]
        assert state["paused_plan_step_idx"] == 2
        assert state["paused_plan_iteration"] == 1
        assert state["paused_phase"] == "act"
        assert state["pending_interrupt"]["reason"] == "user_requested"
        # Messages must be an independent copy (not the live list).
        assert state["paused_messages"] == agent.context.messages
        assert state["paused_messages"] is not agent.context.messages
        agent.state_store.save.assert_awaited_once()


class TestResumeFromPauseInterrupt:
    def test_interrupt_resume_restores_messages_and_appends_new_turn(self) -> None:
        state: dict[str, Any] = {
            "pending_interrupt": {"reason": "user_requested", "timestamp": "t"},
            "paused_messages": [
                {"role": "system", "content": "sp"},
                {"role": "user", "content": "original task"},
                {"role": "assistant", "content": "partial work"},
            ],
            "paused_step": 3,
            "paused_plan": ["a", "b", "c"],
            "paused_plan_step_idx": 2,
            "paused_plan_iteration": 1,
            "paused_phase": "react",
        }
        logger = _make_logger()

        resume = _resume_from_pause(state, "please continue", logger, "s1")

        assert resume is not None
        assert resume.step == 3
        assert resume.plan == ["a", "b", "c"]
        assert resume.plan_step_idx == 2
        # New user turn appended.
        assert resume.messages[-1] == {"role": "user", "content": "please continue"}
        # All pause markers cleared from state.
        for key in (
            "pending_interrupt",
            "paused_messages",
            "paused_step",
            "paused_plan",
            "paused_plan_step_idx",
            "paused_plan_iteration",
            "paused_phase",
        ):
            assert key not in state

    def test_ask_user_resume_still_works(self) -> None:
        """Regression: existing ask_user resume path must remain unchanged."""
        state: dict[str, Any] = {
            "pending_question": {"question": "Which file?", "missing": ["path"]},
            "paused_messages": [{"role": "user", "content": "read file"}],
            "paused_tool_call_id": "tc_1",
            "paused_step": 1,
            "paused_plan": ["read", "summarise"],
            "paused_plan_step_idx": 1,
            "paused_plan_iteration": 1,
            "paused_phase": "act",
        }
        logger = _make_logger()

        resume = _resume_from_pause(state, "README.md", logger, "s1")
        assert resume is not None
        # Synthetic tool message was appended for the LLM.
        last = resume.messages[-1]
        assert last["role"] == "tool"
        assert last["tool_call_id"] == "tc_1"
        assert "README.md" in last["content"]
        assert "pending_question" not in state

    def test_returns_none_when_nothing_to_resume(self) -> None:
        state: dict[str, Any] = {}
        logger = _make_logger()
        assert _resume_from_pause(state, "anything", logger, "s1") is None


class TestAgentInterruptFlag:
    """LeanAgent.request_interrupt/clear_interrupt behaviour."""

    @pytest.mark.asyncio
    async def test_request_and_clear_flag(self) -> None:
        # Import lazily so the module-level Agent alias doesn't pull heavy
        # deps at test collection.
        from taskforce.core.domain.lean_agent import Agent

        # Build a minimal Agent via the explicit constructor.  Only the
        # interrupt-flag surface is exercised here.
        agent = Agent.__new__(Agent)
        agent._interrupt_event = None  # type: ignore[attr-defined]

        assert agent.is_interrupt_requested() is False
        agent.request_interrupt()
        assert agent.is_interrupt_requested() is True
        agent.clear_interrupt()
        assert agent.is_interrupt_requested() is False

    @pytest.mark.asyncio
    async def test_flag_is_asyncio_event(self) -> None:
        from taskforce.core.domain.lean_agent import Agent

        agent = Agent.__new__(Agent)
        agent._interrupt_event = None  # type: ignore[attr-defined]

        # Calling into the lazy getter must return a real asyncio.Event.
        agent.request_interrupt()
        assert isinstance(agent._interrupt_event, asyncio.Event)
