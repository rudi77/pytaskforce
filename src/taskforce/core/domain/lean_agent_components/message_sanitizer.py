"""
Message Sanitizer for Agent conversations.

Handles sanitization of message history to ensure valid tool-call pairs
and prevent orphan tool messages that cause provider errors.
"""

from __future__ import annotations

from typing import Any

from taskforce.core.interfaces.logging import LoggerProtocol


class MessageSanitizer:
    """
    Sanitize message history for LLM provider compatibility.

    Responsibilities:
    - Ensure tool messages have matching assistant.tool_calls
    - Drop orphan tool messages
    - Preserve tool-call pairs when trimming history
    """

    def __init__(self, logger: LoggerProtocol) -> None:
        """
        Initialize the message sanitizer.

        Args:
            logger: Logger for warnings about dropped messages
        """
        self._logger = logger

    def find_matching_tool_call_assistant_index(
        self, messages: list[dict[str, Any]], tool_message_index: int
    ) -> int | None:
        """
        Find the assistant message index that contains the tool_call_id.

        Azure/OpenAI requires each `role="tool"` message to be a response
        to a preceding assistant message that includes `tool_calls` with
        a matching `id`.

        Args:
            messages: Full message list
            tool_message_index: Index of the tool message to match

        Returns:
            Index of matching assistant message, or None if not found
        """
        if tool_message_index <= 0 or tool_message_index >= len(messages):
            return None

        tool_msg = messages[tool_message_index]
        if tool_msg.get("role") != "tool":
            return None

        tool_call_id = tool_msg.get("tool_call_id")
        if not tool_call_id:
            return None

        for idx in range(tool_message_index - 1, -1, -1):
            msg = messages[idx]
            if msg.get("role") != "assistant":
                continue
            tool_calls = msg.get("tool_calls") or []
            if any(tc.get("id") == tool_call_id for tc in tool_calls):
                return idx

        return None

    def drop_orphan_tool_messages(
        self, messages: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        """
        Drop tool messages without a matching assistant.tool_calls message.

        This prevents provider errors like:
        "messages with role 'tool' must be a response to a preceding
        message with 'tool_calls'".

        Args:
            messages: Message list to sanitize

        Returns:
            Sanitized message list with orphans removed
        """
        if not messages:
            return messages

        sanitized: list[dict[str, Any]] = []
        for idx, msg in enumerate(messages):
            if msg.get("role") != "tool":
                sanitized.append(msg)
                continue

            assistant_idx = self.find_matching_tool_call_assistant_index(messages, idx)
            if assistant_idx is None or assistant_idx >= idx:
                self._logger.warning(
                    "dropping_orphan_tool_message",
                    tool_call_id=msg.get("tool_call_id"),
                    tool_name=msg.get("name"),
                )
                continue

            sanitized.append(msg)

        return sanitized

    def keep_recent_preserving_tool_pairs(
        self, messages: list[dict[str, Any]], keep_last_n: int
    ) -> list[dict[str, Any]]:
        """
        Keep recent messages without cutting tool-call pairs.

        If the kept window contains a tool message whose matching
        assistant.tool_calls lies before the window, the window start
        is moved back to include that assistant message.

        Args:
            messages: Full message list (first message should be system prompt)
            keep_last_n: Number of recent messages to keep

        Returns:
            Trimmed and sanitized message list
        """
        if not messages:
            return messages
        if keep_last_n <= 0:
            return [messages[0]] if messages else []

        system_prompt = messages[0]
        if len(messages) <= 1:
            return [system_prompt]

        start = max(1, len(messages) - keep_last_n)

        # Expand window to include matching assistant.tool_calls
        adjusted = True
        while adjusted:
            adjusted = False
            for idx in range(start, len(messages)):
                if messages[idx].get("role") != "tool":
                    continue
                assistant_idx = self.find_matching_tool_call_assistant_index(
                    messages, idx
                )
                if assistant_idx is not None and assistant_idx < start:
                    start = assistant_idx
                    adjusted = True
                    break

        trimmed = [system_prompt, *messages[start:]]
        return self.drop_orphan_tool_messages(trimmed)

    def adjust_keep_boundary_for_tool_pairs(
        self, messages: list[dict[str, Any]], keep_from: int
    ) -> int:
        """
        Adjust a boundary index to not cut tool-call pairs.

        Args:
            messages: Full message list
            keep_from: Initial boundary index

        Returns:
            Adjusted boundary that doesn't cut tool-call pairs
        """
        if keep_from >= len(messages):
            return keep_from

        adjusted = True
        while adjusted:
            adjusted = False
            for idx in range(keep_from, len(messages)):
                if messages[idx].get("role") != "tool":
                    continue
                assistant_idx = self.find_matching_tool_call_assistant_index(
                    messages, idx
                )
                if assistant_idx is not None and assistant_idx < keep_from:
                    keep_from = assistant_idx
                    adjusted = True
                    break

        return keep_from
