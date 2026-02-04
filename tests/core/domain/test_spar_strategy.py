"""
Unit Tests for SparStrategy.

Validates:
- Basic execution flow (plan -> act -> reflect -> final)
- Reflection prompt presence
"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from taskforce.core.domain.enums import EventType
from taskforce.core.domain.planning_strategy import SparStrategy
from taskforce.core.interfaces.logging import LoggerProtocol


class MockLogger(LoggerProtocol):
    """Mock logger for testing."""

    def __init__(self) -> None:
        self.logs: list[tuple[str, dict[str, Any]]] = []

    def info(self, event: str, **kwargs: Any) -> None:
        self.logs.append(("info", {"event": event, **kwargs}))

    def warning(self, event: str, **kwargs: Any) -> None:
        self.logs.append(("warning", {"event": event, **kwargs}))

    def error(self, event: str, **kwargs: Any) -> None:
        self.logs.append(("error", {"event": event, **kwargs}))

    def debug(self, event: str, **kwargs: Any) -> None:
        self.logs.append(("debug", {"event": event, **kwargs}))


@pytest.fixture
def mock_agent() -> MagicMock:
    """Create a mock agent with required attributes."""
    agent = MagicMock()
    agent.logger = MockLogger()
    agent._planner = None
    agent.max_steps = 10
    agent.max_parallel_tools = 4
    agent.model_alias = "gpt-4"
    agent.system_prompt = "You are a helpful assistant."
    agent._openai_tools = []
    agent._build_system_prompt = MagicMock(return_value="System prompt")
    agent._build_initial_messages = MagicMock(
        return_value=[{"role": "system", "content": "System prompt"}]
    )
    agent._truncate_output = MagicMock(side_effect=lambda x: x[:100])
    agent.llm_provider = AsyncMock()
    agent.state_manager = AsyncMock()
    agent.state_manager.load_state = AsyncMock(return_value=None)
    agent.state_store = AsyncMock()
    agent.record_heartbeat = AsyncMock()
    return agent


def test_spar_executes_reflection(mock_agent: MagicMock) -> None:
    """Ensure SPAR runs plan, act, reflect, and final response."""
    mock_agent.llm_provider = SimpleNamespace(
        complete=AsyncMock(
            side_effect=[
                {"success": True, "content": '["Step 1"]'},
                {"success": True, "content": "Step done."},
                {"success": True, "content": "Reflection looks good."},
                {"success": True, "content": "Final reflection looks good."},
                {"success": True, "content": "Final answer."},
            ]
        )
    )
    strategy = SparStrategy(
        max_step_iterations=1,
        max_plan_steps=3,
        reflect_every_step=True,
        max_reflection_iterations=1,
    )

    async def run() -> list:
        collected = []
        async for event in strategy.execute_stream(mock_agent, "Test mission", "session-1"):
            collected.append(event)
        return collected

    events = asyncio.run(run())

    assert any(
        event.event_type == EventType.FINAL_ANSWER and event.data.get("content") == "Final answer."
        for event in events
    )
    assert mock_agent.llm_provider.complete.call_count == 5

    reflection_calls = []
    for call in mock_agent.llm_provider.complete.call_args_list:
        messages = call.kwargs.get("messages", [])
        if any("REFLECT" in message.get("content", "") for message in messages):
            reflection_calls.append(call)
    assert reflection_calls, "Expected a reflection prompt in LLM calls."
