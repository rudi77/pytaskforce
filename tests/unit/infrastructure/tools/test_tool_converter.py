"""
Unit Tests for Tool Converter

Tests the tool converter utilities including output truncation.
"""

import json

from taskforce.infrastructure.tools.tool_converter import (
    _truncate_tool_result,
    assistant_tool_calls_to_message,
    tool_result_to_message,
    tools_to_openai_format,
)


def test_tool_result_to_message_basic():
    """Test basic tool result conversion."""
    result = {"success": True, "output": "Hello, world!"}

    message = tool_result_to_message("call_123", "test_tool", result)

    assert message["role"] == "tool"
    assert message["tool_call_id"] == "call_123"
    assert message["name"] == "test_tool"

    # Content should be JSON string
    content = json.loads(message["content"])
    assert content["success"] is True
    assert content["output"] == "Hello, world!"


def test_tool_result_truncation_large_output():
    """Test that large outputs are truncated."""
    # Create output larger than default 20k chars
    large_output = "x" * 30000

    result = {"success": True, "output": large_output}

    message = tool_result_to_message("call_123", "test_tool", result)

    content = json.loads(message["content"])

    # Output should be truncated
    assert len(content["output"]) < len(large_output)
    assert "TRUNCATED" in content["output"]
    assert content["output"].startswith("x" * 20000)


def test_tool_result_truncation_custom_limit():
    """Test truncation with custom limit."""
    large_output = "y" * 15000

    result = {"success": True, "output": large_output}

    # Use custom limit of 10k
    message = tool_result_to_message(
        "call_123", "test_tool", result, max_output_chars=10000
    )

    content = json.loads(message["content"])

    # Output should be truncated at 10k
    assert len(content["output"]) < len(large_output)
    assert "TRUNCATED" in content["output"]
    assert content["output"].startswith("y" * 10000)


def test_truncate_tool_result_multiple_fields():
    """Test truncation of multiple large fields."""
    result = {
        "success": True,
        "output": "o" * 25000,
        "stdout": "s" * 25000,
        "content": "c" * 25000,
    }

    truncated = _truncate_tool_result(result, max_chars=10000)

    # All large fields should be truncated
    assert "TRUNCATED" in truncated["output"]
    assert "TRUNCATED" in truncated["stdout"]
    assert "TRUNCATED" in truncated["content"]

    # Each should be truncated to max_chars
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

    # Small fields should be unchanged
    assert truncated["output"] == "Small output"
    assert truncated["error"] is None
    assert "TRUNCATED" not in str(truncated)


def test_truncate_tool_result_structured_data():
    """Test truncation of structured data (list/dict)."""
    # Create large list
    large_list = [{"item": i, "data": "x" * 1000} for i in range(100)]

    result = {"success": True, "data": large_list}

    truncated = _truncate_tool_result(result, max_chars=5000)

    # Structured data should be converted to JSON and truncated
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

    message = tool_result_to_message(
        "call_123", "test_tool", result, max_output_chars=10000
    )

    content = json.loads(message["content"])

    # Should show overflow amount
    assert "15000 more chars" in content["output"]

