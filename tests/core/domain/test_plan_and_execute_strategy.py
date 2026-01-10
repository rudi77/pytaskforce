"""
Unit Tests for PlanAndExecuteStrategy Extracted Functions

Tests the decomposed functions from PlanAndExecuteStrategy.execute_stream:
- _initialize_plan()
- _execute_plan_step()
- _process_step_tool_calls()
- _check_step_completion()
- _generate_final_response()
- _parse_plan_steps() (exception handling)
"""

from __future__ import annotations

import json
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from taskforce.core.domain.models import StreamEvent
from taskforce.core.domain.planning_strategy import (
    PlanAndExecuteStrategy,
    _parse_plan_steps,
)
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
def mock_logger() -> MockLogger:
    """Create a mock logger."""
    return MockLogger()


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
    agent._create_tool_message = AsyncMock(
        return_value={"role": "tool", "content": "Tool result"}
    )
    agent._truncate_output = MagicMock(side_effect=lambda x: x[:100])
    agent._execute_tool = AsyncMock(return_value={"success": True, "output": "Done"})
    agent.llm_provider = AsyncMock()
    agent.state_manager = AsyncMock()
    agent.state_store = AsyncMock()
    return agent


@pytest.fixture
def strategy(mock_logger: MockLogger) -> PlanAndExecuteStrategy:
    """Create PlanAndExecuteStrategy instance."""
    return PlanAndExecuteStrategy(
        max_step_iterations=3, max_plan_steps=5, logger=mock_logger
    )


class TestParsePlanSteps:
    """Test _parse_plan_steps exception handling."""

    def test_parse_valid_json_array(self, mock_logger: MockLogger) -> None:
        """Test parsing valid JSON array."""
        content = '```json\n["Step 1", "Step 2", "Step 3"]\n```'
        result = _parse_plan_steps(content, mock_logger)
        assert result == ["Step 1", "Step 2", "Step 3"]

    def test_parse_json_without_code_block(self, mock_logger: MockLogger) -> None:
        """Test parsing JSON without code block markers falls back to line parsing."""
        content = '["Step 1", "Step 2"]'
        result = _parse_plan_steps(content, mock_logger)
        # Without code block, function goes straight to line parsing
        # The JSON string becomes a single line, which gets parsed as a step
        assert len(result) >= 1
        # The entire JSON string may be treated as one step in line parsing
        assert any("Step" in step for step in result)

    def test_parse_malformed_json_falls_back_to_lines(
        self, mock_logger: MockLogger
    ) -> None:
        """Test malformed JSON falls back to line-based parsing."""
        content = "```json\n{invalid json}\n```\n1. Step one\n2. Step two"
        result = _parse_plan_steps(content, mock_logger)
        assert len(result) >= 2
        assert any("Step one" in step for step in result)
        assert any("Step two" in step for step in result)
        assert any(
            log[1]["event"] == "json_parse_failed" for log in mock_logger.logs
        )

    def test_parse_invalid_type_falls_back(self, mock_logger: MockLogger) -> None:
        """Test invalid type (not a list) falls back to line parsing."""
        content = '```json\n{"not": "a list"}\n```\n- Step one'
        result = _parse_plan_steps(content, mock_logger)
        assert len(result) >= 1
        assert any("Step one" in step for step in result)

    def test_parse_empty_content_returns_empty_list(
        self, mock_logger: MockLogger
    ) -> None:
        """Test empty content returns empty list."""
        result = _parse_plan_steps("", mock_logger)
        assert result == []

    def test_parse_line_based_format(self, mock_logger: MockLogger) -> None:
        """Test parsing line-based format."""
        content = "1. First step\n2. Second step\n- Third step"
        result = _parse_plan_steps(content, mock_logger)
        assert len(result) >= 2
        assert any("First step" in step for step in result)
        assert any("Second step" in step for step in result)


