"""
Integration test for large tool output handling.

This test verifies that the complete system (LeanAgent + ToolResultStore)
correctly handles very large tool outputs without exploding message history.

Test Scenario:
1. Agent executes a tool that returns a very large output (>50KB)
2. Verify that message history stays small (handle+preview only)
3. Verify that full result is retrievable from store
4. Verify that agent can complete the mission successfully
"""

import tempfile
from pathlib import Path

import pytest

from taskforce.core.domain.lean_agent import LeanAgent
from taskforce.infrastructure.cache.tool_result_store import FileToolResultStore
from taskforce.infrastructure.llm.openai_service import OpenAIService
from taskforce.infrastructure.persistence.file_state import FileStateManager
from taskforce.infrastructure.tools.native.python_tool import PythonTool


@pytest.fixture
async def integration_setup(tmp_path):
    """Set up complete agent with real components."""
    # Create state manager
    state_manager = FileStateManager(work_dir=str(tmp_path))

    # Create tool result store
    store_dir = tmp_path / "tool_results"
    tool_result_store = FileToolResultStore(store_dir=store_dir)

    # Create LLM provider (mock for integration test)
    from unittest.mock import AsyncMock

    llm_provider = AsyncMock()

    # Create Python tool (can generate large outputs)
    python_tool = PythonTool()

    return {
        "state_manager": state_manager,
        "tool_result_store": tool_result_store,
        "llm_provider": llm_provider,
        "python_tool": python_tool,
        "tmp_path": tmp_path,
    }


@pytest.mark.asyncio
async def test_large_tool_output_stays_small_in_messages(integration_setup):
    """
    Integration test: Large tool output is stored as handle, keeping messages small.

    This is the key "stop the bleeding" test case from the story.
    """
    # Arrange
    agent = LeanAgent(
        state_manager=integration_setup["state_manager"],
        llm_provider=integration_setup["llm_provider"],
        tools=[integration_setup["python_tool"]],
        tool_result_store=integration_setup["tool_result_store"],
    )

    # Mock LLM to execute Python tool that generates large output
    import json as json_module

    large_code = "result = 'x' * 50000\nresult"

    integration_setup["llm_provider"].complete.side_effect = [
        # First call - LLM wants to execute Python code
        {
            "success": True,
            "tool_calls": [
                {
                    "id": "call_large_py",
                    "type": "function",
                    "function": {
                        "name": "python",
                        "arguments": json_module.dumps({"code": large_code}),
                    },
                }
            ],
        },
        # Second call - LLM returns final answer
        {
            "success": True,
            "content": "Generated large output successfully",
        },
    ]

    # Act
    result = await agent.execute(
        mission="Generate a large string",
        session_id="integration_large_output",
    )

    # Assert - execution completed
    assert result.status == "completed"
    assert "large output" in result.final_message.lower()

    # Assert - second LLM call received small message
    second_call_args = integration_setup["llm_provider"].complete.call_args_list[1]
    messages = second_call_args[1]["messages"]

    # Calculate total message size
    import json

    total_message_chars = sum(
        len(json.dumps(msg, ensure_ascii=False)) for msg in messages
    )

    # Assert - total message size is reasonable (not 50KB+)
    # With handle+preview, should be < 10KB even with large tool output
    assert total_message_chars < 10000, (
        f"Message history too large: {total_message_chars} chars. "
        "Handle-based storage should keep it small."
    )

    # Assert - tool message contains handle, not raw output
    tool_messages = [m for m in messages if m.get("role") == "tool"]
    assert len(tool_messages) == 1

    tool_message = tool_messages[0]
    tool_content = json.loads(tool_message["content"])

    # Verify handle structure
    assert "handle" in tool_content
    assert "preview_text" in tool_content
    # truncated may be True or False depending on output format

    # Assert - full result is in store
    from taskforce.core.interfaces.tool_result_store import ToolResultHandle

    handle = ToolResultHandle.from_dict(tool_content["handle"])
    stored_result = await integration_setup["tool_result_store"].fetch(handle)

    assert stored_result is not None
    assert stored_result["success"] is True
    assert len(stored_result["output"]) >= 50000  # Full output preserved


