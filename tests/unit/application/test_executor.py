"""
Unit Tests for AgentExecutor

Tests the application layer executor service with mocked dependencies.
Verifies orchestration logic, progress tracking, error handling, and logging.
"""

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, call

import pytest

from taskforce.application.executor import AgentExecutor, ProgressUpdate
from taskforce.application.factory import AgentFactory
from taskforce.core.domain.models import ExecutionResult


@pytest.mark.asyncio
async def test_execute_mission_basic():
    """Test basic mission execution with mocked factory and agent."""
    # Mock factory and agent
    mock_factory = MagicMock(spec=AgentFactory)
    mock_agent = AsyncMock()
    mock_agent.execute.return_value = ExecutionResult(
        session_id="test-123",
        status="completed",
        final_message="Success",
        execution_history=[],
        todolist_id="todo-456",
    )
    mock_factory.create_agent.return_value = mock_agent

    # Execute mission
    executor = AgentExecutor(factory=mock_factory)
    result = await executor.execute_mission("Test mission", profile="dev")

    # Verify result
    assert result.status == "completed"
    assert result.final_message == "Success"
    assert result.todolist_id == "todo-456"

    # Verify factory and agent were called correctly
    mock_factory.create_agent.assert_called_once_with(profile="dev")
    mock_agent.execute.assert_called_once()

    # Verify execute was called with mission and generated session_id
    call_args = mock_agent.execute.call_args
    assert call_args.kwargs["mission"] == "Test mission"
    assert "session_id" in call_args.kwargs
    assert isinstance(call_args.kwargs["session_id"], str)


@pytest.mark.asyncio
async def test_execute_mission_with_session_id():
    """Test mission execution with provided session ID."""
    mock_factory = MagicMock(spec=AgentFactory)
    mock_agent = AsyncMock()
    mock_agent.execute.return_value = ExecutionResult(
        session_id="custom-session",
        status="completed",
        final_message="Success",
    )
    mock_factory.create_agent.return_value = mock_agent

    executor = AgentExecutor(factory=mock_factory)
    result = await executor.execute_mission(
        "Test mission", profile="dev", session_id="custom-session"
    )

    # Verify custom session ID was used
    assert result.session_id == "custom-session"
    mock_agent.execute.assert_called_once()
    call_args = mock_agent.execute.call_args
    assert call_args.kwargs["session_id"] == "custom-session"


@pytest.mark.asyncio
async def test_execute_mission_with_progress_callback():
    """Test mission execution with progress callback."""
    mock_factory = MagicMock(spec=AgentFactory)
    mock_agent = AsyncMock()
    mock_agent.execute.return_value = ExecutionResult(
        session_id="test-123",
        status="completed",
        final_message="Success",
        execution_history=[
            {
                "type": "thought",
                "step": 1,
                "data": {"rationale": "Analyzing task", "action": {}},
            },
            {
                "type": "observation",
                "step": 1,
                "data": {"success": True, "result": "Done"},
            },
        ],
    )
    mock_factory.create_agent.return_value = mock_agent

    # Track progress updates
    updates = []

    def progress_callback(update: ProgressUpdate):
        updates.append(update)

    executor = AgentExecutor(factory=mock_factory)
    result = await executor.execute_mission(
        "Test mission", progress_callback=progress_callback
    )

    # Verify result
    assert result.status == "completed"

    # Verify progress updates were sent
    assert len(updates) >= 1
    assert any(u.event_type == "complete" for u in updates)

    # Verify update structure
    complete_update = next(u for u in updates if u.event_type == "complete")
    assert isinstance(complete_update.timestamp, datetime)
    assert complete_update.message == "Success"
    assert complete_update.details["status"] == "completed"


@pytest.mark.asyncio
async def test_execute_mission_error_handling():
    """Test error handling during mission execution."""
    mock_factory = MagicMock(spec=AgentFactory)
    mock_agent = AsyncMock()
    mock_agent.execute.side_effect = RuntimeError("LLM failure")
    mock_factory.create_agent.return_value = mock_agent

    executor = AgentExecutor(factory=mock_factory)

    # Verify exception is raised
    with pytest.raises(RuntimeError, match="LLM failure"):
        await executor.execute_mission("Test mission")

    # Verify agent was called
    mock_agent.execute.assert_called_once()


@pytest.mark.asyncio
async def test_execute_mission_different_profiles():
    """Test mission execution with different profiles."""
    mock_factory = MagicMock(spec=AgentFactory)
    mock_agent = AsyncMock()
    mock_agent.execute.return_value = ExecutionResult(
        session_id="test-123", status="completed", final_message="Success"
    )
    mock_factory.create_agent.return_value = mock_agent

    executor = AgentExecutor(factory=mock_factory)

    # Test dev profile
    await executor.execute_mission("Test mission", profile="dev")
    mock_factory.create_agent.assert_called_with(profile="dev")

    # Test staging profile
    await executor.execute_mission("Test mission", profile="staging")
    mock_factory.create_agent.assert_called_with(profile="staging")

    # Test prod profile
    await executor.execute_mission("Test mission", profile="prod")
    mock_factory.create_agent.assert_called_with(profile="prod")


