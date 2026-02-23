"""Tests for ToolExecutor and ToolResultMessageFactory.

Covers tool execution (success, error, not found), and message
construction for both standard and handle-based tool results.
"""

from __future__ import annotations

import json
from typing import Any
from unittest.mock import AsyncMock, MagicMock

from taskforce.core.domain.lean_agent_components.tool_executor import (
    ToolExecutor,
    ToolResultMessageFactory,
)
from taskforce.core.domain.tool_result import ToolResultHandle

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


def _make_mock_tool(
    name: str = "test_tool",
    result: dict[str, Any] | None = None,
    side_effect: Exception | None = None,
) -> MagicMock:
    """Create a mock tool with configurable execute behavior."""
    tool = MagicMock()
    tool.name = name
    tool.description = f"Description for {name}"
    tool.parameters_schema = {
        "type": "object",
        "properties": {"input": {"type": "string"}},
    }
    if side_effect:
        tool.execute = AsyncMock(side_effect=side_effect)
    else:
        tool.execute = AsyncMock(return_value=result or {"success": True, "output": "ok"})
    return tool


def _make_executor(tools: list[MagicMock] | None = None) -> ToolExecutor:
    """Create a ToolExecutor with optional tools."""
    if tools is None:
        tools = [_make_mock_tool()]
    tools_dict = {t.name: t for t in tools}
    return ToolExecutor(tools=tools_dict, logger=_StubLogger())


def _make_handle(
    handle_id: str = "handle-001",
    tool_name: str = "test_tool",
) -> ToolResultHandle:
    """Create a ToolResultHandle for testing."""
    return ToolResultHandle(
        id=handle_id,
        tool=tool_name,
        created_at="2026-02-23T00:00:00Z",
        size_bytes=10000,
        size_chars=8000,
    )


# ---------------------------------------------------------------------------
# ToolExecutor Tests
# ---------------------------------------------------------------------------


class TestToolExecutorGetTool:
    """Tests for ToolExecutor.get_tool."""

    def test_returns_tool_by_name(self) -> None:
        """get_tool returns the tool when found."""
        tool = _make_mock_tool("file_read")
        executor = _make_executor(tools=[tool])
        result = executor.get_tool("file_read")
        assert result is tool

    def test_returns_none_for_unknown_tool(self) -> None:
        """get_tool returns None for unregistered tool name."""
        executor = _make_executor(tools=[_make_mock_tool("file_read")])
        result = executor.get_tool("nonexistent")
        assert result is None


