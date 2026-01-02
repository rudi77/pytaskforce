"""
Unit Tests for LeanAgent Streaming Execution

Tests the LeanAgent.execute_stream() method which yields StreamEvent objects
during execution, enabling real-time feedback to consumers.
"""

import json
from unittest.mock import AsyncMock, MagicMock

import pytest

from taskforce.core.domain.lean_agent import LeanAgent
from taskforce.core.domain.models import StreamEvent
from taskforce.core.tools.planner_tool import PlannerTool


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


@pytest.fixture
def planner_tool():
    """Real PlannerTool for testing plan management."""
    return PlannerTool()


def make_tool_call(tool_name: str, args: dict, call_id: str = "call_1"):
    """Helper to create a tool call response structure."""
    return {
        "id": call_id,
        "type": "function",
        "function": {
            "name": tool_name,
            "arguments": json.dumps(args),
        },
    }


async def mock_stream_simple_response(content: str):
    """Mock streaming generator that yields tokens then done."""
    for token in content.split():
        yield {"type": "token", "content": token + " "}
    yield {"type": "done", "usage": {"total_tokens": 10}}


async def mock_stream_tool_call(tool_name: str, tool_id: str, args: dict):
    """Mock streaming generator that yields a tool call."""
    yield {"type": "tool_call_start", "id": tool_id, "name": tool_name, "index": 0}
    args_json = json.dumps(args)
    yield {"type": "tool_call_delta", "id": tool_id, "arguments_delta": args_json, "index": 0}
    yield {
        "type": "tool_call_end",
        "id": tool_id,
        "name": tool_name,
        "arguments": args_json,
        "index": 0,
    }
    yield {"type": "done", "usage": {"total_tokens": 15}}


