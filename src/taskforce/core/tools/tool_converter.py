"""
Tool Converter - OpenAI function calling format conversion.

This module provides utilities for converting internal tool definitions
to the format required by OpenAI's native function calling API.

It also provides functions for creating lightweight handle+preview pairs
from large tool results to keep message history small.
"""

import json
from typing import Any

from taskforce.core.domain.tool_result import (
    ToolResultHandle,
    ToolResultPreview,
)
from taskforce.core.interfaces.tools import ToolProtocol


def tools_to_openai_format(
    tools: dict[str, ToolProtocol],
) -> list[dict[str, Any]]:
    """
    Convert internal tool definitions to OpenAI function calling format.

    This function transforms ToolProtocol instances into the JSON Schema
    format required by the OpenAI API's native function calling feature.

    Args:
        tools: Dictionary mapping tool names to ToolProtocol instances

    Returns:
        List of tool definitions in OpenAI format:
        [
            {
                "type": "function",
                "function": {
                    "name": "tool_name",
                    "description": "Tool description",
                    "parameters": { JSON Schema }
                }
            },
            ...
        ]

    Example:
        >>> from taskforce.infrastructure.tools.native.file_tools \
        ...     import FileReadTool
        >>> tools = {"file_read": FileReadTool()}
        >>> openai_tools = tools_to_openai_format(tools)
        >>> print(openai_tools[0]["function"]["name"])
        'file_read'
    """
    openai_tools = []

    for tool in tools.values():
        openai_tool = {
            "type": "function",
            "function": {
                "name": tool.name,
                "description": tool.description,
                "parameters": tool.parameters_schema,
            },
        }
        openai_tools.append(openai_tool)

    return openai_tools


def tool_result_to_message(
    tool_call_id: str,
    tool_name: str,
    result: dict[str, Any],
    max_output_chars: int = 20000,
) -> dict[str, Any]:
    """
    Convert a tool execution result to an OpenAI tool message format.

    After executing a tool, the result must be added to the message history
    in the specific format expected by the OpenAI API.

    IMPORTANT: Large outputs are automatically truncated to prevent token
    overflow errors. The default limit is 20,000 chars (~5,000 tokens).

    Args:
        tool_call_id: The unique ID from the tool_call request
        tool_name: Name of the executed tool
        result: Result dictionary from tool.execute()
        max_output_chars: Max characters for output field (default: 20000)

    Returns:
        Message dict in OpenAI tool response format:
        {
            "role": "tool",
            "tool_call_id": "...",
            "name": "tool_name",
            "content": "JSON string of result"
        }

    Example:
        >>> result = {"success": True, "output": "File contents..."}
        >>> msg = tool_result_to_message("call_abc123", "file_read", result)
        >>> print(msg["role"])
        'tool'
    """
    # Truncate large outputs to prevent token overflow
    truncated_result = _truncate_tool_result(result, max_output_chars)

    # Convert to compact text (strips redundant JSON boilerplate)
    content = _result_to_compact_text(truncated_result)

    return {
        "role": "tool",
        "tool_call_id": tool_call_id,
        "name": tool_name,
        "content": content,
    }


def _result_to_compact_text(result: dict[str, Any]) -> str:
    """Convert a tool result dict to a compact text representation.

    Strips redundant wrapper keys (success, returncode, path, size, etc.)
    and returns only the primary content value. This saves ~40-50 tokens
    per tool call compared to full JSON serialization.

    Rules:
    - Error results: return ``"ERROR: <message>"``
    - Success results: extract the first found content key
      (``output`` > ``content`` > ``result`` > ``stdout``), append
      ``stderr`` if present.
    - Fallback: compact JSON (no indent) when no known content field exists.

    Args:
        result: Tool result dictionary.

    Returns:
        Compact text string for the message ``content`` field.
    """
    # Error path: only the error message matters
    if not result.get("success", True):
        error = result.get("error", "Unknown error")
        return f"ERROR: {error}"

    # Extract primary content value
    content_keys = ("output", "content", "result", "stdout")
    primary = None
    for key in content_keys:
        if key in result and result[key] is not None:
            val = result[key]
            primary = (
                val if isinstance(val, str) else json.dumps(val, ensure_ascii=False, default=str)
            )
            break

    if primary is None:
        # No known content field – fall back to compact JSON
        return json.dumps(result, ensure_ascii=False, default=str)

    # Append stderr if present
    stderr = result.get("stderr")
    if stderr and isinstance(stderr, str) and stderr.strip():
        primary = f"{primary}\n[stderr] {stderr}"

    return primary