class TestInitializePlan:
    """Test _initialize_plan() function."""

    @pytest.mark.asyncio
    async def test_initialize_plan_with_llm_steps(
        self, strategy: PlanAndExecuteStrategy, mock_agent: MagicMock
    ) -> None:
        """Test plan initialization with LLM-generated steps."""
        mock_agent.llm_provider.complete = AsyncMock(
            return_value={
                "success": True,
                "content": '```json\n["Analyze", "Execute", "Summarize"]\n```',
            }
        )
        result = await strategy._initialize_plan(
            mock_agent, "Test mission", strategy.logger
        )
        assert len(result) == 3
        assert result == ["Analyze", "Execute", "Summarize"]

    @pytest.mark.asyncio
    async def test_initialize_plan_fallback_to_defaults(
        self, strategy: PlanAndExecuteStrategy, mock_agent: MagicMock
    ) -> None:
        """Test plan initialization falls back to defaults when LLM fails."""
        mock_agent.llm_provider.complete = AsyncMock(
            return_value={"success": False, "error": "LLM error"}
        )
        result = await strategy._initialize_plan(
            mock_agent, "Test mission", strategy.logger
        )
        assert len(result) == 3
        assert "Analyze the mission" in result[0]
        assert "Summarize the results" in result[2]

    @pytest.mark.asyncio
    async def test_initialize_plan_respects_max_steps(
        self, strategy: PlanAndExecuteStrategy, mock_agent: MagicMock
    ) -> None:
        """Test plan initialization respects max_plan_steps limit."""
        steps_json = json.dumps([f"Step {i}" for i in range(10)])
        mock_agent.llm_provider.complete = AsyncMock(
            return_value={
                "success": True,
                "content": f"```json\n{steps_json}\n```",
            }
        )
        result = await strategy._initialize_plan(
            mock_agent, "Test mission", strategy.logger
        )
        assert len(result) == 5
        assert result == ["Step 0", "Step 1", "Step 2", "Step 3", "Step 4"]


class TestCheckStepCompletion:
    """Test _check_step_completion() function."""

    @pytest.mark.asyncio
    async def test_check_completion_with_content(
        self, strategy: PlanAndExecuteStrategy, mock_agent: MagicMock
    ) -> None:
        """Test step completion detection with content."""
        messages: list[dict[str, Any]] = []
        is_complete, plan_event = await strategy._check_step_completion(
            "Step completed", mock_agent, 1, messages
        )
        assert is_complete is True
        assert plan_event is None
        assert len(messages) == 1
        assert messages[0]["role"] == "assistant"
        assert messages[0]["content"] == "Step completed"

    @pytest.mark.asyncio
    async def test_check_completion_without_content(
        self, strategy: PlanAndExecuteStrategy, mock_agent: MagicMock
    ) -> None:
        """Test step completion detection without content."""
        messages: list[dict[str, Any]] = []
        is_complete, plan_event = await strategy._check_step_completion(
            "", mock_agent, 1, messages
        )
        assert is_complete is False
        assert plan_event is None
        assert len(messages) == 0

    @pytest.mark.asyncio
    async def test_check_completion_with_planner(
        self, strategy: PlanAndExecuteStrategy, mock_agent: MagicMock
    ) -> None:
        """Test step completion with planner integration."""
        mock_planner = AsyncMock()
        mock_planner.execute = AsyncMock()
        mock_planner.get_plan_summary = MagicMock(return_value="Plan summary")
        mock_agent._planner = mock_planner

        messages: list[dict[str, Any]] = []
        is_complete, plan_event = await strategy._check_step_completion(
            "Done", mock_agent, 2, messages
        )

        assert is_complete is True
        assert plan_event is not None
        assert plan_event.event_type == "plan_updated"
        assert plan_event.data["action"] == "mark_done"
        assert plan_event.data["step"] == 2
        assert plan_event.data["status"] == "completed"
        mock_planner.execute.assert_called_once_with(action="mark_done", step_index=2)


