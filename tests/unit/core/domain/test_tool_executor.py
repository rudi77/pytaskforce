"""Tests for ToolExecutor and ToolResultMessageFactory.

Covers tool execution (success, error, not found), and message
construction for both standard and handle-based tool results.
"""

from __future__ import annotations

import json
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from taskforce.core.domain.lean_agent_components.tool_executor import (
    MAX_LOGGED_STRING_CHARS,
    ToolExecutor,
    ToolResultMessageFactory,
    _truncate_for_log,
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

    async def test_execution_logs_tool_name_and_full_args(self) -> None:
        """execute logs tool name and full argument values."""
        logger = _StubLogger()
        tool = _make_mock_tool("file_write", result={"success": True})
        executor = ToolExecutor(
            tools={"file_write": tool},
            logger=logger,
        )

        await executor.execute("file_write", {"path": "/tmp/out.txt", "content": "data"})

        execute_logs = [log for log in logger.logs if log[1].get("event") == "tool_execute"]
        assert len(execute_logs) == 1
        assert execute_logs[0][1]["tool"] == "file_write"
        # Full args (values), not just keys
        assert execute_logs[0][1]["args"] == {
            "path": "/tmp/out.txt",
            "content": "data",
        }

    async def test_execution_logs_completion_with_result(self) -> None:
        """execute logs tool_complete with full result dict on success."""
        logger = _StubLogger()
        tool = _make_mock_tool("my_tool", result={"success": True, "output": "done", "bytes": 42})
        executor = ToolExecutor(tools={"my_tool": tool}, logger=logger)

        await executor.execute("my_tool", {"input": "test"})

        complete_logs = [log for log in logger.logs if log[1].get("event") == "tool_complete"]
        assert len(complete_logs) == 1
        level, payload = complete_logs[0]
        assert level == "info"
        assert payload["success"] is True
        assert payload["result"] == {"success": True, "output": "done", "bytes": 42}

    async def test_failed_result_logs_warning_with_error_fields(self) -> None:
        """execute logs tool_complete at warning level with error/details on failure."""
        logger = _StubLogger()
        tool = _make_mock_tool(
            "powershell",
            result={
                "success": False,
                "error": "command exited with 1",
                "error_type": "ToolError",
                "details": {"stderr": "Get-Mailbox not recognized"},
            },
        )
        executor = ToolExecutor(tools={"powershell": tool}, logger=logger)

        await executor.execute("powershell", {"command": "Get-Mailbox"})

        complete_logs = [log for log in logger.logs if log[1].get("event") == "tool_complete"]
        assert len(complete_logs) == 1
        level, payload = complete_logs[0]
        assert level == "warning"
        assert payload["success"] is False
        assert payload["error"] == "command exited with 1"
        assert payload["error_type"] == "ToolError"
        assert payload["details"] == {"stderr": "Get-Mailbox not recognized"}

    async def test_exception_logs_error_with_args_and_type(self) -> None:
        """execute logs tool_exception with args and error_type on uncaught failure."""
        logger = _StubLogger()
        tool = _make_mock_tool(
            "failing_tool",
            side_effect=RuntimeError("Boom"),
        )
        executor = ToolExecutor(tools={"failing_tool": tool}, logger=logger)

        await executor.execute("failing_tool", {"input": "trigger"})

        error_logs = [log for log in logger.logs if log[1].get("event") == "tool_exception"]
        assert len(error_logs) == 1
        level, payload = error_logs[0]
        assert level == "error"
        assert "Boom" in payload["error"]
        assert payload["error_type"] == "RuntimeError"
        assert payload["args"] == {"input": "trigger"}

    async def test_long_string_values_are_truncated_in_args(self) -> None:
        """execute truncates long string values in logged args."""
        logger = _StubLogger()
        tool = _make_mock_tool("my_tool", result={"success": True})
        executor = ToolExecutor(tools={"my_tool": tool}, logger=logger)

        big = "A" * (MAX_LOGGED_STRING_CHARS + 500)
        await executor.execute("my_tool", {"blob": big})

        execute_logs = [log for log in logger.logs if log[1].get("event") == "tool_execute"]
        logged = execute_logs[0][1]["args"]["blob"]
        assert len(logged) < len(big)
        assert logged.startswith("A" * 100)
        assert "chars]" in logged

    async def test_long_string_values_are_truncated_in_result(self) -> None:
        """execute truncates long string values in logged result."""
        logger = _StubLogger()
        big = "B" * (MAX_LOGGED_STRING_CHARS + 500)
        tool = _make_mock_tool(
            "reader",
            result={"success": True, "output": big},
        )
        executor = ToolExecutor(tools={"reader": tool}, logger=logger)

        await executor.execute("reader", {"path": "x"})

        complete_logs = [log for log in logger.logs if log[1].get("event") == "tool_complete"]
        logged = complete_logs[0][1]["result"]["output"]
        assert len(logged) < len(big)
        assert "chars]" in logged


class TestTruncateForLog:
    """Unit tests for the truncation helper."""

    def test_short_string_unchanged(self) -> None:
        assert _truncate_for_log("hello") == "hello"

    def test_long_string_truncated_with_suffix(self) -> None:
        value = "x" * 5000
        out = _truncate_for_log(value, max_chars=100)
        assert out.startswith("x" * 100)
        assert out.endswith("chars]")
        assert len(out) < len(value)

    def test_nested_dict_truncation(self) -> None:
        payload = {"outer": {"inner": "y" * 5000}}
        out = _truncate_for_log(payload, max_chars=50)
        assert out["outer"]["inner"].startswith("y" * 50)
        assert "chars]" in out["outer"]["inner"]

    def test_list_values_truncated(self) -> None:
        out = _truncate_for_log(["a", "z" * 5000], max_chars=10)
        assert out[0] == "a"
        assert out[1].startswith("z" * 10)

    def test_non_string_passthrough(self) -> None:
        assert _truncate_for_log(42) == 42
        assert _truncate_for_log(None) is None
        assert _truncate_for_log(True) is True

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
        # Content is compact text (primary output value)
        assert result["content"] == "Hello"

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
        # Should still be the full result (compact text, truncated),
        # not a handle-based preview
        assert result["content"].startswith("x" * 100)

    async def test_handle_based_message_for_large_result(self) -> None:
        """Large results use the tool result store and expose fetch_result handle.

        Note: file_read results are never stored (to avoid infinite loops),
        so we use a different tool name here.
        """
        handle = _make_handle("handle-large-1", "shell")
        store = AsyncMock()
        store.put = AsyncMock(return_value=handle)
        store._result_path = MagicMock(return_value="/tmp/results/handle-large-1.json")

        factory = ToolResultMessageFactory(
            tool_result_store=store,
            result_store_threshold=100,  # Very low to trigger handle storage
            logger=_StubLogger(),
        )

        large_result = {"success": True, "output": "x" * 5000}
        result = await factory.build_message(
            tool_call_id="call_789",
            tool_name="shell",
            tool_result=large_result,
            session_id="session-1",
            step=3,
        )

        assert result["role"] == "tool"
        assert result["tool_call_id"] == "call_789"
        assert result["name"] == "shell"

        # Store should have been called
        store.put.assert_awaited_once()
        put_kwargs = store.put.call_args
        assert put_kwargs.kwargs["tool_name"] == "shell"

        # Content should contain an opaque fetch_result handle.
        content = json.loads(result["content"])
        assert "result_file" not in content
        assert content["truncated"] is True
        assert content["handle_id"] == "handle-large-1"
        assert "size_chars" in content
        assert "fetch_result" in content["message"]

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
        # Compact text: primary output value directly
        assert result["content"] == "small"

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
        store._result_path = MagicMock(return_value="/tmp/results/test.json")

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
        """Factory logs when storing result to file."""
        logger = _StubLogger()
        handle = _make_handle("logged-handle", "test_tool")
        store = AsyncMock()
        store.put = AsyncMock(return_value=handle)
        store._result_path = MagicMock(return_value="/tmp/results/logged-handle.json")

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

        file_logs = [
            log for log in logger.logs if log[1].get("event") == "tool_result_stored_to_file"
        ]
        assert len(file_logs) == 1
        assert file_logs[0][1]["file"] == "/tmp/results/logged-handle.json"


# ---------------------------------------------------------------------------
# Per-tool result_store_threshold override
# ---------------------------------------------------------------------------


class TestToolResultMessageFactoryPerToolThreshold:
    """A tool exposing ``tool_result_store_threshold`` overrides the global default."""

    @pytest.mark.spec("tools.tool_result_threshold_per_tool_overrides_profile")
    async def test_per_tool_override_triggers_storage_below_global(self) -> None:
        """Tool with low threshold stores results that the global default would inline."""
        handle = _make_handle("handle-pertool-1", "web_search")
        store = AsyncMock()
        store.put = AsyncMock(return_value=handle)
        store._result_path = MagicMock(return_value="/tmp/results/handle-pertool-1.json")

        # Tool exposes a threshold of 200 chars; global default is 5000.
        web_tool = MagicMock()
        web_tool.name = "web_search"
        web_tool.tool_result_store_threshold = 200

        factory = ToolResultMessageFactory(
            tool_result_store=store,
            result_store_threshold=5000,  # Global default — would inline a 1k payload.
            logger=_StubLogger(),
            tools={"web_search": web_tool},
        )

        result = await factory.build_message(
            tool_call_id="call_pt_1",
            tool_name="web_search",
            tool_result={"success": True, "results": [{"title": "x" * 800, "url": "u"}]},
            session_id="s1",
            step=1,
        )

        store.put.assert_awaited_once()
        content = json.loads(result["content"])
        assert "result_file" not in content
        assert content["truncated"] is True
        assert content["handle_id"] == "handle-pertool-1"
        assert "fetch_result" in content["message"]

    async def test_no_override_falls_back_to_global_default(self) -> None:
        """Tool without ``tool_result_store_threshold`` uses the global value."""
        store = AsyncMock()
        store.put = AsyncMock()

        plain_tool = MagicMock(spec=[])  # No tool_result_store_threshold attribute
        plain_tool.name = "plain"

        factory = ToolResultMessageFactory(
            tool_result_store=store,
            result_store_threshold=5000,
            logger=_StubLogger(),
            tools={"plain": plain_tool},
        )

        await factory.build_message(
            tool_call_id="call_plain",
            tool_name="plain",
            tool_result={"success": True, "output": "small"},
            session_id="s1",
            step=1,
        )

        store.put.assert_not_awaited()


# ---------------------------------------------------------------------------
# build_messages: multimodal follow-up for tools that return images
# ---------------------------------------------------------------------------


class TestToolResultMessageFactoryBuildMessages:
    """Tests for ToolResultMessageFactory.build_messages."""

    async def test_no_attachments_returns_single_message(self) -> None:
        """Without attachments, build_messages == [build_message]."""
        factory = ToolResultMessageFactory(
            tool_result_store=None,
            result_store_threshold=5000,
            logger=_StubLogger(),
        )

        msgs = await factory.build_messages(
            tool_call_id="call_1",
            tool_name="file_read",
            tool_result={"success": True, "output": "Hello"},
            session_id="s1",
            step=1,
        )

        assert len(msgs) == 1
        assert msgs[0]["role"] == "tool"
        assert msgs[0]["content"] == "Hello"

    async def test_image_attachment_appends_multimodal_user_message(self) -> None:
        """Image attachment -> follow-up user message with image_url block."""
        factory = ToolResultMessageFactory(
            tool_result_store=None,
            result_store_threshold=5000,
            logger=_StubLogger(),
        )

        data_url = "data:image/jpeg;base64,/9j/4AAQSkZJRg=="
        msgs = await factory.build_messages(
            tool_call_id="call_img",
            tool_name="multimedia",
            tool_result={
                "success": True,
                "output": "Loaded image: photo.jpg",
                "attachments": [{"type": "image", "mime_type": "image/jpeg", "data_url": data_url}],
            },
            session_id="s1",
            step=1,
        )

        assert len(msgs) == 2
        # Tool message: lean, NO base64 leakage
        assert msgs[0]["role"] == "tool"
        assert msgs[0]["content"] == "Loaded image: photo.jpg"
        assert data_url not in msgs[0]["content"]
        # Follow-up: user role, multimodal content list with image_url block
        assert msgs[1]["role"] == "user"
        assert isinstance(msgs[1]["content"], list)
        types = [part.get("type") for part in msgs[1]["content"]]
        assert "image_url" in types
        image_block = next(p for p in msgs[1]["content"] if p["type"] == "image_url")
        assert image_block["image_url"]["url"] == data_url

    async def test_attachments_stripped_before_storing(self) -> None:
        """Large result + attachments: persisted payload must not contain them."""
        handle = _make_handle("h1", "multimedia")
        store = AsyncMock()
        store.put = AsyncMock(return_value=handle)
        store._result_path = MagicMock(return_value="/tmp/results/h1.json")

        factory = ToolResultMessageFactory(
            tool_result_store=store,
            result_store_threshold=100,
            logger=_StubLogger(),
        )

        big_output = "summary " * 200
        msgs = await factory.build_messages(
            tool_call_id="call_big_img",
            tool_name="multimedia",
            tool_result={
                "success": True,
                "output": big_output,
                "attachments": [
                    {
                        "type": "image",
                        "mime_type": "image/png",
                        "data_url": "data:image/png;base64,AAAA",
                    }
                ],
            },
            session_id="s1",
            step=1,
        )

        assert len(msgs) == 2
        store.put.assert_awaited_once()
        stored_payload = store.put.call_args.kwargs["result"]
        assert "attachments" not in stored_payload, "attachments must be stripped before persisting"

    async def test_document_only_attachment_no_user_followup(self) -> None:
        """Document attachments (no image data_url) don't trigger a follow-up."""
        factory = ToolResultMessageFactory(
            tool_result_store=None,
            result_store_threshold=5000,
            logger=_StubLogger(),
        )

        msgs = await factory.build_messages(
            tool_call_id="call_doc",
            tool_name="multimedia",
            tool_result={
                "success": True,
                "output": "Loaded PDF",
                "attachments": [
                    {
                        "type": "document",
                        "file_path": "/tmp/foo.pdf",
                        "file_name": "foo.pdf",
                        "mime_type": "application/pdf",
                    }
                ],
            },
            session_id="s1",
            step=1,
        )

        assert len(msgs) == 1
        assert msgs[0]["role"] == "tool"
