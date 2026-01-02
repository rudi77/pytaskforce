"""
Token Budgeter - Budget management for prompt length and safe compression.

This module provides utilities for estimating token usage and enforcing
budget constraints to prevent "input tokens exceed limit" errors.

Key features:
- Heuristic token estimation (chars/4 + overhead)
- Budget-based compression triggers
- Safe message sanitization (hard caps on content)
- Handle-aware: understands tool result handles vs raw outputs
"""

import json
from typing import Any

import structlog


class TokenBudgeter:
    """
    Budget manager for LLM prompt token estimation and enforcement.

    Uses a simple heuristic for token estimation:
    - Base: len(text) / 4 (approximates ~4 chars per token)
    - Overhead: JSON structure, message roles, tool schemas
    - Context pack: Estimated separately with caps

    This is intentionally conservative to prevent overflow.
    """

    # Default budget limits (conservative for GPT-4 class models)
    DEFAULT_MAX_INPUT_TOKENS = 100000  # ~100k tokens for input
    DEFAULT_COMPRESSION_TRIGGER = 80000  # Trigger compression at 80% of max

    # Heuristic constants
    CHARS_PER_TOKEN = 4  # Conservative estimate (real: 3-5)
    MESSAGE_OVERHEAD_TOKENS = 10  # Per message (role, structure)
    TOOL_SCHEMA_OVERHEAD_TOKENS = 50  # Per tool definition
    SYSTEM_PROMPT_OVERHEAD_TOKENS = 100  # System prompt structure

    # Hard caps for individual message content (safety limits)
    MAX_MESSAGE_CONTENT_CHARS = 50000  # ~12.5k tokens max per message
    MAX_TOOL_OUTPUT_CHARS = 20000  # ~5k tokens max per tool output
    MAX_CONTEXT_PACK_CHARS = 10000  # ~2.5k tokens max for context pack

    def __init__(
        self,
        max_input_tokens: int | None = None,
        compression_trigger: int | None = None,
    ):
        """
        Initialize TokenBudgeter with budget limits.

        Args:
            max_input_tokens: Maximum input tokens allowed (default: 100k)
            compression_trigger: Token count to trigger compression (default: 80k)
        """
        self.max_input_tokens = max_input_tokens or self.DEFAULT_MAX_INPUT_TOKENS
        self.compression_trigger = compression_trigger or self.DEFAULT_COMPRESSION_TRIGGER
        self.logger = structlog.get_logger().bind(component="token_budgeter")

    def estimate_tokens(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        context_pack: str | None = None,
    ) -> int:
        """
        Estimate total token count for a prompt.

        Args:
            messages: List of message dictionaries
            tools: Optional list of tool schemas
            context_pack: Optional context pack string

        Returns:
            Estimated token count (conservative)
        """
        total_tokens = 0

        # System prompt overhead
        total_tokens += self.SYSTEM_PROMPT_OVERHEAD_TOKENS

        # Messages
        for msg in messages:
            # Message overhead (role, structure)
            total_tokens += self.MESSAGE_OVERHEAD_TOKENS

            # Content
            content = msg.get("content")
            if content:
                if isinstance(content, str):
                    total_tokens += len(content) // self.CHARS_PER_TOKEN
                elif isinstance(content, list):
                    # Multi-part content (images, etc.)
                    for part in content:
                        if isinstance(part, dict) and "text" in part:
                            total_tokens += len(part["text"]) // self.CHARS_PER_TOKEN

            # Tool calls (if present)
            tool_calls = msg.get("tool_calls")
            if tool_calls:
                for tc in tool_calls:
                    # Tool name + arguments
                    tc_json = json.dumps(tc, ensure_ascii=False, default=str)
                    total_tokens += len(tc_json) // self.CHARS_PER_TOKEN

        # Tool schemas
        if tools:
            for tool in tools:
                total_tokens += self.TOOL_SCHEMA_OVERHEAD_TOKENS
                # Tool schema JSON
                tool_json = json.dumps(tool, ensure_ascii=False, default=str)
                total_tokens += len(tool_json) // self.CHARS_PER_TOKEN

        # Context pack
        if context_pack:
            total_tokens += len(context_pack) // self.CHARS_PER_TOKEN

        self.logger.debug(
            "tokens_estimated",
            messages_count=len(messages),
            tools_count=len(tools) if tools else 0,
            context_pack_length=len(context_pack) if context_pack else 0,
            estimated_tokens=total_tokens,
        )

        return total_tokens

    def is_over_budget(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        context_pack: str | None = None,
    ) -> bool:
        """
        Check if prompt exceeds maximum budget.

        Args:
            messages: List of message dictionaries
            tools: Optional list of tool schemas
            context_pack: Optional context pack string

        Returns:
            True if estimated tokens exceed max_input_tokens
        """
        estimated = self.estimate_tokens(messages, tools, context_pack)
        over_budget = estimated > self.max_input_tokens

        if over_budget:
            self.logger.warning(
                "budget_exceeded",
                estimated_tokens=estimated,
                max_tokens=self.max_input_tokens,
                overflow=estimated - self.max_input_tokens,
            )

        return over_budget

    def should_compress(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        context_pack: str | None = None,
    ) -> bool:
        """
        Check if prompt should trigger compression.

        Args:
            messages: List of message dictionaries
            tools: Optional list of tool schemas
            context_pack: Optional context pack string

        Returns:
            True if estimated tokens exceed compression_trigger
        """
        estimated = self.estimate_tokens(messages, tools, context_pack)
        should_compress = estimated > self.compression_trigger

        if should_compress:
            self.logger.info(
                "compression_recommended",
                estimated_tokens=estimated,
                trigger_threshold=self.compression_trigger,
            )

        return should_compress

    def sanitize_message(
        self,
        message: dict[str, Any],
        max_chars: int | None = None,
    ) -> dict[str, Any]:
        """
        Sanitize a message by truncating large content fields.

        This is a hard safety cap to prevent individual messages from
        overwhelming the prompt. Applied before messages go into summaries
        or LLM calls.

        Args:
            message: Message dictionary to sanitize
            max_chars: Maximum characters for content (default: MAX_MESSAGE_CONTENT_CHARS)

        Returns:
            Sanitized message dictionary (copy)
        """
        # Tool messages can be extremely large (e.g., RAG result lists).
        # Cap tool message content more aggressively than normal messages.
        if max_chars is None and message.get("role") == "tool":
            max_chars = self.MAX_TOOL_OUTPUT_CHARS
        max_chars = max_chars or self.MAX_MESSAGE_CONTENT_CHARS
        sanitized = message.copy()

        # Sanitize content field
        content = sanitized.get("content")
        if content and isinstance(content, str):
            if len(content) > max_chars:
                overflow = len(content) - max_chars
                sanitized["content"] = (
                    content[:max_chars]
                    + f"\n\n[... SANITIZED - {overflow} more chars omitted for safety ...]"
                )
                self.logger.debug(
                    "message_content_sanitized",
                    role=sanitized.get("role"),
                    original_length=len(content),
                    sanitized_length=len(sanitized["content"]),
                )

        # Sanitize tool_calls arguments (if present)
        tool_calls = sanitized.get("tool_calls")
        if tool_calls:
            for tc in tool_calls:
                if "function" in tc and "arguments" in tc["function"]:
                    args_str = tc["function"]["arguments"]
                    if isinstance(args_str, str) and len(args_str) > max_chars:
                        overflow = len(args_str) - max_chars
                        tc["function"]["arguments"] = (
                            args_str[:max_chars] + f" ... [SANITIZED - {overflow} chars omitted]"
                        )

        return sanitized

    def sanitize_messages(
        self,
        messages: list[dict[str, Any]],
        max_chars: int | None = None,
    ) -> list[dict[str, Any]]:
        """
        Sanitize a list of messages.

        Args:
            messages: List of message dictionaries
            max_chars: Maximum characters per message content

        Returns:
            List of sanitized message dictionaries
        """
        return [self.sanitize_message(msg, max_chars) for msg in messages]

    def extract_tool_output_preview(
        self,
        tool_result: dict[str, Any],
        max_chars: int | None = None,
    ) -> str:
        """
        Extract a safe preview from a tool result.

        Used when building summaries or context - extracts only the
        essential information without raw payloads.

        Args:
            tool_result: Tool result dictionary
            max_chars: Maximum characters for preview (default: MAX_TOOL_OUTPUT_CHARS)

        Returns:
            Preview string (safe for inclusion in prompts)
        """
        max_chars = max_chars or self.MAX_TOOL_OUTPUT_CHARS
        preview_parts = []

        # Success status
        success = tool_result.get("success", False)
        preview_parts.append(f"Success: {success}")

        # Error (if present)
        if not success and "error" in tool_result:
            error_msg = str(tool_result["error"])[:500]
            preview_parts.append(f"Error: {error_msg}")

        # Output preview (truncated)
        if "output" in tool_result:
            output = str(tool_result["output"])
            if len(output) > max_chars:
                output_preview = output[:max_chars] + "..."
            else:
                output_preview = output
            preview_parts.append(f"Output: {output_preview}")

        # Handle reference (if present)
        if "handle" in tool_result:
            handle_id = tool_result["handle"].get("id", "unknown")
            preview_parts.append(f"Handle: {handle_id}")

        return " | ".join(preview_parts)

    def get_budget_stats(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        context_pack: str | None = None,
    ) -> dict[str, Any]:
        """
        Get detailed budget statistics for diagnostics.

        Args:
            messages: List of message dictionaries
            tools: Optional list of tool schemas
            context_pack: Optional context pack string

        Returns:
            Dictionary with budget statistics
        """
        estimated = self.estimate_tokens(messages, tools, context_pack)
        remaining = max(0, self.max_input_tokens - estimated)
        utilization = (estimated / self.max_input_tokens) * 100

        return {
            "estimated_tokens": estimated,
            "max_tokens": self.max_input_tokens,
            "remaining_tokens": remaining,
            "utilization_percent": round(utilization, 2),
            "over_budget": estimated > self.max_input_tokens,
            "should_compress": estimated > self.compression_trigger,
            "compression_trigger": self.compression_trigger,
        }