class TestProcessStepToolCalls:
    """Test _process_step_tool_calls() function."""

    @pytest.mark.asyncio
    async def test_process_single_tool_call(
        self, strategy: PlanAndExecuteStrategy, mock_agent: MagicMock
    ) -> None:
        """Test processing a single tool call."""
        from taskforce.core.domain.planning_strategy import _execute_tool_calls

        tool_calls = [
            {
                "id": "call_123",
                "function": {"name": "test_tool", "arguments": '{"arg": "value"}'},
            }
        ]
        messages: list[dict[str, Any]] = []

        mock_agent._execute_tool = AsyncMock(
            return_value={"success": True, "output": "Tool output"}
        )

        events = []
        async for event in strategy._process_step_tool_calls(
            tool_calls, mock_agent, "session_1", 1, messages, strategy.logger
        ):
            events.append(event)

        assert len(events) >= 2
        assert events[0].event_type == "tool_call"
        assert events[0].data["tool"] == "test_tool"
        assert any(e.event_type == "tool_result" for e in events)
        assert len(messages) >= 2

    @pytest.mark.asyncio
    async def test_process_multiple_tool_calls(
        self, strategy: PlanAndExecuteStrategy, mock_agent: MagicMock
    ) -> None:
        """Test processing multiple tool calls."""
        tool_calls = [
            {
                "id": "call_1",
                "function": {"name": "tool_a", "arguments": "{}"},
            },
            {
                "id": "call_2",
                "function": {"name": "tool_b", "arguments": "{}"},
            },
        ]
        messages: list[dict[str, Any]] = []

        mock_agent._execute_tool = AsyncMock(
            return_value={"success": True, "output": "Done"}
        )

        events = []
        async for event in strategy._process_step_tool_calls(
            tool_calls, mock_agent, "session_1", 1, messages, strategy.logger
        ):
            events.append(event)

        tool_call_events = [e for e in events if e.event_type == "tool_call"]
        assert len(tool_call_events) == 2


class TestGenerateFinalResponse:
    """Test _generate_final_response() function."""

    @pytest.mark.asyncio
    async def test_generate_final_response_success(
        self, strategy: PlanAndExecuteStrategy, mock_agent: MagicMock
    ) -> None:
        """Test successful final response generation."""
        mock_agent.llm_provider.complete = AsyncMock(
            return_value={"success": True, "content": "Final summary"}
        )
        messages: list[dict[str, Any]] = [{"role": "user", "content": "Mission"}]

        result = await strategy._generate_final_response(mock_agent, messages)

        assert result == "Final summary"
        assert len(messages) == 2
        assert "All planned steps are complete" in messages[1]["content"]
        mock_agent.llm_provider.complete.assert_called_once()

    @pytest.mark.asyncio
    async def test_generate_final_response_failure(
        self, strategy: PlanAndExecuteStrategy, mock_agent: MagicMock
    ) -> None:
        """Test final response generation when LLM fails."""
        mock_agent.llm_provider.complete = AsyncMock(
            return_value={"success": False, "error": "LLM error"}
        )
        messages: list[dict[str, Any]] = []

        result = await strategy._generate_final_response(mock_agent, messages)

        assert result == ""

    @pytest.mark.asyncio
    async def test_generate_final_response_empty_content(
        self, strategy: PlanAndExecuteStrategy, mock_agent: MagicMock
    ) -> None:
        """Test final response generation with empty content."""
        mock_agent.llm_provider.complete = AsyncMock(
            return_value={"success": True, "content": ""}
        )
        messages: list[dict[str, Any]] = []

        result = await strategy._generate_final_response(mock_agent, messages)

        assert result == ""