@pytest.mark.asyncio
async def test_execute_mission_streaming_basic():
    """Test streaming execution yields progress updates."""
    mock_factory = MagicMock(spec=AgentFactory)
    mock_agent = AsyncMock()
    mock_agent.execute.return_value = ExecutionResult(
        session_id="test-123",
        status="completed",
        final_message="Success",
        execution_history=[
            {
                "type": "thought",
                "step": 1,
                "data": {"rationale": "Analyzing task", "action": {}},
            },
            {
                "type": "observation",
                "step": 1,
                "data": {"success": True, "result": "Done"},
            },
        ],
    )
    mock_factory.create_agent.return_value = mock_agent

    executor = AgentExecutor(factory=mock_factory)

    # Collect streaming updates
    updates = []
    async for update in executor.execute_mission_streaming("Test mission"):
        updates.append(update)

    # Verify updates were yielded
    assert len(updates) >= 3  # started + thought + observation + complete

    # Verify started event
    assert updates[0].event_type == "started"
    assert "Starting mission" in updates[0].message

    # Verify thought event
    thought_updates = [u for u in updates if u.event_type == "thought"]
    assert len(thought_updates) >= 1

    # Verify observation event
    observation_updates = [u for u in updates if u.event_type == "observation"]
    assert len(observation_updates) >= 1

    # Verify complete event
    complete_updates = [u for u in updates if u.event_type == "complete"]
    assert len(complete_updates) == 1
    assert complete_updates[0].message == "Success"


@pytest.mark.asyncio
async def test_execute_mission_streaming_with_session_id():
    """Test streaming execution with provided session ID."""
    mock_factory = MagicMock(spec=AgentFactory)
    mock_agent = AsyncMock()
    mock_agent.execute.return_value = ExecutionResult(
        session_id="custom-session",
        status="completed",
        final_message="Success",
        execution_history=[],
    )
    mock_factory.create_agent.return_value = mock_agent

    executor = AgentExecutor(factory=mock_factory)

    # Collect updates
    updates = []
    async for update in executor.execute_mission_streaming(
        "Test mission", session_id="custom-session"
    ):
        updates.append(update)

    # Verify session ID in started event
    assert updates[0].details["session_id"] == "custom-session"

    # Verify agent was called with custom session ID
    call_args = mock_agent.execute.call_args
    assert call_args.kwargs["session_id"] == "custom-session"


@pytest.mark.asyncio
async def test_execute_mission_streaming_error_handling():
    """Test streaming execution error handling."""
    mock_factory = MagicMock(spec=AgentFactory)
    mock_agent = AsyncMock()
    mock_agent.execute.side_effect = RuntimeError("Execution failed")
    mock_factory.create_agent.return_value = mock_agent

    executor = AgentExecutor(factory=mock_factory)

    # Collect updates until error
    updates = []
    with pytest.raises(RuntimeError, match="Execution failed"):
        async for update in executor.execute_mission_streaming("Test mission"):
            updates.append(update)

    # Verify started event was yielded
    assert len(updates) >= 1
    assert updates[0].event_type == "started"

    # Verify error event was yielded
    error_updates = [u for u in updates if u.event_type == "error"]
    assert len(error_updates) == 1
    assert "Execution failed" in error_updates[0].message


@pytest.mark.asyncio
async def test_execute_mission_paused_status():
    """Test mission execution that pauses for user input."""
    mock_factory = MagicMock(spec=AgentFactory)
    mock_agent = AsyncMock()
    mock_agent.execute.return_value = ExecutionResult(
        session_id="test-123",
        status="paused",
        final_message="Waiting for user input",
        execution_history=[],
    )
    mock_factory.create_agent.return_value = mock_agent

    executor = AgentExecutor(factory=mock_factory)
    result = await executor.execute_mission("Test mission")

    # Verify paused status
    assert result.status == "paused"
    assert "user input" in result.final_message.lower()


@pytest.mark.asyncio
async def test_execute_mission_failed_status():
    """Test mission execution that fails."""
    mock_factory = MagicMock(spec=AgentFactory)
    mock_agent = AsyncMock()
    mock_agent.execute.return_value = ExecutionResult(
        session_id="test-123",
        status="failed",
        final_message="Exceeded maximum iterations",
        execution_history=[],
    )
    mock_factory.create_agent.return_value = mock_agent

    executor = AgentExecutor(factory=mock_factory)
    result = await executor.execute_mission("Test mission")

    # Verify failed status
    assert result.status == "failed"
    assert result.final_message == "Exceeded maximum iterations"


@pytest.mark.asyncio
async def test_generate_session_id_uniqueness():
    """Test that generated session IDs are unique."""
    executor = AgentExecutor()

    # Generate multiple session IDs
    session_ids = [executor._generate_session_id() for _ in range(100)]

    # Verify all are unique
    assert len(session_ids) == len(set(session_ids))

    # Verify format (UUID)
    for session_id in session_ids:
        assert isinstance(session_id, str)
        assert len(session_id) == 36  # UUID format: 8-4-4-4-12
        assert session_id.count("-") == 4


@pytest.mark.asyncio
async def test_executor_uses_default_factory():
    """Test that executor creates default factory if none provided."""
    executor = AgentExecutor()

    # Verify factory was created
    assert executor.factory is not None
    assert isinstance(executor.factory, AgentFactory)


@pytest.mark.asyncio
async def test_progress_update_structure():
    """Test ProgressUpdate dataclass structure."""
    update = ProgressUpdate(
        timestamp=datetime.now(),
        event_type="thought",
        message="Analyzing task",
        details={"step": 1, "rationale": "Need to read file"},
    )

    # Verify attributes
    assert isinstance(update.timestamp, datetime)
    assert update.event_type == "thought"
    assert update.message == "Analyzing task"
    assert update.details["step"] == 1
    assert update.details["rationale"] == "Need to read file"

