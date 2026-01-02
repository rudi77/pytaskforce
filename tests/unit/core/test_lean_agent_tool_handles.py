"""
Unit tests for LeanAgent tool result handle integration.

Tests verify that LeanAgent correctly uses ToolResultStore for large
tool outputs, keeping message history small while maintaining debuggability.
"""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from taskforce.core.domain.lean_agent import LeanAgent
from taskforce.core.interfaces.tool_result_store import ToolResultHandle
from taskforce.infrastructure.cache.tool_result_store import FileToolResultStore


@pytest.fixture
def mock_state_manager():
    """Mock state manager."""
    manager = AsyncMock()
    manager.load_state.return_value = {}
    manager.save_state.return_value = True
    return manager


@pytest.fixture
def mock_llm_provider():
    """Mock LLM provider."""
    provider = AsyncMock()
    return provider


@pytest.fixture
def mock_tool():
    """Mock tool that returns large output."""
    tool = MagicMock()
    tool.name = "large_output_tool"
    tool.description = "A tool that returns large output"
    tool.parameters_schema = {
        "type": "object",
        "properties": {},
    }

    # Return large output (>5000 chars for handle, >20000 for truncation)
    large_output = "x" * 25000  # Exceeds default truncation limit
    tool.execute = AsyncMock(
        return_value={
            "success": True,
            "output": large_output,
        }
    )
    return tool


@pytest.fixture
async def tool_result_store(tmp_path):
    """Create a temporary tool result store."""
    store = FileToolResultStore(store_dir=tmp_path / "tool_results")
    return store


@pytest.mark.asyncio
async def test_agent_uses_handle_for_large_result(
    mock_state_manager,
    mock_llm_provider,
    mock_tool,
    tool_result_store,
):
    """Test that agent stores large tool results as handles."""
    # Arrange
    agent = LeanAgent(
        state_manager=mock_state_manager,
        llm_provider=mock_llm_provider,
        tools=[mock_tool],
        tool_result_store=tool_result_store,
    )

    # Mock LLM to call tool once, then return final answer
    mock_llm_provider.complete.side_effect = [
        # First call - LLM wants to use tool
        {
            "success": True,
            "tool_calls": [
                {
                    "id": "call_123",
                    "type": "function",
                    "function": {
                        "name": "large_output_tool",
                        "arguments": "{}",
                    },
                }
            ],
        },
        # Second call - LLM returns final answer
        {
            "success": True,
            "content": "Task completed successfully",
        },
    ]

    # Act
    result = await agent.execute(
        mission="Test mission",
        session_id="test_session_handle",
    )

    # Assert - execution completed
    assert result.status == "completed"
    assert result.final_message == "Task completed successfully"

    # Assert - tool was called
    mock_tool.execute.assert_called_once()

    # Assert - LLM was called twice
    assert mock_llm_provider.complete.call_count == 2

    # Assert - second LLM call received handle+preview, not full output
    second_call_args = mock_llm_provider.complete.call_args_list[1]
    messages = second_call_args[1]["messages"]

    # Find the tool message
    tool_messages = [m for m in messages if m.get("role") == "tool"]
    assert len(tool_messages) == 1

    tool_message = tool_messages[0]
    tool_content = json.loads(tool_message["content"])

    # Assert - message contains handle and preview, not raw output
    assert "handle" in tool_content
    assert "preview_text" in tool_content
    assert "truncated" in tool_content

    # Assert - handle has expected structure
    handle_data = tool_content["handle"]
    assert "id" in handle_data
    assert "tool" in handle_data
    assert handle_data["tool"] == "large_output_tool"
    assert "size_chars" in handle_data
    assert handle_data["size_chars"] > 5000  # Large result

    # Assert - preview is short
    preview_text = tool_content["preview_text"]
    assert len(preview_text) <= 500  # Preview cap

    # Assert - full result can be fetched from store
    handle = ToolResultHandle.from_dict(handle_data)
    stored_result = await tool_result_store.fetch(handle)
    assert stored_result is not None
    assert len(stored_result["output"]) == 25000  # Full output preserved


@pytest.mark.asyncio
async def test_agent_uses_standard_message_for_small_result(
    mock_state_manager,
    mock_llm_provider,
    tool_result_store,
):
    """Test that agent uses standard messages for small tool results."""
    # Arrange - tool with small output
    small_tool = MagicMock()
    small_tool.name = "small_output_tool"
    small_tool.description = "A tool with small output"
    small_tool.parameters_schema = {"type": "object", "properties": {}}
    small_tool.execute = AsyncMock(
        return_value={
            "success": True,
            "output": "Small output",  # < 5000 chars
        }
    )

    agent = LeanAgent(
        state_manager=mock_state_manager,
        llm_provider=mock_llm_provider,
        tools=[small_tool],
        tool_result_store=tool_result_store,
    )

    # Mock LLM
    mock_llm_provider.complete.side_effect = [
        {
            "success": True,
            "tool_calls": [
                {
                    "id": "call_456",
                    "type": "function",
                    "function": {
                        "name": "small_output_tool",
                        "arguments": "{}",
                    },
                }
            ],
        },
        {
            "success": True,
            "content": "Done",
        },
    ]

    # Act
    result = await agent.execute(
        mission="Test mission",
        session_id="test_session_small",
    )

    # Assert
    assert result.status == "completed"

    # Assert - second LLM call received standard message (not handle)
    second_call_args = mock_llm_provider.complete.call_args_list[1]
    messages = second_call_args[1]["messages"]

    tool_messages = [m for m in messages if m.get("role") == "tool"]
    assert len(tool_messages) == 1

    tool_message = tool_messages[0]
    tool_content = json.loads(tool_message["content"])

    # Assert - standard format (success + output), not handle format
    assert "success" in tool_content
    assert "output" in tool_content
    assert "handle" not in tool_content  # No handle for small result


