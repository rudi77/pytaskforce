"""Tests for AgentExecutor.interrupt() and the active-agents registry.

Covers:
- interrupt() returns False when no session is running.
- interrupt() signals the registered agent and returns True.
- has_active_session reflects registry state.
- The registry is populated during execute_mission_streaming and cleared
  in the finally block.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from taskforce.application.executor import AgentExecutor
from taskforce.application.factory import AgentFactory
from taskforce.core.domain.enums import EventType
from taskforce.core.domain.models import StreamEvent


class TestInterruptMethod:
    def test_interrupt_returns_false_for_unknown_session(self) -> None:
        executor = AgentExecutor(factory=MagicMock(spec=AgentFactory))
        assert executor.interrupt("nonexistent-session") is False
        assert executor.has_active_session("nonexistent-session") is False

    def test_interrupt_signals_active_agent(self) -> None:
        executor = AgentExecutor(factory=MagicMock(spec=AgentFactory))
        agent = MagicMock()
        agent.request_interrupt = MagicMock()

        executor._active_agents["sess-1"] = agent

        assert executor.has_active_session("sess-1") is True
        assert executor.interrupt("sess-1") is True
        agent.request_interrupt.assert_called_once()


class TestRegistryLifecycle:
    @pytest.mark.asyncio
    async def test_registry_populated_and_cleared(self) -> None:
        """Streaming run should register the agent and remove it on exit."""
        mock_factory = MagicMock(spec=AgentFactory)
        executor = AgentExecutor(factory=mock_factory)

        # Observe the registry state from inside the agent's stream.
        observed: dict[str, Any] = {"inside": False}

        async def fake_stream(mission: str, session_id: str):
            # The executor must have registered us before yielding the
            # first event.
            observed["inside"] = session_id in executor._active_agents
            yield StreamEvent(
                event_type=EventType.COMPLETE,
                data={"status": "completed", "final_message": "ok", "session_id": session_id},
            )

        mock_agent = MagicMock()
        mock_agent.execute_stream = fake_stream
        mock_agent.close = AsyncMock()
        mock_agent.clear_interrupt = MagicMock()

        # Bypass the internal AgentCreationPipeline by passing ``agent``.
        session_id = "registry-test"
        async for _ in executor.execute_mission_streaming(
            mission="noop", session_id=session_id, agent=mock_agent
        ):
            pass

        assert observed["inside"] is True
        assert session_id not in executor._active_agents
        mock_agent.clear_interrupt.assert_called()

    @pytest.mark.asyncio
    async def test_interrupt_during_streaming_is_visible(self) -> None:
        """While a mission is running, interrupt(session_id) finds the agent."""
        mock_factory = MagicMock(spec=AgentFactory)
        executor = AgentExecutor(factory=mock_factory)

        signalled: dict[str, Any] = {"called": False}

        async def fake_stream(mission: str, session_id: str):
            # Simulate the CLI/API hitting POST /cancel mid-stream.
            assert executor.interrupt(session_id) is True
            signalled["called"] = True
            yield StreamEvent(
                event_type=EventType.INTERRUPTED,
                data={"reason": "user_requested", "step": 0, "timestamp": "t"},
            )
            yield StreamEvent(
                event_type=EventType.COMPLETE,
                data={
                    "status": "paused",
                    "final_message": "Execution paused by user.",
                    "session_id": session_id,
                },
            )

        mock_agent = MagicMock()
        mock_agent.execute_stream = fake_stream
        mock_agent.close = AsyncMock()
        mock_agent.clear_interrupt = MagicMock()
        mock_agent.request_interrupt = MagicMock()

        session_id = "cancel-me"
        events = []
        async for update in executor.execute_mission_streaming(
            mission="long task", session_id=session_id, agent=mock_agent
        ):
            events.append(update)

        assert signalled["called"] is True
        mock_agent.request_interrupt.assert_called_once()
        # Final COMPLETE event reports paused status.
        complete = next(u for u in events if u.event_type == EventType.COMPLETE.value)
        assert complete.details["status"] == "paused"
