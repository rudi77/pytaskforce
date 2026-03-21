"""
Unit Tests for Tool Converter

Tests the tool converter utilities including output truncation and compact format.
"""

import json

from taskforce.core.domain.tool_result import ToolResultHandle
from taskforce.core.tools.tool_converter import (
    _result_to_compact_text,
    _truncate_tool_result,
    assistant_tool_calls_to_message,
    create_tool_result_preview,
    tool_result_to_message,
)


# ---------------------------------------------------------------------------
# _result_to_compact_text
# ---------------------------------------------------------------------------


def test_compact_text_error_result():
    """Error results return 'ERROR: <message>' only."""
    result = {"success": False, "error": "File not found", "path": "/foo"}
    assert _result_to_compact_text(result) == "ERROR: File not found"


def test_compact_text_error_unknown():
    """Missing error key falls back to 'Unknown error'."""
    result = {"success": False}
    assert _result_to_compact_text(result) == "ERROR: Unknown error"


def test_compact_text_output_field():
    """Success with 'output' returns the output value directly."""
    result = {"success": True, "output": "Hello, world!", "path": "/foo", "size": 13}
    assert _result_to_compact_text(result) == "Hello, world!"


def test_compact_text_content_field():
    """'content' is used when 'output' is absent."""
    result = {"success": True, "content": "File data here"}
    assert _result_to_compact_text(result) == "File data here"


def test_compact_text_result_field():
    """'result' is used when 'output' and 'content' are absent."""
    result = {"success": True, "result": 42}
    assert _result_to_compact_text(result) == "42"


def test_compact_text_stdout_field():
    """'stdout' is used as last resort content key."""
    result = {"success": True, "stdout": "command output"}
    assert _result_to_compact_text(result) == "command output"


def test_compact_text_with_stderr():
    """stderr is appended when present."""
    result = {"success": True, "output": "ok", "stderr": "warning: deprecation"}
    text = _result_to_compact_text(result)
    assert text == "ok\n[stderr] warning: deprecation"


def test_compact_text_empty_stderr_ignored():
    """Empty/whitespace stderr is ignored."""
    result = {"success": True, "output": "ok", "stderr": "  "}
    assert _result_to_compact_text(result) == "ok"


def test_compact_text_fallback_json():
    """When no known content field exists, falls back to compact JSON."""
    result = {"success": True, "custom_field": "data"}
    text = _result_to_compact_text(result)
    parsed = json.loads(text)
    assert parsed["custom_field"] == "data"


def test_compact_text_structured_result():
    """Structured (dict/list) content fields are JSON-serialized."""
    result = {"success": True, "result": {"items": [1, 2, 3]}}
    text = _result_to_compact_text(result)
    parsed = json.loads(text)
    assert parsed["items"] == [1, 2, 3]


def test_compact_text_none_output_skipped():
    """None-valued content keys are skipped in priority scan."""
    result = {"success": True, "output": None, "content": "actual data"}
    assert _result_to_compact_text(result) == "actual data"


# ---------------------------------------------------------------------------
# tool_result_to_message (uses compact text now)
# ---------------------------------------------------------------------------


def test_tool_result_to_message_basic():
    """Test basic tool result conversion with compact format."""
    result = {"success": True, "output": "Hello, world!"}

    message = tool_result_to_message("call_123", "test_tool", result)

    assert message["role"] == "tool"
    assert message["tool_call_id"] == "call_123"
    assert message["name"] == "test_tool"
    # Content is now compact text, not JSON
    assert message["content"] == "Hello, world!"


def test_tool_result_to_message_error():
    """Error results produce ERROR: prefix."""
    result = {"success": False, "error": "Something broke"}
    message = tool_result_to_message("call_123", "test_tool", result)
    assert message["content"] == "ERROR: Something broke"


def test_tool_result_truncation_large_output():
    """Test that large outputs are truncated."""
    large_output = "x" * 30000
    result = {"success": True, "output": large_output}

    message = tool_result_to_message("call_123", "test_tool", result)

    # Output should be truncated (compact text = output value directly)
    assert len(message["content"]) < len(large_output)
    assert "TRUNCATED" in message["content"]
    assert message["content"].startswith("x" * 20000)


def test_tool_result_truncation_custom_limit():
    """Test truncation with custom limit."""
    large_output = "y" * 15000
    result = {"success": True, "output": large_output}

    message = tool_result_to_message("call_123", "test_tool", result, max_output_chars=10000)

    assert len(message["content"]) < len(large_output)
    assert "TRUNCATED" in message["content"]
    assert message["content"].startswith("y" * 10000)


