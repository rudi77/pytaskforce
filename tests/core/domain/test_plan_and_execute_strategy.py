"""
Unit Tests for PlanAndExecuteStrategy.

Tests the key functions:
- _parse_plan_steps() (parsing logic)
- _generate_final_response() (non-streaming final response for tests)
- execute_stream() integration behavior
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

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
    agent.record_heartbeat = AsyncMock()
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
        # Now correctly parses JSON without code blocks
        assert result == ["Step 1", "Step 2"]

    def test_parse_malformed_json_falls_back_to_lines(
        self, mock_logger: MockLogger
    ) -> None:
        """Test malformed JSON falls back to line-based parsing."""
        content = "```json\n{invalid json}\n```\n1. Step one\n2. Step two"
        result = _parse_plan_steps(content, mock_logger)
        assert len(result) >= 2
        assert any("Step one" in step for step in result)
        assert any("Step two" in step for step in result)

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


class TestStreamFinalResponse:
    """Test _stream_final_response() shared helper."""

    @pytest.mark.asyncio
    async def test_stream_final_response_success(
        self, mock_agent: MagicMock
    ) -> None:
        """Test successful final response generation via shared helper."""
        from taskforce.core.domain.enums import EventType
        from taskforce.core.domain.planning_strategy import _stream_final_response

        mock_agent.llm_provider.complete = AsyncMock(
            return_value={"success": True, "content": "Final summary"}
        )
        # Ensure non-streaming path is used
        if hasattr(mock_agent.llm_provider, "complete_stream"):
            del mock_agent.llm_provider.complete_stream

        messages: list[dict[str, Any]] = [{"role": "user", "content": "Mission"}]

        events = [e async for e in _stream_final_response(mock_agent, messages)]

        assert len(events) == 1
        assert events[0].event_type == EventType.FINAL_ANSWER
        assert events[0].data["content"] == "Final summary"
        assert len(messages) == 2
        assert "All steps complete" in messages[1]["content"]

    @pytest.mark.asyncio
    async def test_stream_final_response_failure(
        self, mock_agent: MagicMock
    ) -> None:
        """Test final response generation when LLM fails."""
        from taskforce.core.domain.enums import EventType
        from taskforce.core.domain.planning_strategy import _stream_final_response

        mock_agent.llm_provider.complete = AsyncMock(
            return_value={"success": False, "error": "LLM error"}
        )
        if hasattr(mock_agent.llm_provider, "complete_stream"):
            del mock_agent.llm_provider.complete_stream

        messages: list[dict[str, Any]] = []

        events = [e async for e in _stream_final_response(mock_agent, messages)]

        # Empty content → fallback "Plan completed." message
        assert len(events) == 1
        assert events[0].event_type == EventType.FINAL_ANSWER
        assert events[0].data["content"] == "Plan completed."

    @pytest.mark.asyncio
    async def test_stream_final_response_empty_content(
        self, mock_agent: MagicMock
    ) -> None:
        """Test final response generation with empty content."""
        from taskforce.core.domain.enums import EventType
        from taskforce.core.domain.planning_strategy import _stream_final_response

        mock_agent.llm_provider.complete = AsyncMock(
            return_value={"success": True, "content": ""}
        )
        if hasattr(mock_agent.llm_provider, "complete_stream"):
            del mock_agent.llm_provider.complete_stream

        messages: list[dict[str, Any]] = []

        events = [e async for e in _stream_final_response(mock_agent, messages)]

        assert len(events) == 1
        assert events[0].event_type == EventType.FINAL_ANSWER
        assert events[0].data["content"] == "Plan completed."


class TestStrategyParameters:
    """Test strategy initialization and parameters."""

    def test_default_parameters(self) -> None:
        """Test default strategy parameters."""
        strategy = PlanAndExecuteStrategy()
        assert strategy.max_step_iterations == 4
        assert strategy.max_plan_steps == 12
        assert strategy.logger is None

    def test_custom_parameters(self, mock_logger: MockLogger) -> None:
        """Test custom strategy parameters."""
        strategy = PlanAndExecuteStrategy(
            max_step_iterations=2,
            max_plan_steps=5,
            logger=mock_logger,
        )
        assert strategy.max_step_iterations == 2
        assert strategy.max_plan_steps == 5
        assert strategy.logger is mock_logger

    def test_strategy_name(self) -> None:
        """Test strategy name attribute."""
        strategy = PlanAndExecuteStrategy()
        assert strategy.name == "plan_and_execute"