def _truncate_tool_result(
    result: dict[str, Any],
    max_chars: int,
) -> dict[str, Any]:
    """
    Truncate large fields in tool result to prevent token overflow.

    Specifically handles:
    - output: Main output string (most common large field)
    - result: Result data (can be large for data operations)
    - content: File content (for file read operations)
    - stdout/stderr: Command outputs (for shell operations)

    Args:
        result: Original tool result dictionary
        max_chars: Maximum characters per large field

    Returns:
        Result dictionary with truncated fields
    """
    truncated = result.copy()

    # Fields that commonly contain large outputs
    # NOTE: RAG tools often return large payloads under "results" (list of chunks).
    large_fields = [
        "output",
        "result",
        "content",
        "stdout",
        "stderr",
        "data",
        "results",
    ]

    for field in large_fields:
        if field in truncated:
            value = truncated[field]
            if isinstance(value, str) and len(value) > max_chars:
                overflow = len(value) - max_chars
                truncated[field] = (
                    value[:max_chars] + f"\n\n[... TRUNCATED - {overflow} more chars ...]"
                )
            elif isinstance(value, (list, dict)):
                # For structured data, convert to string and check size
                value_str = json.dumps(value, ensure_ascii=False, default=str)
                if len(value_str) > max_chars:
                    overflow = len(value_str) - max_chars
                    truncated[field] = (
                        value_str[:max_chars] + f"\n\n[... TRUNCATED - {overflow} more chars ...]"
                    )

    return truncated


def assistant_tool_calls_to_message(
    tool_calls: list[dict[str, Any]],
) -> dict[str, Any]:
    """
    Create an assistant message with tool calls for message history.

    When the LLM returns tool_calls, we need to add the assistant's
    response (with tool_calls) to the message history before adding
    the tool results.

    Args:
        tool_calls: List of tool calls from LLM response

    Returns:
        Assistant message dict with tool_calls:
        {
            "role": "assistant",
            "content": None,
            "tool_calls": [...]
        }
    """
    return {
        "role": "assistant",
        "content": None,
        "tool_calls": tool_calls,
    }


def create_tool_result_preview(
    handle: ToolResultHandle,
    result: dict[str, Any],
    max_preview_chars: int = 2000,
) -> ToolResultPreview:
    """
    Create a preview of a tool result for message history.

    Extracts a short preview from the tool result to give the LLM context
    without overwhelming the prompt. The preview focuses on the most
    important fields (output, error, success status).

    Args:
        handle: Handle to the stored full result
        result: Full tool result dictionary
        max_preview_chars: Maximum characters for preview text (default: 500)

    Returns:
        ToolResultPreview with handle and short preview text

    Example:
        >>> result = {"success": True, "output": "..." * 10000}
        >>> preview = create_tool_result_preview(handle, result)
        >>> print(len(preview.preview_text))  # <= 500
        >>> print(preview.truncated)  # True
    """
    # Build compact preview – skip boilerplate, show content directly
    success = result.get("success", False)

    if not success:
        error_msg = str(result.get("error", "Unknown error"))[:max_preview_chars]
        preview_text = f"ERROR: {error_msg}"
        truncated = len(str(result.get("error", ""))) > max_preview_chars
    else:
        # Extract primary content (same priority as _result_to_compact_text)
        content_keys = ("output", "content", "result", "stdout")
        raw = None
        for key in content_keys:
            if key in result and result[key] is not None:
                raw = str(result[key])
                break

        if raw is None:
            raw = json.dumps(result, ensure_ascii=False, default=str)

        if len(raw) > max_preview_chars:
            preview_text = raw[:max_preview_chars] + "..."
            truncated = True
        else:
            preview_text = raw
            truncated = False

    # Append size hint for large results
    total_chars = handle.size_chars
    if total_chars > max_preview_chars:
        preview_text += f"\n[{total_chars} chars total, handle: {handle.id[:8]}]"

    return ToolResultPreview(
        handle=handle,
        preview_text=preview_text,
        truncated=truncated,
    )


def tool_result_preview_to_message(
    tool_call_id: str,
    tool_name: str,
    preview: ToolResultPreview,
) -> dict[str, Any]:
    """
    Convert a tool result preview to an OpenAI tool message format.

    This is the handle-based alternative to tool_result_to_message().
    Instead of including the full result, it includes only the handle
    and preview, keeping message history small.

    Args:
        tool_call_id: The unique ID from the tool_call request
        tool_name: Name of the executed tool
        preview: Preview with handle and short text

    Returns:
        Message dict in OpenAI tool response format:
        {
            "role": "tool",
            "tool_call_id": "...",
            "name": "tool_name",
            "content": "JSON string with handle and preview"
        }

    Example:
        >>> preview = create_tool_result_preview(handle, result)
        >>> msg = tool_result_preview_to_message("call_abc", "file_read", preview)
        >>> print(msg["role"])
        'tool'
    """
    # Serialize preview to JSON string for message content
    content = json.dumps(preview.to_dict(), ensure_ascii=False, default=str)

    return {
        "role": "tool",
        "tool_call_id": tool_call_id,
        "name": tool_name,
        "content": content,
    }
