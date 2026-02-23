"""Tests for MessageHistoryManager.

Covers build_initial_messages, preflight_budget_check, compress_messages,
deterministic_compression, and build_safe_summary_input.
"""

from __future__ import annotations

import json
from typing import Any
from unittest.mock import AsyncMock

from taskforce.core.domain.lean_agent_components.message_history_manager import (
    MessageHistoryManager,
)
from taskforce.core.domain.token_budgeter import TokenBudgeter

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


class _StubLogger:
    """Minimal logger satisfying LoggerProtocol."""

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


def _make_llm_provider(
    success: bool = True, content: str = "Summary of conversation."
) -> AsyncMock:
    """Create a mock LLMProviderProtocol."""
    provider = AsyncMock()
    provider.complete = AsyncMock(
        return_value={
            "success": success,
            "content": content,
            "error": "" if success else "LLM failure",
            "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
        }
    )
    return provider


def _make_manager(
    *,
    max_input_tokens: int = 100_000,
    compression_trigger: int = 80_000,
    summary_threshold: int = 20,
    llm_provider: Any = None,
    logger: Any = None,
) -> MessageHistoryManager:
    """Create a MessageHistoryManager with configurable defaults."""
    log = logger or _StubLogger()
    budgeter = TokenBudgeter(
        logger=log,
        max_input_tokens=max_input_tokens,
        compression_trigger=compression_trigger,
    )
    return MessageHistoryManager(
        token_budgeter=budgeter,
        openai_tools=[],
        llm_provider=llm_provider or _make_llm_provider(),
        model_alias="main",
        summary_threshold=summary_threshold,
        logger=log,
    )


def _system_msg(content: str = "System prompt") -> dict[str, Any]:
    return {"role": "system", "content": content}


def _user_msg(content: str = "Hello") -> dict[str, Any]:
    return {"role": "user", "content": content}


def _assistant_msg(content: str = "Hi there") -> dict[str, Any]:
    return {"role": "assistant", "content": content}


def _tool_call_msg(tool_call_id: str, tool_name: str = "test_tool") -> dict[str, Any]:
    return {
        "role": "assistant",
        "content": None,
        "tool_calls": [
            {
                "id": tool_call_id,
                "type": "function",
                "function": {"name": tool_name, "arguments": "{}"},
            }
        ],
    }


def _tool_result_msg(
    tool_call_id: str, tool_name: str = "test_tool", content: str = '{"success": true}'
) -> dict[str, Any]:
    return {
        "role": "tool",
        "tool_call_id": tool_call_id,
        "name": tool_name,
        "content": content,
    }


# ---------------------------------------------------------------------------
# build_initial_messages Tests
# ---------------------------------------------------------------------------


class TestBuildInitialMessages:
    """Tests for MessageHistoryManager.build_initial_messages."""

    def test_basic_message_structure(self) -> None:
        """Returns system prompt + user message."""
        mgr = _make_manager()
        messages = mgr.build_initial_messages(
            mission="Do something",
            state={},
            base_system_prompt="You are an agent.",
        )
        assert len(messages) == 2
        assert messages[0] == {"role": "system", "content": "You are an agent."}
        assert messages[1]["role"] == "user"
        assert "Do something" in messages[1]["content"]

    def test_includes_conversation_history(self) -> None:
        """Conversation history from state is included."""
        mgr = _make_manager()
        state = {
            "conversation_history": [
                {"role": "user", "content": "Previous question"},
                {"role": "assistant", "content": "Previous answer"},
            ]
        }
        messages = mgr.build_initial_messages(
            mission="New question",
            state=state,
            base_system_prompt="System",
        )
        # system + 2 history + user
        assert len(messages) == 4
        assert messages[1]["content"] == "Previous question"
        assert messages[2]["content"] == "Previous answer"
        assert "New question" in messages[3]["content"]

    def test_filters_invalid_history_messages(self) -> None:
        """History entries without valid role/content are skipped."""
        mgr = _make_manager()
        state = {
            "conversation_history": [
                {"role": "user", "content": "Valid"},
                {"role": "tool", "content": "Tool result"},  # Not user/assistant
                {"role": "user", "content": ""},  # Empty content
                {"role": "assistant", "content": "Also valid"},
            ]
        }
        messages = mgr.build_initial_messages(
            mission="Task", state=state, base_system_prompt="Sys"
        )
        # system + 2 valid history msgs + user = 4
        assert len(messages) == 4

    def test_includes_user_answers(self) -> None:
        """User-provided answers from state are appended to user message."""
        mgr = _make_manager()
        state = {
            "answers": {"project_name": "myapp", "language": "python"}
        }
        messages = mgr.build_initial_messages(
            mission="Build it", state=state, base_system_prompt="Sys"
        )
        user_content = messages[-1]["content"]
        assert "User Provided Information" in user_content
        assert "myapp" in user_content

    def test_empty_state(self) -> None:
        """Works correctly with empty state dict."""
        mgr = _make_manager()
        messages = mgr.build_initial_messages(
            mission="Test", state={}, base_system_prompt="Sys"
        )
        assert len(messages) == 2