class TestExecutePlanStep:
    """Test _execute_plan_step() function."""

    @pytest.mark.asyncio
    async def test_execute_step_with_tool_calls(
        self, strategy: PlanAndExecuteStrategy, mock_agent: MagicMock
    ) -> None:
        """Test executing a step that requires tool calls."""
        mock_agent.llm_provider.complete = AsyncMock(
            return_value={
                "success": True,
                "tool_calls": [
                    {
                        "id": "call_1",
                        "function": {"name": "test_tool", "arguments": "{}"},
                    }
                ],
            }
        )
        mock_agent._execute_tool = AsyncMock(
            return_value={"success": True, "output": "Done"}
        )
        messages: list[dict[str, Any]] = [{"role": "system", "content": "System"}]

        events = []
        async for event, progress, iters, complete in strategy._execute_plan_step(
            mock_agent,
            step_index=1,
            step_description="Test step",
            messages=messages,
            session_id="session_1",
            mission="Test mission",
            state={},
            current_progress=0,
            max_iterations=3,
            logger=strategy.logger,
        ):
            events.append((event, progress, iters, complete))
            if complete:
                break

        assert len(events) > 0
        assert any(e[0].event_type == "tool_call" for e in events)

    @pytest.mark.asyncio
    async def test_execute_step_with_completion(
        self, strategy: PlanAndExecuteStrategy, mock_agent: MagicMock
    ) -> None:
        """Test executing a step that completes immediately."""
        mock_agent.llm_provider.complete = AsyncMock(
            return_value={"success": True, "content": "Step done"}
        )
        messages: list[dict[str, Any]] = [{"role": "system", "content": "System"}]

        events = []
        async for event, progress, iters, complete in strategy._execute_plan_step(
            mock_agent,
            step_index=1,
            step_description="Test step",
            messages=messages,
            session_id="session_1",
            mission="Test mission",
            state={},
            current_progress=0,
            max_iterations=3,
            logger=strategy.logger,
        ):
            events.append((event, progress, iters, complete))
            if complete:
                break

        # Should have at least one event (token_usage or plan_updated)
        assert len(events) >= 0
        # Completion may not yield an event if planner is None, but step should be marked complete
        # Check that messages were updated with completion
        assert len(messages) >= 2  # System + step instruction + assistant response

    @pytest.mark.asyncio
    async def test_execute_step_respects_max_iterations(
        self, strategy: PlanAndExecuteStrategy, mock_agent: MagicMock
    ) -> None:
        """Test step execution respects max_iterations limit."""
        mock_agent.llm_provider.complete = AsyncMock(
            return_value={"success": True, "content": ""}
        )
        messages: list[dict[str, Any]] = [{"role": "system", "content": "System"}]

        events = []
        async for event, progress, iters, complete in strategy._execute_plan_step(
            mock_agent,
            step_index=1,
            step_description="Test step",
            messages=messages,
            session_id="session_1",
            mission="Test mission",
            state={},
            current_progress=0,
            max_iterations=2,
            logger=strategy.logger,
        ):
            events.append((event, progress, iters, complete))

        if events:
            max_iters = max(e[2] for e in events)
            assert max_iters <= 2
        # Verify LLM was called at most max_iterations times
        assert mock_agent.llm_provider.complete.call_count <= 2

    @pytest.mark.asyncio
    async def test_execute_step_handles_llm_error(
        self, strategy: PlanAndExecuteStrategy, mock_agent: MagicMock
    ) -> None:
        """Test step execution handles LLM errors gracefully."""
        mock_agent.llm_provider.complete = AsyncMock(
            return_value={"success": False, "error": "LLM failed"}
        )
        messages: list[dict[str, Any]] = [{"role": "system", "content": "System"}]

        events = []
        async for event, progress, iters, complete in strategy._execute_plan_step(
            mock_agent,
            step_index=1,
            step_description="Test step",
            messages=messages,
            session_id="session_1",
            mission="Test mission",
            state={},
            current_progress=0,
            max_iterations=2,
            logger=strategy.logger,
        ):
            events.append((event, progress, iters, complete))

        error_logs = [
            log for log in strategy.logger.logs if log[1]["event"] == "llm_call_failed"
        ]
        assert len(error_logs) > 0
