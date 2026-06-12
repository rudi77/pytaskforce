"""Pure mapping between OpenAI-format message dicts and ctxman segments.

Forward direction only: ``render {provider: "openai"}`` already returns
messages in OpenAI format, so no reverse mapping is needed.
"""

from __future__ import annotations

import json
from typing import Any


def split_static(
    messages: list[dict[str, Any]],
) -> tuple[str, list[dict[str, Any]]]:
    """Split a message list into (system prompt, non-system messages).

    The system prompt belongs to ctxman's static region and must not be
    appended as a working segment.
    """
    system_prompt = ""
    rest: list[dict[str, Any]] = []
    for message in messages:
        if message.get("role") == "system" and not system_prompt:
            system_prompt = str(message.get("content") or "")
        else:
            rest.append(message)
    return system_prompt, rest


def build_static_segments(
    base_system_prompt: str,
    openai_tools: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Build the static-region segments for session creation."""
    segments: list[dict[str, Any]] = [
        {
            "kind": "system_prompt",
            "role": "system",
            "content": base_system_prompt,
            "source": "core",
        },
    ]
    for tool in openai_tools:
        name = tool.get("function", {}).get("name") or tool.get("name") or "tool"
        segments.append(
            {
                "kind": "tool_def",
                "content": json.dumps(tool, ensure_ascii=False, sort_keys=True),
                "source": f"taskforce:{name}",
            }
        )
    return segments


def message_to_segments(message: dict[str, Any]) -> list[dict[str, Any]]:
    """Map one OpenAI message dict to one or more ctxman segments.

    System messages map to an empty list — they live in the static region.
    """
    role = str(message.get("role") or "")
    content = _content_to_text(message.get("content"))

    if role == "system":
        return []

    if role == "user":
        return [{"kind": "user_msg", "role": "user", "content": content}]

    if role == "assistant":
        tool_calls = message.get("tool_calls") or []
        if not tool_calls:
            return [{"kind": "assistant_msg", "role": "assistant", "content": content}]
        segments: list[dict[str, Any]] = []
        if content:
            segments.append({"kind": "assistant_msg", "role": "assistant", "content": content})
        for tool_call in tool_calls:
            function = tool_call.get("function", {}) or {}
            segments.append(
                {
                    "kind": "tool_call",
                    "role": "assistant",
                    "tool_call_id": tool_call.get("id"),
                    "content": json.dumps(
                        {
                            "name": function.get("name"),
                            "arguments": function.get("arguments"),
                        },
                        ensure_ascii=False,
                    ),
                }
            )
        return segments

    if role == "tool":
        return [
            {
                "kind": "tool_result",
                "role": "tool",
                "tool_call_id": message.get("tool_call_id"),
                "content": content,
            }
        ]

    # Unknown roles degrade to a user-visible message rather than being lost.
    return [{"kind": "user_msg", "role": "user", "content": content}]


def messages_to_segments(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Map a list of OpenAI messages to a flat list of ctxman segments."""
    segments: list[dict[str, Any]] = []
    for message in messages:
        segments.extend(message_to_segments(message))
    return segments


def _content_to_text(content: Any) -> str:
    """Normalize message content (string or content-part list) to text."""
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for part in content:
            if isinstance(part, dict):
                parts.append(str(part.get("text") or part.get("content") or ""))
            else:
                parts.append(str(part))
        return "\n".join(p for p in parts if p)
    return str(content)