@pytest.mark.asyncio
async def test_agent_without_store_uses_standard_messages(
    mock_state_manager,
    mock_llm_provider,
    mock_tool,
):
    """Test that agent without store uses standard messages even for large results."""
    # Arrange - agent without tool_result_store
    agent = LeanAgent(
        state_manager=mock_state_manager,
        llm_provider=mock_llm_provider,
        tools=[mock_tool],
        tool_result_store=None,  # No store
    )

    # Mock LLM
    mock_llm_provider.complete.side_effect = [
        {
            "success": True,
            "tool_calls": [
                {
                    "id": "call_789",
                    "type": "function",
                    "function": {
                        "name": "large_output_tool",
                        "arguments": "{}",
                    },
                }
            ],
        },
        {
            "success": True,
            "content": "Done",
        },
    ]

    # Act
    result = await agent.execute(
        mission="Test mission",
        session_id="test_session_no_store",
    )

    # Assert
    assert result.status == "completed"

    # Assert - standard message format used (with truncation)
    second_call_args = mock_llm_provider.complete.call_args_list[1]
    messages = second_call_args[1]["messages"]

    tool_messages = [m for m in messages if m.get("role") == "tool"]
    assert len(tool_messages) == 1

    tool_message = tool_messages[0]
    tool_content = json.loads(tool_message["content"])

    # Assert - standard format with truncation
    assert "success" in tool_content
    assert "output" in tool_content
    assert "handle" not in tool_content

    # Output should be truncated (default 20000 chars)
    assert "TRUNCATED" in tool_content["output"]


@pytest.mark.asyncio
async def test_handle_includes_metadata(
    mock_state_manager,
    mock_llm_provider,
    mock_tool,
    tool_result_store,
):
    """Test that stored handles include metadata (session_id, step, success)."""
    # Arrange
    agent = LeanAgent(
        state_manager=mock_state_manager,
        llm_provider=mock_llm_provider,
        tools=[mock_tool],
        tool_result_store=tool_result_store,
    )

    mock_llm_provider.complete.side_effect = [
        {
            "success": True,
            "tool_calls": [
                {
                    "id": "call_meta",
                    "type": "function",
                    "function": {
                        "name": "large_output_tool",
                        "arguments": "{}",
                    },
                }
            ],
        },
        {
            "success": True,
            "content": "Done",
        },
    ]

    # Act
    await agent.execute(
        mission="Test mission",
        session_id="test_session_metadata",
    )

    # Assert - get stats to find stored result
    stats = await tool_result_store.get_stats()
    assert stats["total_results"] == 1

    # Find the handle file and verify metadata
    import json
    from pathlib import Path

    handles_dir = Path(tool_result_store.handles_dir)
    handle_files = list(handles_dir.glob("*.json"))
    assert len(handle_files) == 1

    with open(handle_files[0], "r") as f:
        handle_data = json.load(f)

    # Assert metadata
    assert "metadata" in handle_data
    metadata = handle_data["metadata"]
    assert metadata["session_id"] == "test_session_metadata"
    assert "step" in metadata
    assert metadata["step"] == 1  # First step
    assert metadata["success"] is True


@pytest.mark.asyncio
async def test_streaming_uses_handles(
    mock_state_manager,
    mock_llm_provider,
    mock_tool,
    tool_result_store,
):
    """Test that streaming execution also uses handles for large results."""
    # Arrange
    agent = LeanAgent(
        state_manager=mock_state_manager,
        llm_provider=mock_llm_provider,
        tools=[mock_tool],
        tool_result_store=tool_result_store,
    )

    # Mock streaming LLM
    async def mock_stream(*args, **kwargs):
        # Yield tool call chunks
        yield {"type": "tool_call_start", "id": "call_stream", "name": "large_output_tool", "index": 0}
        yield {"type": "tool_call_delta", "index": 0, "arguments_delta": "{}"}
        yield {"type": "tool_call_end", "index": 0, "arguments": "{}"}

    mock_llm_provider.complete_stream = mock_stream

    # Second call for final answer
    mock_llm_provider.complete.return_value = {
        "success": True,
        "content": "Done",
    }

    # Act
    events = []
    async for event in agent.execute_stream(
        mission="Test mission",
        session_id="test_session_stream",
    ):
        events.append(event)

    # Assert - events emitted
    assert len(events) > 0

    # Assert - tool result was stored (check store stats)
    stats = await tool_result_store.get_stats()
    assert stats["total_results"] >= 1  # At least one result stored