def test_truncate_tool_result_multiple_fields():
    """Test truncation of multiple large fields."""
    result = {
        "success": True,
        "output": "o" * 25000,
        "stdout": "s" * 25000,
        "content": "c" * 25000,
    }

    truncated = _truncate_tool_result(result, max_chars=10000)

    assert "TRUNCATED" in truncated["output"]
    assert "TRUNCATED" in truncated["stdout"]
    assert "TRUNCATED" in truncated["content"]

    assert truncated["output"].startswith("o" * 10000)
    assert truncated["stdout"].startswith("s" * 10000)
    assert truncated["content"].startswith("c" * 10000)


def test_truncate_tool_result_preserves_small_fields():
    """Test that small fields are not truncated."""
    result = {
        "success": True,
        "output": "Small output",
        "error": None,
    }

    truncated = _truncate_tool_result(result, max_chars=10000)

    assert truncated["output"] == "Small output"
    assert truncated["error"] is None
    assert "TRUNCATED" not in str(truncated)


def test_truncate_tool_result_structured_data():
    """Test truncation of structured data (list/dict)."""
    large_list = [{"item": i, "data": "x" * 1000} for i in range(100)]
    result = {"success": True, "data": large_list}

    truncated = _truncate_tool_result(result, max_chars=5000)

    assert isinstance(truncated["data"], str)
    assert "TRUNCATED" in truncated["data"]


def test_assistant_tool_calls_to_message():
    """Test assistant message with tool calls."""
    tool_calls = [
        {
            "id": "call_1",
            "type": "function",
            "function": {"name": "test_tool", "arguments": '{"param": "value"}'},
        }
    ]

    message = assistant_tool_calls_to_message(tool_calls)

    assert message["role"] == "assistant"
    assert message["content"] is None
    assert message["tool_calls"] == tool_calls


def test_truncation_shows_overflow_size():
    """Test that truncation message shows how many chars were removed."""
    large_output = "z" * 25000
    result = {"success": True, "output": large_output}

    message = tool_result_to_message("call_123", "test_tool", result, max_output_chars=10000)

    assert "15000 more chars" in message["content"]


# ---------------------------------------------------------------------------
# create_tool_result_preview (improved format)
# ---------------------------------------------------------------------------


def test_preview_success_output():
    """Preview shows content directly, not 'Success: True | Output: ...'."""
    handle = ToolResultHandle(
        id="abc12345-0000-0000-0000-000000000000",
        tool="file_read",
        created_at="2024-01-01T00:00:00Z",
        size_bytes=5000,
        size_chars=5000,
    )
    result = {"success": True, "output": "File contents here"}
    preview = create_tool_result_preview(handle, result)

    assert "File contents here" in preview.preview_text
    # Should NOT contain the old format
    assert "Success:" not in preview.preview_text


def test_preview_error():
    """Error preview shows ERROR: prefix."""
    handle = ToolResultHandle(
        id="abc12345-0000-0000-0000-000000000000",
        tool="shell",
        created_at="2024-01-01T00:00:00Z",
        size_bytes=100,
        size_chars=100,
    )
    result = {"success": False, "error": "Command failed"}
    preview = create_tool_result_preview(handle, result)

    assert preview.preview_text.startswith("ERROR: Command failed")


def test_preview_large_result_shows_size_hint():
    """Large results get a size hint appended."""
    handle = ToolResultHandle(
        id="abc12345-0000-0000-0000-000000000000",
        tool="file_read",
        created_at="2024-01-01T00:00:00Z",
        size_bytes=10000,
        size_chars=10000,
    )
    result = {"success": True, "output": "x" * 10000}
    preview = create_tool_result_preview(handle, result, max_preview_chars=200)

    assert preview.truncated is True
    assert "10000 chars total" in preview.preview_text
    assert "abc12345" in preview.preview_text


def test_preview_small_result_no_size_hint():
    """Small results within preview limit don't get size hints."""
    handle = ToolResultHandle(
        id="abc12345-0000-0000-0000-000000000000",
        tool="file_read",
        created_at="2024-01-01T00:00:00Z",
        size_bytes=20,
        size_chars=20,
    )
    result = {"success": True, "output": "short"}
    preview = create_tool_result_preview(handle, result)

    assert preview.preview_text == "short"
    assert preview.truncated is False