# ---------------------------------------------------------------------------
# preflight_budget_check Tests
# ---------------------------------------------------------------------------


class TestPreflightBudgetCheck:
    """Tests for MessageHistoryManager.preflight_budget_check."""

    def test_under_budget_returns_unchanged(self) -> None:
        """Messages under budget are returned unchanged."""
        mgr = _make_manager(max_input_tokens=100_000)
        messages = [_system_msg(), _user_msg("Hello")]
        result = mgr.preflight_budget_check(messages)
        assert result == messages

    def test_over_budget_sanitizes_and_truncates(self) -> None:
        """Messages over budget are sanitized and possibly truncated."""
        # Create a manager with a very small token budget
        mgr = _make_manager(max_input_tokens=50)

        # Create messages that exceed the tiny budget
        messages = [_system_msg()]
        for i in range(30):
            messages.append(_user_msg(f"Message {i} " + "x" * 500))
            messages.append(_assistant_msg(f"Response {i} " + "y" * 500))

        result = mgr.preflight_budget_check(messages)
        # Should have fewer messages than the original
        assert len(result) < len(messages)
        # First message should still be the system prompt
        assert result[0]["role"] == "system"

    def test_over_budget_emergency_truncation_keeps_recent(self) -> None:
        """Emergency truncation keeps the most recent messages."""
        mgr = _make_manager(max_input_tokens=10)
        messages = [_system_msg()]
        for i in range(20):
            messages.append(_user_msg(f"Old msg {i} " + "x" * 1000))

        result = mgr.preflight_budget_check(messages)
        # Should be drastically reduced
        assert len(result) <= 12  # system + up to ~10 recent + maybe summary


# ---------------------------------------------------------------------------
# compress_messages Tests
# ---------------------------------------------------------------------------


class TestCompressMessages:
    """Tests for MessageHistoryManager.compress_messages."""

    async def test_no_compression_when_under_threshold(self) -> None:
        """Messages below threshold are returned unchanged."""
        mgr = _make_manager(summary_threshold=20, compression_trigger=80_000)
        messages = [_system_msg(), _user_msg("Hello"), _assistant_msg("Hi")]
        result = await mgr.compress_messages(messages)
        assert result == messages

    async def test_compression_triggered_by_message_count(self) -> None:
        """Compression happens when message count exceeds threshold."""
        llm = _make_llm_provider(success=True, content="Conversation summary.")
        mgr = _make_manager(summary_threshold=5, llm_provider=llm)

        messages = [_system_msg()]
        for i in range(10):
            messages.append(_user_msg(f"msg {i}"))
            messages.append(_assistant_msg(f"resp {i}"))

        result = await mgr.compress_messages(messages)
        # Should have fewer messages with a summary injected
        assert len(result) < len(messages)
        # Should include a summary message
        has_summary = any(
            "Previous Context Summary" in (m.get("content") or "")
            for m in result
        )
        assert has_summary
        llm.complete.assert_awaited_once()

    async def test_compression_triggered_by_token_budget(self) -> None:
        """Compression happens when token budget is exceeded."""
        llm = _make_llm_provider(success=True, content="Budget-triggered summary.")
        mgr = _make_manager(
            compression_trigger=100,  # Very low trigger
            summary_threshold=100,  # High count threshold so only budget triggers
            llm_provider=llm,
        )

        messages = [_system_msg()]
        for i in range(15):
            messages.append(_user_msg(f"message {i} " + "x" * 200))
            messages.append(_assistant_msg(f"response {i} " + "y" * 200))

        result = await mgr.compress_messages(messages)
        assert len(result) < len(messages)

    async def test_compression_fallback_on_llm_failure(self) -> None:
        """Falls back to deterministic compression when LLM fails."""
        llm = _make_llm_provider(success=False, content="")
        mgr = _make_manager(summary_threshold=5, llm_provider=llm)

        messages = [_system_msg()]
        for i in range(10):
            messages.append(_user_msg(f"msg {i}"))
            messages.append(_assistant_msg(f"resp {i}"))

        result = await mgr.compress_messages(messages)
        # Should still produce compressed output (deterministic fallback)
        assert len(result) < len(messages)

    async def test_compression_fallback_on_llm_exception(self) -> None:
        """Falls back to deterministic compression when LLM raises."""
        llm = AsyncMock()
        llm.complete = AsyncMock(side_effect=RuntimeError("LLM crashed"))
        mgr = _make_manager(summary_threshold=5, llm_provider=llm)

        messages = [_system_msg()]
        for i in range(10):
            messages.append(_user_msg(f"msg {i}"))
            messages.append(_assistant_msg(f"resp {i}"))

        result = await mgr.compress_messages(messages)
        assert len(result) < len(messages)

    async def test_compression_fallback_on_context_length_error(self) -> None:
        """Falls back when LLM returns context length exceeded error."""
        llm = _make_llm_provider(success=True, content="")
        llm.complete = AsyncMock(
            return_value={
                "success": False,
                "content": "",
                "error": "This request exceeds the context length limit",
            }
        )
        mgr = _make_manager(summary_threshold=5, llm_provider=llm)

        # Need enough messages so deterministic compression actually drops some
        # (it keeps system + summary + last ~10 messages)
        messages = [_system_msg()]
        for i in range(25):
            messages.append(_user_msg(f"msg {i}"))

        result = await mgr.compress_messages(messages)
        assert len(result) < len(messages)


