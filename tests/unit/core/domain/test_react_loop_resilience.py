"""Tests for agent resilience after tool failures.

Covers:
- Retry nudge injection after tool failures in _react_loop
- No nudge when tools succeed
- Stall detection still triggers after repeated no-progress steps
- _build_retry_nudge helper output format
"""

from __future__ import annotations

import json
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from taskforce.core.domain.enums import EventType, MessageRole
from taskforce.core.domain.models import StreamEvent
from taskforce.core.domain.planning_helpers import (
    _build_retry_nudge,
    _react_loop,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_agent(
    max_steps: int = 10,
    max_parallel_tools: int = 1,
) -> MagicMock:
    """Create a minimal mock agent for _react_loop."""
    agent = MagicMock()
    agent.max_steps = max_steps
    agent.max_parallel_tools = max_parallel_tools
    agent._openai_tools = [{"type": "function", "function": {"name": "file_read"}}]
    agent._planner = None
    agent.planner = None
    agent.tools = {}
    agent.state_manager = AsyncMock()
    agent.state_store = AsyncMock()
    agent.record_heartbeat = AsyncMock()
    agent.message_history_manager = MagicMock()
    agent.message_history_manager.compress_messages = AsyncMock(side_effect=lambda m: m)
    agent.message_history_manager.preflight_budget_check = MagicMock(side_effect=lambda m: m)
    agent._build_system_prompt = MagicMock(return_value="system prompt")
    agent._truncate_output = MagicMock(side_effect=lambda x: x)
    agent._prompt_cache = None
    agent.tool_result_message_factory = AsyncMock()
    agent.tool_result_message_factory.build_message = AsyncMock(
        return_value={"role": "tool", "content": "result"}
    )
    agent._execute_tool = AsyncMock()
    agent.load_memory_context = AsyncMock()
    return agent


def _make_logger() -> MagicMock:
    """Create a minimal mock logger."""
    logger = MagicMock()
    logger.info = MagicMock()
    logger.warning = MagicMock()
    logger.debug = MagicMock()
    logger.error = MagicMock()
    return logger


# ---------------------------------------------------------------------------
# _build_retry_nudge tests
# ---------------------------------------------------------------------------


class TestBuildRetryNudge:
    def test_single_tool(self) -> None:
        nudge = _build_retry_nudge(["file_read"])
        assert nudge["role"] == MessageRole.USER.value
        assert "file_read failed" in nudge["content"]
        assert "Do NOT give up" in nudge["content"]
        assert "different tool" in nudge["content"]

    def test_multiple_tools(self) -> None:
        nudge = _build_retry_nudge(["file_read", "web_fetch"])
        assert "file_read, web_fetch" in nudge["content"]

    def test_deduplicates_tool_names(self) -> None:
        nudge = _build_retry_nudge(["file_read", "file_read", "file_read"])
        # Should only appear once in the tools string
        assert nudge["content"].count("file_read") == 1

    def test_suggests_alternatives(self) -> None:
        nudge = _build_retry_nudge(["file_read"])
        assert "python" in nudge["content"]


# ---------------------------------------------------------------------------
# _react_loop resilience tests
# ---------------------------------------------------------------------------


class TestReactLoopResilience:
    @pytest.mark.asyncio
    async def test_nudge_injected_after_tool_failure(self) -> None:
        """After a tool failure, a retry nudge message should be appended."""
        agent = _make_agent(max_steps=3)
        logger = _make_logger()

        # LLM call 1: returns a tool call
        # LLM call 2: returns final content (to end the loop)
        call_count = 0

        async def fake_complete(**kwargs: Any) -> dict[str, Any]:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return {
                    "success": True,
                    "tool_calls": [
                        {
                            "id": "tc_1",
                            "type": "function",
                            "function": {
                                "name": "file_read",
                                "arguments": json.dumps({"path": "test.pdf"}),
                            },
                        }
                    ],
                    "content": "",
                }
            return {
                "success": True,
                "tool_calls": None,
                "content": "Here is the result using python.",
            }

        agent.llm_provider = MagicMock()
        agent.llm_provider.complete = AsyncMock(side_effect=fake_complete)
        # No complete_stream => non-streaming path
        if hasattr(agent.llm_provider, "complete_stream"):
            del agent.llm_provider.complete_stream

        # Tool execution returns failure
        agent._execute_tool = AsyncMock(
            return_value={"success": False, "error": "UTF-8 decode error"}
        )

        messages: list[dict[str, Any]] = [
            {"role": "system", "content": "system prompt"},
            {"role": "user", "content": "Read test.pdf"},
        ]
        state: dict[str, Any] = {}

        events: list[StreamEvent] = []
        async for evt in _react_loop(
            agent, "Read test.pdf", "sess-1", messages, state, 0, logger
        ):
            events.append(evt)

        # Check that a retry nudge was injected into messages
        nudge_messages = [
            m
            for m in messages
            if m.get("role") == MessageRole.USER.value
            and "failed" in m.get("content", "")
            and "Do NOT give up" in m.get("content", "")
        ]
        assert len(nudge_messages) >= 1, "Expected at least one retry nudge message"
        assert "file_read" in nudge_messages[0]["content"]

    @pytest.mark.asyncio
    async def test_no_nudge_when_tools_succeed(self) -> None:
        """No retry nudge should be injected when all tools succeed."""
        agent = _make_agent(max_steps=3)
        logger = _make_logger()

        call_count = 0

        async def fake_complete(**kwargs: Any) -> dict[str, Any]:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return {
                    "success": True,
                    "tool_calls": [
                        {
                            "id": "tc_1",
                            "type": "function",
                            "function": {
                                "name": "file_read",
                                "arguments": json.dumps({"path": "test.txt"}),
                            },
                        }
                    ],
                    "content": "",
                }
            return {
                "success": True,
                "tool_calls": None,
                "content": "File contents: hello world",
            }

        agent.llm_provider = MagicMock()
        agent.llm_provider.complete = AsyncMock(side_effect=fake_complete)
        if hasattr(agent.llm_provider, "complete_stream"):
            del agent.llm_provider.complete_stream

        # Tool execution succeeds
        agent._execute_tool = AsyncMock(
            return_value={"success": True, "output": "hello world"}
        )

        messages: list[dict[str, Any]] = [
            {"role": "system", "content": "system prompt"},
            {"role": "user", "content": "Read test.txt"},
        ]
        state: dict[str, Any] = {}

        events: list[StreamEvent] = []
        async for evt in _react_loop(
            agent, "Read test.txt", "sess-2", messages, state, 0, logger
        ):
            events.append(evt)

        # No nudge messages should exist
        nudge_messages = [
            m
            for m in messages
            if m.get("role") == MessageRole.USER.value
            and "Do NOT give up" in m.get("content", "")
        ]
        assert len(nudge_messages) == 0, "No retry nudge expected when tools succeed"

    @pytest.mark.asyncio
    async def test_stall_detection_still_works(self) -> None:
        """Stall detection (3 consecutive no-progress) should still trigger."""
        agent = _make_agent(max_steps=10)
        logger = _make_logger()

        async def fake_complete(**kwargs: Any) -> dict[str, Any]:
            return {
                "success": True,
                "tool_calls": [
                    {
                        "id": "tc_1",
                        "type": "function",
                        "function": {
                            "name": "grep",
                            "arguments": json.dumps({"pattern": "nonexistent"}),
                        },
                    }
                ],
                "content": "",
            }

        agent.llm_provider = MagicMock()
        agent.llm_provider.complete = AsyncMock(side_effect=fake_complete)
        if hasattr(agent.llm_provider, "complete_stream"):
            del agent.llm_provider.complete_stream

        # Tool returns no-progress output (success but empty results)
        agent._execute_tool = AsyncMock(
            return_value={"success": True, "output": "0 matches in 5 files"}
        )

        messages: list[dict[str, Any]] = [
            {"role": "system", "content": "system prompt"},
            {"role": "user", "content": "Find something"},
        ]
        state: dict[str, Any] = {}

        events: list[StreamEvent] = []
        async for evt in _react_loop(
            agent, "Find something", "sess-3", messages, state, 0, logger
        ):
            events.append(evt)

        # Should have an error event about stalled execution
        error_events = [
            e for e in events if e.event_type == EventType.ERROR
        ]
        assert len(error_events) >= 1
        assert "stalled" in error_events[-1].data.get("message", "").lower()

        # Logger should have warned about stall
        logger.warning.assert_called()
