"""
Unit tests for LeanAgent Context Pack Injection (Story 9.2)

Tests that LeanAgent properly injects context packs before LLM calls.
"""

import json
from unittest.mock import AsyncMock, MagicMock

import pytest

from taskforce.core.domain.context_policy import ContextPolicy
from taskforce.core.domain.lean_agent import LeanAgent


@pytest.fixture
def mock_state_manager():
    """Create mock state manager."""
    manager = AsyncMock()
    manager.load_state = AsyncMock(return_value={})
    manager.save_state = AsyncMock()
    return manager


@pytest.fixture
def mock_llm_provider():
    """Create mock LLM provider."""
    provider = AsyncMock()
    provider.complete = AsyncMock(
        return_value={
            "success": True,
            "content": "Final answer",
            "tool_calls": None,
        }
    )
    return provider


@pytest.fixture
def mock_tool():
    """Create mock tool."""
    tool = MagicMock()
    tool.name = "test_tool"
    tool.description = "A test tool"
    tool.parameters_schema = {"type": "object", "properties": {}}
    tool.execute = AsyncMock(return_value={"success": True, "output": "Tool result"})
    return tool


class TestLeanAgentContextInjection:
    """Test context pack injection in LeanAgent."""

    @pytest.mark.asyncio
    async def test_agent_has_context_policy(
        self, mock_state_manager, mock_llm_provider, mock_tool
    ):
        """Test that agent initializes with context policy."""
        policy = ContextPolicy(max_items=5)
        agent = LeanAgent(
            state_manager=mock_state_manager,
            llm_provider=mock_llm_provider,
            tools=[mock_tool],
            context_policy=policy,
        )

        assert agent.context_policy == policy
        assert agent.context_builder is not None
        assert agent.context_builder.policy == policy

    @pytest.mark.asyncio
    async def test_agent_uses_conservative_default_policy(
        self, mock_state_manager, mock_llm_provider, mock_tool
    ):
        """Test that agent uses conservative default if no policy provided."""
        agent = LeanAgent(
            state_manager=mock_state_manager,
            llm_provider=mock_llm_provider,
            tools=[mock_tool],
        )

        assert agent.context_policy is not None
        assert agent.context_policy.max_items == 5  # Conservative default

    @pytest.mark.asyncio
    async def test_context_pack_injected_in_system_prompt(
        self, mock_state_manager, mock_llm_provider, mock_tool
    ):
        """Test that context pack is injected into system prompt."""
        policy = ContextPolicy.conservative_default()
        agent = LeanAgent(
            state_manager=mock_state_manager,
            llm_provider=mock_llm_provider,
            tools=[mock_tool],
            context_policy=policy,
        )

        # Execute mission
        await agent.execute("Test mission", "session_1")

        # Check that LLM was called
        assert mock_llm_provider.complete.called

        # Get the messages passed to LLM
        call_args = mock_llm_provider.complete.call_args
        messages = call_args.kwargs["messages"]

        # First message should be system prompt
        assert messages[0]["role"] == "system"
        system_prompt = messages[0]["content"]

        # System prompt should contain context pack header
        assert "CONTEXT PACK (BUDGETED)" in system_prompt

    @pytest.mark.asyncio
    async def test_context_pack_includes_mission(
        self, mock_state_manager, mock_llm_provider, mock_tool
    ):
        """Test that context pack includes mission description."""
        policy = ContextPolicy(max_chars_per_item=1000)
        agent = LeanAgent(
            state_manager=mock_state_manager,
            llm_provider=mock_llm_provider,
            tools=[mock_tool],
            context_policy=policy,
        )

        mission = "Analyze the CSV file"
        await agent.execute(mission, "session_1")

        # Get system prompt
        call_args = mock_llm_provider.complete.call_args
        messages = call_args.kwargs["messages"]
        system_prompt = messages[0]["content"]

        # Mission should be in context pack
        assert mission in system_prompt

    @pytest.mark.asyncio
    async def test_context_pack_includes_tool_previews(
        self, mock_state_manager, mock_llm_provider
    ):
        """Test that context pack includes tool result previews."""
        # Create tool that returns large result
        large_tool = MagicMock()
        large_tool.name = "large_tool"
        large_tool.description = "Returns large output"
        large_tool.parameters_schema = {"type": "object", "properties": {}}
        large_tool.execute = AsyncMock(
            return_value={"success": True, "output": "X" * 10000}
        )

        # Mock LLM to first call tool, then return final answer
        llm_provider = AsyncMock()
        call_count = 0

        async def mock_complete(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                # First call: request tool
                return {
                    "success": True,
                    "tool_calls": [
                        {
                            "id": "call_1",
                            "type": "function",
                            "function": {"name": "large_tool", "arguments": "{}"},
                        }
                    ],
                }
            else:
                # Second call: return final answer
                return {"success": True, "content": "Done", "tool_calls": None}

        llm_provider.complete = AsyncMock(side_effect=mock_complete)

        policy = ContextPolicy.conservative_default()
        agent = LeanAgent(
            state_manager=mock_state_manager,
            llm_provider=llm_provider,
            tools=[large_tool],
            context_policy=policy,
        )

        await agent.execute("Test mission", "session_1")

        # Second LLM call should have context pack with tool preview
        assert llm_provider.complete.call_count == 2
        second_call_args = llm_provider.complete.call_args_list[1]
        messages = second_call_args[1]["messages"]
        system_prompt = messages[0]["content"]

        # Context pack should be present
        assert "CONTEXT PACK (BUDGETED)" in system_prompt

    @pytest.mark.asyncio
    async def test_context_pack_respects_budget(
        self, mock_state_manager, mock_llm_provider, mock_tool
    ):
        """Test that context pack respects policy budget."""
        # Very restrictive policy
        policy = ContextPolicy(
            max_items=1, max_chars_per_item=50, max_total_chars=100
        )
        agent = LeanAgent(
            state_manager=mock_state_manager,
            llm_provider=mock_llm_provider,
            tools=[mock_tool],
            context_policy=policy,
        )

        # Long mission that exceeds budget
        mission = "A" * 200
        await agent.execute(mission, "session_1")

        # Get system prompt
        call_args = mock_llm_provider.complete.call_args
        messages = call_args.kwargs["messages"]
        system_prompt = messages[0]["content"]

        # Mission should NOT be in context pack (exceeds max_chars_per_item)
        assert mission not in system_prompt

    @pytest.mark.asyncio
    async def test_context_pack_rebuilt_each_loop(
        self, mock_state_manager, mock_llm_provider
    ):
        """Test that context pack is rebuilt on each loop iteration."""
        # Create tool
        tool = MagicMock()
        tool.name = "test_tool"
        tool.description = "Test tool"
        tool.parameters_schema = {"type": "object", "properties": {}}
        tool.execute = AsyncMock(
            return_value={"success": True, "output": "Tool output"}
        )

        # Mock LLM to call tool twice, then return answer
        call_count = 0

        async def mock_complete(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count <= 2:
                return {
                    "success": True,
                    "tool_calls": [
                        {
                            "id": f"call_{call_count}",
                            "type": "function",
                            "function": {"name": "test_tool", "arguments": "{}"},
                        }
                    ],
                }
            else:
                return {"success": True, "content": "Done", "tool_calls": None}

        llm_provider = AsyncMock()
        llm_provider.complete = AsyncMock(side_effect=mock_complete)

        policy = ContextPolicy.conservative_default()
        agent = LeanAgent(
            state_manager=mock_state_manager,
            llm_provider=llm_provider,
            tools=[tool],
            context_policy=policy,
        )

        await agent.execute("Test mission", "session_1")

        # LLM should be called 3 times
        assert llm_provider.complete.call_count == 3

        # Each call should have context pack in system prompt
        for call_args in llm_provider.complete.call_args_list:
            messages = call_args[1]["messages"]
            system_prompt = messages[0]["content"]
            assert "CONTEXT PACK (BUDGETED)" in system_prompt

    @pytest.mark.asyncio
    async def test_context_pack_with_tool_result_store(
        self, mock_state_manager, mock_llm_provider
    ):
        """Test context pack works with tool result store (Story 9.1)."""
        # Create mock tool result store
        tool_result_store = AsyncMock()
        tool_result_store.put = AsyncMock(
            return_value=MagicMock(
                id="handle_1",
                tool="test_tool",
                size_chars=10000,
                to_dict=lambda: {
                    "id": "handle_1",
                    "tool": "test_tool",
                    "size_chars": 10000,
                },
            )
        )

        # Create tool with large output
        tool = MagicMock()
        tool.name = "test_tool"
        tool.description = "Test tool"
        tool.parameters_schema = {"type": "object", "properties": {}}
        tool.execute = AsyncMock(
            return_value={"success": True, "output": "X" * 10000}
        )

        # Mock LLM
        call_count = 0

        async def mock_complete(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return {
                    "success": True,
                    "tool_calls": [
                        {
                            "id": "call_1",
                            "type": "function",
                            "function": {"name": "test_tool", "arguments": "{}"},
                        }
                    ],
                }
            else:
                return {"success": True, "content": "Done", "tool_calls": None}

        llm_provider = AsyncMock()
        llm_provider.complete = AsyncMock(side_effect=mock_complete)

        policy = ContextPolicy.conservative_default()
        agent = LeanAgent(
            state_manager=mock_state_manager,
            llm_provider=llm_provider,
            tools=[tool],
            tool_result_store=tool_result_store,
            context_policy=policy,
        )

        await agent.execute("Test mission", "session_1")

        # Tool result should be stored
        assert tool_result_store.put.called

        # Second LLM call should have context pack
        assert llm_provider.complete.call_count == 2
        second_call_args = llm_provider.complete.call_args_list[1]
        messages = second_call_args[1]["messages"]
        system_prompt = messages[0]["content"]

        assert "CONTEXT PACK (BUDGETED)" in system_prompt