class TestToolExecutorExecute:
    """Tests for ToolExecutor.execute."""

    async def test_successful_execution(self) -> None:
        """execute returns the tool result on success."""
        tool = _make_mock_tool(
            "file_read",
            result={"success": True, "output": "file contents"},
        )
        executor = _make_executor(tools=[tool])

        result = await executor.execute("file_read", {"path": "/tmp/test.txt"})

        assert result["success"] is True
        assert result["output"] == "file contents"
        tool.execute.assert_awaited_once_with(path="/tmp/test.txt")

    async def test_tool_not_found_returns_error(self) -> None:
        """execute returns error dict when tool is not found."""
        executor = _make_executor(tools=[_make_mock_tool("other_tool")])

        result = await executor.execute("nonexistent", {"param": "value"})

        assert result["success"] is False
        assert "not found" in result["error"].lower()
        assert "nonexistent" in result["error"]

    async def test_tool_exception_returns_error(self) -> None:
        """execute catches exceptions and returns error dict."""
        tool = _make_mock_tool(
            "broken_tool",
            side_effect=ValueError("Something went wrong"),
        )
        executor = _make_executor(tools=[tool])

        result = await executor.execute("broken_tool", {"input": "test"})

        assert result["success"] is False
        assert "Something went wrong" in result["error"]

    async def test_execution_logs_tool_name_and_args(self) -> None:
        """execute logs tool name and arg keys."""
        logger = _StubLogger()
        tool = _make_mock_tool("file_write", result={"success": True})
        executor = ToolExecutor(
            tools={"file_write": tool},
            logger=logger,
        )

        await executor.execute("file_write", {"path": "/tmp/out.txt", "content": "data"})

        # Should log tool_execute with tool name and args keys
        execute_logs = [
            log for log in logger.logs if log[1].get("event") == "tool_execute"
        ]
        assert len(execute_logs) == 1
        assert execute_logs[0][1]["tool"] == "file_write"
        assert set(execute_logs[0][1]["args_keys"]) == {"path", "content"}

    async def test_execution_logs_completion(self) -> None:
        """execute logs tool_complete after successful execution."""
        logger = _StubLogger()
        tool = _make_mock_tool("my_tool", result={"success": True})
        executor = ToolExecutor(tools={"my_tool": tool}, logger=logger)

        await executor.execute("my_tool", {"input": "test"})

        complete_logs = [
            log for log in logger.logs if log[1].get("event") == "tool_complete"
        ]
        assert len(complete_logs) == 1
        assert complete_logs[0][1]["success"] is True

    async def test_exception_logs_error(self) -> None:
        """execute logs tool_exception on failure."""
        logger = _StubLogger()
        tool = _make_mock_tool(
            "failing_tool",
            side_effect=RuntimeError("Boom"),
        )
        executor = ToolExecutor(tools={"failing_tool": tool}, logger=logger)

        await executor.execute("failing_tool", {})

        error_logs = [
            log for log in logger.logs if log[1].get("event") == "tool_exception"
        ]
        assert len(error_logs) == 1
        assert "Boom" in error_logs[0][1]["error"]

    async def test_multiple_tools(self) -> None:
        """Executor can handle multiple registered tools."""
        tool_a = _make_mock_tool("tool_a", result={"success": True, "output": "A"})
        tool_b = _make_mock_tool("tool_b", result={"success": True, "output": "B"})
        executor = _make_executor(tools=[tool_a, tool_b])

        result_a = await executor.execute("tool_a", {})
        result_b = await executor.execute("tool_b", {})

        assert result_a["output"] == "A"
        assert result_b["output"] == "B"

    async def test_empty_args(self) -> None:
        """execute handles empty args dict."""
        tool = _make_mock_tool("no_args_tool", result={"success": True})
        executor = _make_executor(tools=[tool])

        result = await executor.execute("no_args_tool", {})

        assert result["success"] is True
        tool.execute.assert_awaited_once_with()


# ---------------------------------------------------------------------------
# ToolResultMessageFactory Tests
# ---------------------------------------------------------------------------