@pytest.mark.asyncio
async def test_multiple_large_outputs_accumulate_in_store_not_messages(integration_setup):
    """
    Test that multiple large tool outputs don't accumulate in message history.

    Scenario: Agent calls multiple tools with large outputs in sequence.
    Expected: Message history stays small, all results in store.
    """
    # Arrange
    agent = LeanAgent(
        state_manager=integration_setup["state_manager"],
        llm_provider=integration_setup["llm_provider"],
        tools=[integration_setup["python_tool"]],
        tool_result_store=integration_setup["tool_result_store"],
    )

    # Mock LLM to call tool 3 times with large outputs
    integration_setup["llm_provider"].complete.side_effect = [
        # Call 1
        {
            "success": True,
            "tool_calls": [
                {
                    "id": "call_1",
                    "type": "function",
                    "function": {
                        "name": "python",
                        "arguments": '{"code": "\\"a\\" * 20000"}',
                    },
                }
            ],
        },
        # Call 2
        {
            "success": True,
            "tool_calls": [
                {
                    "id": "call_2",
                    "type": "function",
                    "function": {
                        "name": "python",
                        "arguments": '{"code": "\\"b\\" * 20000"}',
                    },
                }
            ],
        },
        # Call 3
        {
            "success": True,
            "tool_calls": [
                {
                    "id": "call_3",
                    "type": "function",
                    "function": {
                        "name": "python",
                        "arguments": '{"code": "\\"c\\" * 20000"}',
                    },
                }
            ],
        },
        # Final answer
        {
            "success": True,
            "content": "All tasks completed",
        },
    ]

    # Act
    result = await agent.execute(
        mission="Execute multiple operations",
        session_id="integration_multiple_large",
    )

    # Assert - execution completed
    assert result.status == "completed"

    # Assert - store contains 3 results
    stats = await integration_setup["tool_result_store"].get_stats()
    assert stats["total_results"] == 3

    # Assert - final message history is still small
    final_call_args = integration_setup["llm_provider"].complete.call_args_list[-1]
    messages = final_call_args[1]["messages"]

    import json

    total_message_chars = sum(
        len(json.dumps(msg, ensure_ascii=False)) for msg in messages
    )

    # Even with 3 large outputs, message history should stay < 20KB
    assert total_message_chars < 20000, (
        f"Message history grew too large: {total_message_chars} chars. "
        "Multiple large outputs should use handles."
    )


@pytest.mark.asyncio
async def test_session_cleanup_removes_tool_results(integration_setup):
    """
    Test that cleaning up a session also removes associated tool results.
    """
    # Arrange
    agent = LeanAgent(
        state_manager=integration_setup["state_manager"],
        llm_provider=integration_setup["llm_provider"],
        tools=[integration_setup["python_tool"]],
        tool_result_store=integration_setup["tool_result_store"],
    )

    # Mock LLM
    integration_setup["llm_provider"].complete.side_effect = [
        {
            "success": True,
            "tool_calls": [
                {
                    "id": "call_cleanup",
                    "type": "function",
                    "function": {
                        "name": "python",
                        "arguments": '{"code": "\\"x\\" * 10000"}',
                    },
                }
            ],
        },
        {
            "success": True,
            "content": "Done",
        },
    ]

    session_id = "integration_cleanup_test"

    # Act - execute mission
    await agent.execute(mission="Test cleanup", session_id=session_id)

    # Assert - result was stored
    stats_before = await integration_setup["tool_result_store"].get_stats()
    assert stats_before["total_results"] == 1

    # Act - cleanup session
    count = await integration_setup["tool_result_store"].cleanup_session(session_id)

    # Assert - result was removed
    assert count == 1
    stats_after = await integration_setup["tool_result_store"].get_stats()
    assert stats_after["total_results"] == 0


@pytest.mark.asyncio
async def test_backward_compatibility_without_store(integration_setup):
    """
    Test that agent works correctly without tool_result_store (backward compatibility).

    When no store is provided, agent should fall back to standard truncation.
    """
    # Arrange - agent WITHOUT store
    agent = LeanAgent(
        state_manager=integration_setup["state_manager"],
        llm_provider=integration_setup["llm_provider"],
        tools=[integration_setup["python_tool"]],
        tool_result_store=None,  # No store
    )

    # Mock LLM
    integration_setup["llm_provider"].complete.side_effect = [
        {
            "success": True,
            "tool_calls": [
                {
                    "id": "call_no_store",
                    "type": "function",
                    "function": {
                        "name": "python",
                        "arguments": '{"code": "\\"y\\" * 30000"}',
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
        mission="Test without store",
        session_id="integration_no_store",
    )

    # Assert - execution completed
    assert result.status == "completed"

    # Assert - no results in store (because no store was used)
    stats = await integration_setup["tool_result_store"].get_stats()
    assert stats["total_results"] == 0

    # Assert - message used standard truncation
    second_call_args = integration_setup["llm_provider"].complete.call_args_list[1]
    messages = second_call_args[1]["messages"]

    tool_messages = [m for m in messages if m.get("role") == "tool"]
    assert len(tool_messages) == 1

    import json

    tool_content = json.loads(tool_messages[0]["content"])

    # Standard format (not handle format)
    assert "success" in tool_content
    assert "output" in tool_content
    assert "handle" not in tool_content

    # Output should be truncated
    assert "TRUNCATED" in tool_content["output"]

