"""
Unit Tests for Token Usage Tracking

Tests that token usage is properly tracked and emitted as events during
agent execution, and that ExecutionResult contains aggregated token statistics.
"""

import json
from unittest.mock import AsyncMock, MagicMock

import pytest

from taskforce.core.domain.lean_agent import LeanAgent
from taskforce.core.domain.models import StreamEvent, ExecutionResult
from taskforce.core.domain.planning_strategy import _collect_execution_result


@pytest.fixture
def mock_state_manager():
    """Mock StateManagerProtocol."""
    mock = AsyncMock()
    mock.load_state.return_value = {"answers": {}}
    mock.save_state.return_value = True
    return mock


@pytest.fixture
def mock_tool():
    """Mock ToolProtocol for a generic tool."""
    tool = MagicMock()
    tool.name = "test_tool"
    tool.description = "A test tool for unit tests"
    tool.parameters_schema = {
        "type": "object",
        "properties": {"param": {"type": "string"}},
    }
    tool.execute = AsyncMock(
        return_value={"success": True, "output": "test result"}
    )
    return tool


async def mock_stream_with_token_usage():
    """Mock streaming generator that yields tokens and token usage."""
    # First LLM call with token usage
    yield {"type": "token", "content": "Hello "}
    yield {"type": "token", "content": "world!"}
    yield {
        "type": "done",
        "usage": {
            "prompt_tokens": 10,
            "completion_tokens": 5,
            "total_tokens": 15,
        },
    }


class TestTokenUsageTracking:
    """Tests for token usage tracking feature."""

    @pytest.mark.asyncio
    async def test_stream_event_includes_token_usage(
        self, mock_state_manager, mock_tool
    ):
        """Test that token_usage StreamEvent is emitted with LLM calls."""
        # Create mock provider with streaming support that includes usage
        mock_provider = AsyncMock()
        mock_provider.complete_stream = MagicMock(
            return_value=mock_stream_with_token_usage()
        )

        agent = LeanAgent(
            state_manager=mock_state_manager,
            llm_provider=mock_provider,
            tools=[mock_tool],
        )

        # Collect all events
        events = []
        async for event in agent.execute_stream("Test mission", "test-session"):
            events.append(event)

        # Find token_usage events
        token_usage_events = [e for e in events if e.event_type == "token_usage"]

        # Should have at least one token_usage event
        assert len(token_usage_events) > 0, "Expected token_usage events"

        # Verify event structure
        usage_event = token_usage_events[0]
        assert usage_event.event_type == "token_usage"
        assert "prompt_tokens" in usage_event.data
        assert "completion_tokens" in usage_event.data
        assert "total_tokens" in usage_event.data
        assert usage_event.data["total_tokens"] == 15

    @pytest.mark.asyncio
    async def test_execution_result_aggregates_token_usage(self):
        """Test that ExecutionResult aggregates token usage from multiple events."""

        async def mock_events():
            # Simulate multiple LLM calls with different token usage
            yield StreamEvent(
                event_type="token_usage",
                data={
                    "prompt_tokens": 10,
                    "completion_tokens": 5,
                    "total_tokens": 15,
                },
            )
            yield StreamEvent(
                event_type="token_usage",
                data={
                    "prompt_tokens": 20,
                    "completion_tokens": 10,
                    "total_tokens": 30,
                },
            )
            yield StreamEvent(
                event_type="final_answer",
                data={"content": "Test complete"},
            )

        result = await _collect_execution_result("test-session", mock_events())

        # Verify aggregated token usage
        assert result.token_usage is not None
        assert result.token_usage["prompt_tokens"] == 30  # 10 + 20
        assert result.token_usage["completion_tokens"] == 15  # 5 + 10
        assert result.token_usage["total_tokens"] == 45  # 15 + 30

    @pytest.mark.asyncio
    async def test_execution_result_default_token_usage(self):
        """Test that ExecutionResult has default zero token usage."""

        async def mock_events():
            # No token_usage events
            yield StreamEvent(
                event_type="final_answer",
                data={"content": "Test complete"},
            )

        result = await _collect_execution_result("test-session", mock_events())

        # Verify default token usage
        assert result.token_usage is not None
        assert result.token_usage["prompt_tokens"] == 0
        assert result.token_usage["completion_tokens"] == 0
        assert result.token_usage["total_tokens"] == 0

    def test_execution_result_has_token_usage_field(self):
        """Test that ExecutionResult includes token_usage field."""
        result = ExecutionResult(
            session_id="test-123",
            status="completed",
            final_message="Done",
        )

        # Verify token_usage field exists with defaults
        assert hasattr(result, "token_usage")
        assert result.token_usage["prompt_tokens"] == 0
        assert result.token_usage["completion_tokens"] == 0
        assert result.token_usage["total_tokens"] == 0

    def test_execution_result_accepts_custom_token_usage(self):
        """Test that ExecutionResult accepts custom token usage."""
        custom_usage = {
            "prompt_tokens": 100,
            "completion_tokens": 50,
            "total_tokens": 150,
        }

        result = ExecutionResult(
            session_id="test-123",
            status="completed",
            final_message="Done",
            token_usage=custom_usage,
        )

        assert result.token_usage == custom_usage