class TestLeanAgentStreaming:
    """Tests for LeanAgent streaming execution."""

    @pytest.mark.asyncio
    async def test_execute_stream_yields_step_start_events(
        self, mock_state_manager, mock_tool
    ):
        """Test that step_start events are yielded for each loop iteration."""
        # Create mock provider with streaming support
        mock_provider = AsyncMock()
        mock_provider.complete_stream = MagicMock(
            return_value=mock_stream_simple_response("Hello world!")
        )

        agent = LeanAgent(
            state_manager=mock_state_manager,
            llm_provider=mock_provider,
            tools=[mock_tool],
            system_prompt="Test prompt",
        )

        events = []
        async for event in agent.execute_stream("Say hello", "test-session"):
            events.append(event)

        step_events = [e for e in events if e.event_type == "step_start"]
        assert len(step_events) >= 1
        assert step_events[0].data["step"] == 1
        assert step_events[0].data["max_steps"] == agent.MAX_STEPS

    @pytest.mark.asyncio
    async def test_execute_stream_yields_llm_token_events(
        self, mock_state_manager, mock_tool
    ):
        """Test that llm_token events are yielded for LLM response tokens."""
        mock_provider = AsyncMock()
        mock_provider.complete_stream = MagicMock(
            return_value=mock_stream_simple_response("Hello world!")
        )

        agent = LeanAgent(
            state_manager=mock_state_manager,
            llm_provider=mock_provider,
            tools=[mock_tool],
            system_prompt="Test prompt",
        )

        events = []
        async for event in agent.execute_stream("Say hello", "test-session"):
            events.append(event)

        token_events = [e for e in events if e.event_type == "llm_token"]
        assert len(token_events) >= 1
        assert all("content" in e.data for e in token_events)

    @pytest.mark.asyncio
    async def test_execute_stream_yields_tool_call_events(
        self, mock_state_manager, mock_tool
    ):
        """Test that tool_call events are yielded before tool execution."""
        call_count = 0

        async def streaming_with_tool_then_response(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                # First call: tool call
                async for chunk in mock_stream_tool_call(
                    "test_tool", "call_1", {"param": "value"}
                ):
                    yield chunk
            else:
                # Second call: final response
                async for chunk in mock_stream_simple_response("Task completed"):
                    yield chunk

        mock_provider = AsyncMock()
        mock_provider.complete_stream = streaming_with_tool_then_response

        agent = LeanAgent(
            state_manager=mock_state_manager,
            llm_provider=mock_provider,
            tools=[mock_tool],
            system_prompt="Test prompt",
        )

        events = []
        async for event in agent.execute_stream("Use test_tool", "test-session"):
            events.append(event)

        tool_call_events = [e for e in events if e.event_type == "tool_call"]
        assert len(tool_call_events) >= 1
        assert tool_call_events[0].data["tool"] == "test_tool"
        assert tool_call_events[0].data["status"] == "starting"

    @pytest.mark.asyncio
    async def test_execute_stream_yields_tool_result_events(
        self, mock_state_manager, mock_tool
    ):
        """Test that tool_result events are yielded after tool execution."""
        call_count = 0

        async def streaming_with_tool_then_response(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                async for chunk in mock_stream_tool_call(
                    "test_tool", "call_1", {"param": "value"}
                ):
                    yield chunk
            else:
                async for chunk in mock_stream_simple_response("Done"):
                    yield chunk

        mock_provider = AsyncMock()
        mock_provider.complete_stream = streaming_with_tool_then_response

        agent = LeanAgent(
            state_manager=mock_state_manager,
            llm_provider=mock_provider,
            tools=[mock_tool],
            system_prompt="Test prompt",
        )

        events = []
        async for event in agent.execute_stream("Use test_tool", "test-session"):
            events.append(event)

        tool_result_events = [e for e in events if e.event_type == "tool_result"]
        assert len(tool_result_events) >= 1
        assert tool_result_events[0].data["tool"] == "test_tool"
        assert tool_result_events[0].data["success"] is True
        assert "output" in tool_result_events[0].data

    @pytest.mark.asyncio
    async def test_execute_stream_yields_plan_updated_events(
        self, mock_state_manager, mock_tool, planner_tool
    ):
        """Test that plan_updated events are yielded when PlannerTool is used."""
        call_count = 0

        async def streaming_with_planner(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                # Create plan
                async for chunk in mock_stream_tool_call(
                    "planner",
                    "call_1",
                    {"action": "create_plan", "tasks": ["Step 1", "Step 2"]},
                ):
                    yield chunk
            else:
                async for chunk in mock_stream_simple_response("Plan created"):
                    yield chunk

        mock_provider = AsyncMock()
        mock_provider.complete_stream = streaming_with_planner

        agent = LeanAgent(
            state_manager=mock_state_manager,
            llm_provider=mock_provider,
            tools=[mock_tool, planner_tool],
            system_prompt="Test prompt",
        )

        events = []
        async for event in agent.execute_stream("Create a plan", "test-session"):
            events.append(event)

        plan_events = [e for e in events if e.event_type == "plan_updated"]
        assert len(plan_events) >= 1
        assert plan_events[0].data["action"] == "create_plan"

    @pytest.mark.asyncio
    async def test_execute_stream_yields_final_answer_event(
        self, mock_state_manager, mock_tool
    ):
        """Test that final_answer event is yielded at the end."""
        mock_provider = AsyncMock()
        mock_provider.complete_stream = MagicMock(
            return_value=mock_stream_simple_response("This is the final answer.")
        )

        agent = LeanAgent(
            state_manager=mock_state_manager,
            llm_provider=mock_provider,
            tools=[mock_tool],
            system_prompt="Test prompt",
        )

        events = []
        async for event in agent.execute_stream("Answer question", "test-session"):
            events.append(event)

        final_events = [e for e in events if e.event_type == "final_answer"]
        assert len(final_events) == 1
        assert "content" in final_events[0].data
        # Content is accumulated tokens
        assert "This" in final_events[0].data["content"]

    @pytest.mark.asyncio
    async def test_execute_stream_graceful_fallback_no_streaming(
        self, mock_state_manager, mock_tool
    ):
        """Test graceful fallback when provider doesn't support streaming."""
        # Create provider WITHOUT complete_stream method
        mock_provider = AsyncMock()
        mock_provider.complete.return_value = {
            "success": True,
            "content": "Hello from non-streaming!",
            "tool_calls": None,
        }
        # Explicitly remove complete_stream to test fallback
        if hasattr(mock_provider, "complete_stream"):
            delattr(mock_provider, "complete_stream")

        agent = LeanAgent(
            state_manager=mock_state_manager,
            llm_provider=mock_provider,
            tools=[mock_tool],
            system_prompt="Test prompt",
        )

        events = []
        async for event in agent.execute_stream("Test fallback", "test-session"):
            events.append(event)

        # Should still yield final_answer event from fallback
        final_events = [e for e in events if e.event_type == "final_answer"]
        assert len(final_events) == 1
        assert final_events[0].data["content"] == "Hello from non-streaming!"

    @pytest.mark.asyncio
    async def test_execute_stream_saves_state(
        self, mock_state_manager, mock_tool, planner_tool
    ):
        """Test that state is persisted at the end of streaming execution."""
        call_count = 0

        async def streaming_with_planner(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                async for chunk in mock_stream_tool_call(
                    "planner",
                    "call_1",
                    {"action": "create_plan", "tasks": ["Task A"]},
                ):
                    yield chunk
            else:
                async for chunk in mock_stream_simple_response("Done"):
                    yield chunk

        mock_provider = AsyncMock()
        mock_provider.complete_stream = streaming_with_planner

        agent = LeanAgent(
            state_manager=mock_state_manager,
            llm_provider=mock_provider,
            tools=[mock_tool, planner_tool],
            system_prompt="Test prompt",
        )

        events = []
        async for event in agent.execute_stream("Create plan", "test-session"):
            events.append(event)

        # Verify state was saved with planner_state
        mock_state_manager.save_state.assert_called()
        saved_state = mock_state_manager.save_state.call_args[0][1]
        assert "planner_state" in saved_state

    @pytest.mark.asyncio
    async def test_execute_stream_yields_error_events(
        self, mock_state_manager, mock_tool
    ):
        """Test that error events are yielded when streaming errors occur."""

        async def streaming_with_error(*args, **kwargs):
            yield {"type": "error", "message": "API error occurred"}

        mock_provider = AsyncMock()
        mock_provider.complete_stream = streaming_with_error

        agent = LeanAgent(
            state_manager=mock_state_manager,
            llm_provider=mock_provider,
            tools=[mock_tool],
            system_prompt="Test prompt",
        )
        agent.MAX_STEPS = 2  # Limit steps for test

        events = []
        async for event in agent.execute_stream("Test error", "test-session"):
            events.append(event)

        error_events = [e for e in events if e.event_type == "error"]
        assert len(error_events) >= 1

    @pytest.mark.asyncio
    async def test_execute_still_works_after_streaming_added(
        self, mock_state_manager, mock_tool
    ):
        """Test backward compatibility: execute() still works unchanged."""
        mock_provider = AsyncMock()
        mock_provider.complete.return_value = {
            "success": True,
            "content": "Hello from execute()!",
            "tool_calls": None,
        }
        mock_provider.complete_stream = MagicMock(
            return_value=mock_stream_simple_response("Hello")
        )

        agent = LeanAgent(
            state_manager=mock_state_manager,
            llm_provider=mock_provider,
            tools=[mock_tool],
            system_prompt="Test prompt",
        )

        # Test that regular execute() still works
        result = await agent.execute("Test execute", "test-session")

        assert result.status == "completed"
        assert result.final_message == "Hello from execute()!"


class TestStreamEventDataclass:
    """Tests for the StreamEvent dataclass."""

    def test_stream_event_creation(self):
        """Test StreamEvent can be created with required fields."""
        event = StreamEvent(
            event_type="step_start",
            data={"step": 1, "max_steps": 30},
        )

        assert event.event_type == "step_start"
        assert event.data["step"] == 1
        assert event.timestamp is not None

    def test_stream_event_to_dict(self):
        """Test StreamEvent.to_dict() returns correct format."""
        event = StreamEvent(
            event_type="llm_token",
            data={"content": "Hello"},
        )

        result = event.to_dict()

        assert result["event_type"] == "llm_token"
        assert result["data"]["content"] == "Hello"
        assert "timestamp" in result
        assert isinstance(result["timestamp"], str)  # ISO format

    def test_stream_event_all_types_valid(self):
        """Test all defined event types can be used."""
        event_types = [
            "step_start",
            "llm_token",
            "tool_call",
            "tool_result",
            "plan_updated",
            "final_answer",
            "error",
        ]

        for event_type in event_types:
            event = StreamEvent(event_type=event_type, data={})
            assert event.event_type == event_type


class TestStreamingMultiStep:
    """Tests for multi-step streaming execution."""

    @pytest.mark.asyncio
    async def test_execute_stream_multiple_tool_calls(
        self, mock_state_manager, mock_tool
    ):
        """Test streaming with multiple tool calls in sequence."""
        call_count = 0

        async def streaming_multi_step(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                # First tool call
                async for chunk in mock_stream_tool_call(
                    "test_tool", "call_1", {"param": "first"}
                ):
                    yield chunk
            elif call_count == 2:
                # Second tool call
                async for chunk in mock_stream_tool_call(
                    "test_tool", "call_2", {"param": "second"}
                ):
                    yield chunk
            else:
                # Final answer
                async for chunk in mock_stream_simple_response("All done"):
                    yield chunk

        mock_provider = AsyncMock()
        mock_provider.complete_stream = streaming_multi_step

        agent = LeanAgent(
            state_manager=mock_state_manager,
            llm_provider=mock_provider,
            tools=[mock_tool],
            system_prompt="Test prompt",
        )

        events = []
        async for event in agent.execute_stream("Multi-step task", "test-session"):
            events.append(event)

        # Should have multiple step_start events
        step_events = [e for e in events if e.event_type == "step_start"]
        assert len(step_events) == 3  # 3 iterations

        # Should have multiple tool_call events
        tool_call_events = [e for e in events if e.event_type == "tool_call"]
        assert len(tool_call_events) == 2

        # Should have final_answer at the end
        final_events = [e for e in events if e.event_type == "final_answer"]
        assert len(final_events) == 1


class TestTruncateOutput:
    """Tests for the _truncate_output helper method."""

    @pytest.mark.asyncio
    async def test_truncate_output_short_string(self, mock_state_manager, mock_tool):
        """Test that short strings are not truncated."""
        mock_provider = AsyncMock()
        mock_provider.complete_stream = MagicMock(
            return_value=mock_stream_simple_response("Hello")
        )

        agent = LeanAgent(
            state_manager=mock_state_manager,
            llm_provider=mock_provider,
            tools=[mock_tool],
            system_prompt="Test",
        )

        result = agent._truncate_output("Short text")
        assert result == "Short text"
        assert "..." not in result

    @pytest.mark.asyncio
    async def test_truncate_output_long_string(self, mock_state_manager, mock_tool):
        """Test that long strings are truncated with ellipsis."""
        mock_provider = AsyncMock()
        mock_provider.complete_stream = MagicMock(
            return_value=mock_stream_simple_response("Hello")
        )

        agent = LeanAgent(
            state_manager=mock_state_manager,
            llm_provider=mock_provider,
            tools=[mock_tool],
            system_prompt="Test",
        )

        long_text = "A" * 300
        result = agent._truncate_output(long_text)

        assert len(result) == 203  # 200 + "..."
        assert result.endswith("...")