class TestToolResultMessageFactoryBuildMessage:
    """Tests for ToolResultMessageFactory.build_message."""

    async def test_standard_message_for_small_result(self) -> None:
        """Small results produce standard tool messages (no handle)."""
        factory = ToolResultMessageFactory(
            tool_result_store=None,
            result_store_threshold=5000,
            logger=_StubLogger(),
        )

        result = await factory.build_message(
            tool_call_id="call_123",
            tool_name="file_read",
            tool_result={"success": True, "output": "Hello"},
            session_id="session-1",
            step=1,
        )

        assert result["role"] == "tool"
        assert result["tool_call_id"] == "call_123"
        assert result["name"] == "file_read"
        # Content should be JSON string of the result
        content = json.loads(result["content"])
        assert content["success"] is True
        assert content["output"] == "Hello"

    async def test_standard_message_without_store(self) -> None:
        """Without tool_result_store, always returns standard message."""
        factory = ToolResultMessageFactory(
            tool_result_store=None,
            result_store_threshold=10,  # Very low threshold
            logger=_StubLogger(),
        )

        large_result = {"success": True, "output": "x" * 10000}
        result = await factory.build_message(
            tool_call_id="call_456",
            tool_name="file_read",
            tool_result=large_result,
            session_id="session-1",
            step=2,
        )

        assert result["role"] == "tool"
        # Should still be the full result (truncated by tool_result_to_message),
        # not a handle-based preview
        content = json.loads(result["content"])
        assert content["success"] is True

    async def test_handle_based_message_for_large_result(self) -> None:
        """Large results use the tool result store and produce handle+preview."""
        handle = _make_handle("handle-large-1", "file_read")
        store = AsyncMock()
        store.put = AsyncMock(return_value=handle)

        factory = ToolResultMessageFactory(
            tool_result_store=store,
            result_store_threshold=100,  # Very low to trigger handle storage
            logger=_StubLogger(),
        )

        large_result = {"success": True, "output": "x" * 5000}
        result = await factory.build_message(
            tool_call_id="call_789",
            tool_name="file_read",
            tool_result=large_result,
            session_id="session-1",
            step=3,
        )

        assert result["role"] == "tool"
        assert result["tool_call_id"] == "call_789"
        assert result["name"] == "file_read"

        # Store should have been called
        store.put.assert_awaited_once()
        put_kwargs = store.put.call_args
        assert put_kwargs.kwargs["tool_name"] == "file_read"

        # Content should contain handle and preview
        content = json.loads(result["content"])
        assert "handle" in content
        assert "preview_text" in content
        assert content["handle"]["id"] == "handle-large-1"

    async def test_store_not_used_for_small_result(self) -> None:
        """Store is not called when result is below threshold."""
        store = AsyncMock()
        factory = ToolResultMessageFactory(
            tool_result_store=store,
            result_store_threshold=5000,
            logger=_StubLogger(),
        )

        small_result = {"success": True, "output": "small"}
        result = await factory.build_message(
            tool_call_id="call_small",
            tool_name="test_tool",
            tool_result=small_result,
            session_id="session-1",
            step=1,
        )

        store.put.assert_not_awaited()
        content = json.loads(result["content"])
        assert content["output"] == "small"

    async def test_message_includes_correct_tool_call_id(self) -> None:
        """The returned message always includes the correct tool_call_id."""
        factory = ToolResultMessageFactory(
            tool_result_store=None,
            result_store_threshold=5000,
            logger=_StubLogger(),
        )

        result = await factory.build_message(
            tool_call_id="unique-call-id-xyz",
            tool_name="shell",
            tool_result={"success": True, "output": "done"},
            session_id="s1",
            step=5,
        )

        assert result["tool_call_id"] == "unique-call-id-xyz"

    async def test_store_receives_metadata(self) -> None:
        """Store.put receives step and success metadata."""
        handle = _make_handle()
        store = AsyncMock()
        store.put = AsyncMock(return_value=handle)

        factory = ToolResultMessageFactory(
            tool_result_store=store,
            result_store_threshold=10,
            logger=_StubLogger(),
        )

        await factory.build_message(
            tool_call_id="call_meta",
            tool_name="test_tool",
            tool_result={"success": True, "output": "x" * 1000},
            session_id="session-meta",
            step=7,
        )

        put_call = store.put.call_args
        assert put_call.kwargs["session_id"] == "session-meta"
        assert put_call.kwargs["metadata"]["step"] == 7
        assert put_call.kwargs["metadata"]["success"] is True

    async def test_logs_handle_storage(self) -> None:
        """Factory logs when storing result with handle."""
        logger = _StubLogger()
        handle = _make_handle("logged-handle", "test_tool")
        store = AsyncMock()
        store.put = AsyncMock(return_value=handle)

        factory = ToolResultMessageFactory(
            tool_result_store=store,
            result_store_threshold=10,
            logger=logger,
        )

        await factory.build_message(
            tool_call_id="call_log",
            tool_name="test_tool",
            tool_result={"success": True, "output": "x" * 1000},
            session_id="s1",
            step=1,
        )

        handle_logs = [
            log
            for log in logger.logs
            if log[1].get("event") == "tool_result_stored_with_handle"
        ]
        assert len(handle_logs) == 1
        assert handle_logs[0][1]["handle_id"] == "logged-handle"
