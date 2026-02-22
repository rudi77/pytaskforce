"""
Unit Tests for SparStrategy.

Validates:
- Basic execution flow (plan -> act -> reflect -> final)
- Reflection prompt presence
"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

from taskforce.core.domain.enums import EventType
from taskforce.core.domain.planning_strategy import SparStrategy

# mock_agent fixture is provided by tests/conftest.py


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
