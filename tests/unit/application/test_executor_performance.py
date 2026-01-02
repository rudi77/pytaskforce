"""
Performance Tests for AgentExecutor

Verifies that the executor layer adds minimal overhead (<50ms) to mission execution.
"""

import asyncio
import time
from unittest.mock import AsyncMock, MagicMock

import pytest

from taskforce.application.executor import AgentExecutor
from taskforce.application.factory import AgentFactory
from taskforce.core.domain.models import ExecutionResult


@pytest.mark.asyncio
async def test_executor_overhead_under_50ms():
    """Test that executor overhead is under 50ms per mission."""
    # Mock factory and agent
    mock_factory = MagicMock(spec=AgentFactory)
    mock_agent = AsyncMock()

    # Agent execution takes 100ms (simulated)
    async def mock_execute(*args, **kwargs):
        await asyncio.sleep(0.1)  # 100ms
        return ExecutionResult(
            session_id="test-123",
            status="completed",
            final_message="Success",
            execution_history=[],
        )

    mock_agent.execute = mock_execute
    mock_factory.create_agent.return_value = mock_agent

    executor = AgentExecutor(factory=mock_factory)

    # Measure total execution time
    start = time.perf_counter()
    result = await executor.execute_mission("Test mission", profile="dev")
    end = time.perf_counter()

    total_time_ms = (end - start) * 1000

    # Verify result
    assert result.status == "completed"

    # Verify overhead is under 50ms
    # Total time should be ~100ms (agent) + overhead
    # Overhead = total - agent_time
    overhead_ms = total_time_ms - 100

    assert (
        overhead_ms < 50
    ), f"Executor overhead {overhead_ms:.2f}ms exceeds 50ms threshold"


@pytest.mark.asyncio
async def test_executor_overhead_minimal():
    """Test that executor adds minimal overhead with instant agent execution."""
    # Mock factory and agent with instant execution
    mock_factory = MagicMock(spec=AgentFactory)
    mock_agent = AsyncMock()
    mock_agent.execute.return_value = ExecutionResult(
        session_id="test-123",
        status="completed",
        final_message="Success",
        execution_history=[],
    )
    mock_factory.create_agent.return_value = mock_agent

    executor = AgentExecutor(factory=mock_factory)

    # Measure execution time
    start = time.perf_counter()
    result = await executor.execute_mission("Test mission", profile="dev")
    end = time.perf_counter()

    total_time_ms = (end - start) * 1000

    # Verify result
    assert result.status == "completed"

    # With instant agent execution, total time is pure overhead
    # Should be well under 50ms (typically <10ms)
    assert (
        total_time_ms < 50
    ), f"Executor overhead {total_time_ms:.2f}ms exceeds 50ms threshold"


@pytest.mark.asyncio
async def test_executor_streaming_overhead():
    """Test that streaming execution has minimal overhead."""
    # Mock factory and agent
    mock_factory = MagicMock(spec=AgentFactory)
    mock_agent = AsyncMock()
    mock_agent.execute.return_value = ExecutionResult(
        session_id="test-123",
        status="completed",
        final_message="Success",
        execution_history=[
            {"type": "thought", "step": 1, "data": {"rationale": "Test"}},
            {"type": "observation", "step": 1, "data": {"success": True}},
        ],
    )
    mock_factory.create_agent.return_value = mock_agent

    executor = AgentExecutor(factory=mock_factory)

    # Measure streaming execution time
    start = time.perf_counter()
    updates = []
    async for update in executor.execute_mission_streaming("Test mission"):
        updates.append(update)
    end = time.perf_counter()

    total_time_ms = (end - start) * 1000

    # Verify updates were yielded
    assert len(updates) >= 3  # started + thought + observation + complete

    # Verify overhead is under 50ms
    assert (
        total_time_ms < 50
    ), f"Streaming overhead {total_time_ms:.2f}ms exceeds 50ms threshold"