# ---------------------------------------------------------------------------
# deterministic_compression Tests
# ---------------------------------------------------------------------------


class TestDeterministicCompression:
    """Tests for MessageHistoryManager.deterministic_compression."""

    def test_preserves_system_prompt(self) -> None:
        """System prompt is always preserved as first message."""
        mgr = _make_manager()
        messages = [_system_msg("Important system context")]
        for i in range(20):
            messages.append(_user_msg(f"msg {i}"))

        result = mgr.deterministic_compression(messages)
        assert result[0]["role"] == "system"
        assert result[0]["content"] == "Important system context"

    def test_keeps_recent_messages(self) -> None:
        """Keeps the most recent messages after compression."""
        mgr = _make_manager()
        messages = [_system_msg()]
        for i in range(30):
            messages.append(_user_msg(f"msg_{i}"))

        result = mgr.deterministic_compression(messages)
        # Should keep system + summary + recent messages
        assert len(result) <= 13  # system + summary + up to ~10 recent
        # Last message should be the most recent one
        assert "msg_29" in result[-1]["content"]

    def test_adds_dropped_count_summary(self) -> None:
        """Adds a summary message indicating how many messages were dropped."""
        mgr = _make_manager()
        messages = [_system_msg()]
        for i in range(25):
            messages.append(_user_msg(f"msg {i}"))

        result = mgr.deterministic_compression(messages)
        # Should have a compression summary message
        has_compression_note = any(
            "compressed" in (m.get("content") or "").lower()
            for m in result
            if m.get("role") == "system" and m != result[0]
        )
        assert has_compression_note

    def test_empty_messages_handled(self) -> None:
        """Empty message list is handled gracefully."""
        mgr = _make_manager()
        result = mgr.deterministic_compression([])
        assert result[0]["role"] == "system"

    def test_preserves_tool_call_pairs(self) -> None:
        """Tool call + tool result pairs are preserved together."""
        mgr = _make_manager()
        messages = [_system_msg()]
        # Old filler messages
        for i in range(20):
            messages.append(_user_msg(f"old_{i}"))

        # Tool call pair near the end
        tool_call_id = "call_abc"
        messages.append(_tool_call_msg(tool_call_id, "my_tool"))
        messages.append(_tool_result_msg(tool_call_id, "my_tool"))
        messages.append(_user_msg("final message"))

        result = mgr.deterministic_compression(messages)

        # If tool result is present, the matching tool call must be present
        tool_msgs = [m for m in result if m.get("role") == "tool"]
        for tm in tool_msgs:
            tid = tm.get("tool_call_id")
            assert any(
                m.get("role") == "assistant"
                and any(tc.get("id") == tid for tc in (m.get("tool_calls") or []))
                for m in result
            ), f"Orphan tool message found for tool_call_id={tid}"


# ---------------------------------------------------------------------------
# build_safe_summary_input Tests
# ---------------------------------------------------------------------------


class TestBuildSafeSummaryInput:
    """Tests for MessageHistoryManager.build_safe_summary_input."""

    def test_formats_user_messages(self) -> None:
        """User messages are included with content preview."""
        mgr = _make_manager()
        messages = [_user_msg("Hello world")]
        result = mgr.build_safe_summary_input(messages)
        assert "Message 1 - user" in result
        assert "Hello world" in result

    def test_formats_tool_messages(self) -> None:
        """Tool messages are formatted with tool name and result preview."""
        mgr = _make_manager()
        messages = [
            _tool_result_msg("call_1", "file_read", json.dumps({"success": True, "output": "contents"}))
        ]
        result = mgr.build_safe_summary_input(messages)
        assert "Message 1 - tool" in result
        assert "file_read" in result

    def test_formats_assistant_messages_with_tool_calls(self) -> None:
        """Assistant messages with tool_calls show tool names."""
        mgr = _make_manager()
        messages = [_tool_call_msg("call_1", "file_read")]
        result = mgr.build_safe_summary_input(messages)
        assert "Message 1 - assistant" in result
        assert "file_read" in result

    def test_handles_non_json_tool_content(self) -> None:
        """Non-JSON tool content is handled gracefully."""
        mgr = _make_manager()
        messages = [
            {
                "role": "tool",
                "tool_call_id": "call_1",
                "name": "my_tool",
                "content": "plain text result",
            }
        ]
        result = mgr.build_safe_summary_input(messages)
        assert "plain text result" in result

    def test_empty_messages(self) -> None:
        """Empty message list returns empty string."""
        mgr = _make_manager()
        result = mgr.build_safe_summary_input([])
        assert result == ""

    def test_multiple_messages_separated(self) -> None:
        """Multiple messages are separated in the output."""
        mgr = _make_manager()
        messages = [_user_msg("First"), _assistant_msg("Second")]
        result = mgr.build_safe_summary_input(messages)
        assert "Message 1" in result
        assert "Message 2" in result
