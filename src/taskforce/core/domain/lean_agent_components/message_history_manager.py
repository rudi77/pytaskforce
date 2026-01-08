"""Message history management for Agent."""

from __future__ import annotations

import json
from typing import Any

import structlog

from taskforce.core.domain.token_budgeter import TokenBudgeter
from taskforce.core.interfaces.llm import LLMProviderProtocol


class MessageHistoryManager:
    """Manage Agent message history, compression, and budget enforcement."""

    def __init__(
        self,
        *,
        token_budgeter: TokenBudgeter,
        openai_tools: list[dict[str, Any]],
        llm_provider: LLMProviderProtocol,
        model_alias: str,
        summary_threshold: int,
        logger: structlog.stdlib.BoundLogger,
    ) -> None:
        self._token_budgeter = token_budgeter
        self._openai_tools = openai_tools
        self._llm_provider = llm_provider
        self._model_alias = model_alias
        self._summary_threshold = summary_threshold
        self._logger = logger

    def build_initial_messages(
        self,
        mission: str,
        state: dict[str, Any],
        base_system_prompt: str,
    ) -> list[dict[str, Any]]:
        """
        Build initial message list for LLM conversation.

        Includes conversation_history from state to support multi-turn chat.
        The history contains previous user/assistant exchanges for context.
        """
        messages: list[dict[str, Any]] = [
            {"role": "system", "content": base_system_prompt},
        ]

        conversation_history = state.get("conversation_history", [])
        if conversation_history:
            for msg in conversation_history:
                role = msg.get("role")
                content = msg.get("content", "")
                if role in ("user", "assistant") and content:
                    messages.append({"role": role, "content": content})
            self._logger.debug(
                "conversation_history_loaded",
                history_length=len(conversation_history),
            )

        user_answers = state.get("answers", {})
        answers_text = ""
        if user_answers:
            answers_text = (
                "\n\n## User Provided Information\n" f"{json.dumps(user_answers, indent=2)}"
            )

        user_message = f"{mission}{answers_text}"
        messages.append({"role": "user", "content": user_message})

        return messages

    def _find_matching_tool_call_assistant_index(
        self, messages: list[dict[str, Any]], tool_message_index: int
    ) -> int | None:
        """
        Find the assistant message index that contains the tool_call_id for a tool message.

        Azure/OpenAI requires each `role="tool"` message to be a response to a preceding
        assistant message that includes `tool_calls` with a matching `id`.
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

    def _drop_orphan_tool_messages(
        self, messages: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        """
        Drop tool messages that are not preceded by a matching assistant.tool_calls message.

        This is a safety net to prevent provider errors like:
        "messages with role 'tool' must be a response to a preceding message with 'tool_calls'".
        """
        if not messages:
            return messages

        sanitized: list[dict[str, Any]] = []
        for idx, msg in enumerate(messages):
            if msg.get("role") != "tool":
                sanitized.append(msg)
                continue

            assistant_idx = self._find_matching_tool_call_assistant_index(messages, idx)
            if assistant_idx is None or assistant_idx >= idx:
                self._logger.warning(
                    "dropping_orphan_tool_message",
                    tool_call_id=msg.get("tool_call_id"),
                    tool_name=msg.get("name"),
                )
                continue

            sanitized.append(msg)

        return sanitized

    def _keep_recent_messages_preserving_tool_call_pairs(
        self, messages: list[dict[str, Any]], keep_last_n: int
    ) -> list[dict[str, Any]]:
        """
        Keep the most recent messages, but never cut a tool-call pair in half.

        If the kept window contains a tool message whose matching assistant.tool_calls
        lies before the window, the window start is moved back to include that assistant.
        """
        if not messages:
            return messages
        if keep_last_n <= 0:
            return [messages[0]] if messages else []

        system_prompt = messages[0]
        if len(messages) <= 1:
            return [system_prompt]

        start = max(1, len(messages) - keep_last_n)

        # Expand window start to include the matching assistant.tool_calls for any tool messages.
        adjusted = True
        while adjusted:
            adjusted = False
            for idx in range(start, len(messages)):
                if messages[idx].get("role") != "tool":
                    continue
                assistant_idx = self._find_matching_tool_call_assistant_index(messages, idx)
                if assistant_idx is not None and assistant_idx < start:
                    start = assistant_idx
                    adjusted = True
                    break

        trimmed = [system_prompt, *messages[start:]]
        return self._drop_orphan_tool_messages(trimmed)

    async def compress_messages(self, messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """
        Compress message history using safe LLM-based summarization.

        Strategy (Story 9.3 - Safe Compression):
        1. Trigger based on token budget (primary) or message count (fallback)
        2. Build safe summary input from sanitized message previews (NO raw dumps)
        3. Use LLM to summarize old messages (skip system prompt)
        4. Replace old messages with summary + keep recent messages
        5. Fallback: Simple truncation if LLM summarization fails
        """
        message_count = len(messages)

        should_compress_budget = self._token_budgeter.should_compress(
            messages=messages,
            tools=self._openai_tools,
        )

        should_compress_count = message_count > self._summary_threshold

        if not (should_compress_budget or should_compress_count):
            return messages

        self._logger.warning(
            "compressing_messages",
            message_count=message_count,
            threshold=self._summary_threshold,
            budget_trigger=should_compress_budget,
            count_trigger=should_compress_count,
        )

        max_messages_to_summarize = min(self._summary_threshold - 1, 15)
        old_messages = messages[1 : 1 + max_messages_to_summarize]

        summary_input = self.build_safe_summary_input(old_messages)

        if len(summary_input) > 50000:
            self._logger.error(
                "compression_input_too_large",
                input_length=len(summary_input),
                action="using_deterministic_fallback",
            )
            return self.deterministic_compression(messages)

        summary_prompt = f"""Summarize this conversation history concisely:

{summary_input}

Provide a 2-3 paragraph summary of:
- Key decisions made
- Important tool results and findings
- Context needed for understanding recent messages

Keep it factual and concise."""

        compression_messages = [{"role": "user", "content": summary_prompt}]
        compression_estimated = self._token_budgeter.estimate_tokens(compression_messages)

        if compression_estimated > self._token_budgeter.max_input_tokens:
            self._logger.error(
                "compression_prompt_over_budget",
                estimated_tokens=compression_estimated,
                max_tokens=self._token_budgeter.max_input_tokens,
                action="using_deterministic_fallback",
            )
            return self.deterministic_compression(messages)

        try:
            result = await self._llm_provider.complete(
                messages=compression_messages,
                model=self._model_alias,
                temperature=0,
            )

            error = result.get("error", "")
            if "context length" in error.lower() or "token limit" in error.lower():
                self._logger.error(
                    "compression_context_length_exceeded",
                    error=error,
                    action="using_deterministic_fallback",
                )
                return self.deterministic_compression(messages)

            if not result.get("success"):
                self._logger.error(
                    "compression_failed",
                    error=error,
                )
                return self.deterministic_compression(messages)

            summary = result.get("content", "")

            # Ensure we don't cut tool-call pairs at the boundary.
            keep_from = self._summary_threshold
            if keep_from < len(messages):
                # Rewind if kept range starts in the middle of a tool call sequence.
                adjusted = True
                while adjusted:
                    adjusted = False
                    for idx in range(keep_from, len(messages)):
                        if messages[idx].get("role") != "tool":
                            continue
                        assistant_idx = self._find_matching_tool_call_assistant_index(messages, idx)
                        if assistant_idx is not None and assistant_idx < keep_from:
                            keep_from = assistant_idx
                            adjusted = True
                            break

            compressed = [
                messages[0],
                {
                    "role": "assistant",
                    "content": f"[Previous Context Summary]\n{summary}",
                },
                *messages[keep_from:],
            ]

            self._logger.info(
                "messages_compressed_with_summary",
                original_count=message_count,
                compressed_count=len(compressed),
                summary_length=len(summary),
            )

            return self._drop_orphan_tool_messages(compressed)

        except Exception as error:
            self._logger.error("compression_exception", error=str(error))
            return self.deterministic_compression(messages)

    def deterministic_compression(self, messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """
        Deterministic compression without LLM (emergency fallback).

        Strategy:
        - Keep system prompt
        - Keep last 10 messages (hard cap)
        - Add a simple text summary of what was dropped
        """
        self._logger.warning(
            "using_deterministic_compression",
            original_count=len(messages),
        )

        system_prompt = messages[0] if messages else {"role": "system", "content": ""}
        # Keep last 10 messages, but preserve tool-call pairs.
        trimmed = self._keep_recent_messages_preserving_tool_call_pairs(messages, keep_last_n=10)
        recent_messages = trimmed[1:]  # exclude system prompt (kept separately below)

        dropped_count = max(0, len(messages) - len(recent_messages) - 1)
        if dropped_count > 0:
            summary_text = (
                f"[{dropped_count} earlier messages compressed for token budget. "
                "Continuing from recent context.]"
            )
            compressed = [
                system_prompt,
                {"role": "assistant", "content": summary_text},
                *recent_messages,
            ]
        else:
            compressed = [system_prompt, *recent_messages]

        self._logger.info(
            "deterministic_compression_complete",
            original_count=len(messages),
            compressed_count=len(compressed),
            dropped_count=dropped_count,
        )

        return self._drop_orphan_tool_messages(compressed)

    def build_safe_summary_input(self, messages: list[dict[str, Any]]) -> str:
        """
        Build safe summary input from messages without raw JSON dumps.

        Extracts only essential information from messages:
        - Role and content (sanitized)
        - Tool call names (not full arguments)
        - Tool result previews (not raw outputs)
        """
        summary_parts: list[str] = []

        for idx, msg in enumerate(messages):
            role = msg.get("role", "unknown")
            parts = [f"[Message {idx + 1} - {role}]"]

            if role == "tool":
                tool_name = msg.get("name", "unknown")
                parts.append(f"Tool: {tool_name}")

                try:
                    content_str = msg.get("content", "")
                    if content_str:
                        result_data = json.loads(content_str)
                        preview = self._token_budgeter.extract_tool_output_preview(result_data)
                        parts.append(f"Result: {preview}")
                except (json.JSONDecodeError, TypeError):
                    content_str = str(msg.get("content", ""))[:500]
                    parts.append(f"Result: {content_str}")
            else:
                content = msg.get("content")
                if content:
                    sanitized_msg = self._token_budgeter.sanitize_message(msg)
                    sanitized_content = sanitized_msg.get("content", "")
                    if sanitized_content:
                        parts.append(f"Content: {sanitized_content[:1000]}")

                tool_calls = msg.get("tool_calls")
                if tool_calls:
                    tool_names = [
                        tc.get("function", {}).get("name", "unknown") for tc in tool_calls
                    ]
                    parts.append(f"Tools called: {', '.join(tool_names)}")

            summary_parts.append("\n".join(parts))

        return "\n\n".join(summary_parts)

    async def preflight_budget_check(
        self, messages: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        """
        Preflight budget check before LLM call.

        If messages exceed budget even after compression, apply emergency
        sanitization and truncation to prevent token overflow errors.
        """
        if not self._token_budgeter.is_over_budget(
            messages=messages,
            tools=self._openai_tools,
        ):
            return messages

        self._logger.error(
            "emergency_budget_enforcement",
            message_count=len(messages),
            action="sanitize_and_truncate",
        )

        sanitized = self._token_budgeter.sanitize_messages(messages)

        if self._token_budgeter.is_over_budget(
            messages=sanitized,
            tools=self._openai_tools,
        ):
            self._logger.error(
                "emergency_truncation",
                original_count=len(sanitized),
                action="keep_recent_only",
            )
            emergency_truncated = self._keep_recent_messages_preserving_tool_call_pairs(
                sanitized, keep_last_n=10
            )

            self._logger.warning(
                "emergency_truncation_complete",
                final_count=len(emergency_truncated),
            )

            return emergency_truncated

        return self._drop_orphan_tool_messages(sanitized)
