"""
Token Budgeter - Budget management for prompt length and safe compression.

This module provides utilities for estimating token usage and enforcing
budget constraints to prevent "input tokens exceed limit" errors.

Key features:
- Pluggable token estimation via TokenEstimatorProtocol
- Budget-based compression triggers
- Safe message sanitization (hard caps on content)
- Handle-aware: understands tool result handles vs raw outputs
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

from taskforce.core.domain.heuristic_token_estimator import HeuristicTokenEstimator
from taskforce.core.interfaces.logging import LoggerProtocol

if TYPE_CHECKING:
    from taskforce.core.interfaces.token_estimator import TokenEstimatorProtocol


class TokenBudgeter:
    """
    Budget manager for LLM prompt token estimation and enforcement.

    Uses a pluggable TokenEstimatorProtocol for token counting. When no
    estimator is provided, falls back to HeuristicTokenEstimator with
    calibrated constants.

    The estimator can be swapped for accurate tiktoken-based counting
    when the optional ``tokenizer`` dependency is installed.
    """

    # Default budget limits (conservative for GPT-4 class models)
    DEFAULT_MAX_INPUT_TOKENS = 100000  # ~100k tokens for input
    DEFAULT_COMPRESSION_TRIGGER = 40000  # Trigger compression at 40% - keep history lean

    # Legacy heuristic constants (kept for backward compatibility)
    CHARS_PER_TOKEN = 4
    MESSAGE_OVERHEAD_TOKENS = 10
    TOOL_SCHEMA_OVERHEAD_TOKENS = 50
    SYSTEM_PROMPT_OVERHEAD_TOKENS = 100

    # Hard caps for individual message content (safety limits)
    MAX_MESSAGE_CONTENT_CHARS = 50000  # ~12.5k tokens max per message
    MAX_TOOL_OUTPUT_CHARS = 20000  # ~5k tokens max per tool output
    MAX_CONTEXT_PACK_CHARS = 10000  # ~2.5k tokens max for context pack

    def __init__(
        self,
        logger: LoggerProtocol,
        max_input_tokens: int | None = None,
        compression_trigger: int | None = None,
        estimator: TokenEstimatorProtocol | None = None,
    ):
        """
        Initialize TokenBudgeter with budget limits.

        Args:
            logger: Logger instance (created in factory and always required).
            max_input_tokens: Maximum input tokens allowed (default: 100k)
            compression_trigger: Token count to trigger compression (default: 80k)
            estimator: Token estimation strategy (default: HeuristicTokenEstimator)
        """
        self.max_input_tokens = max_input_tokens or self.DEFAULT_MAX_INPUT_TOKENS
        self.compression_trigger = compression_trigger or self.DEFAULT_COMPRESSION_TRIGGER
        self.logger = logger
        self._estimator: TokenEstimatorProtocol = estimator or HeuristicTokenEstimator()

    def estimate_tokens(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        context_pack: str | None = None,
    ) -> int:
        """
        Estimate total token count for a prompt.

        Results are memoised for the duration of a single call chain: when
        called twice in the same ReAct loop iteration with identical arguments
        (same list object and same tools reference) the second call returns
        the cached value and skips logging to avoid duplicate ``tokens_estimated``
        log events.

        Args:
            messages: List of message dictionaries
            tools: Optional list of tool schemas
            context_pack: Optional context pack string

        Returns:
            Estimated token count (conservative)
        """
        # Short-circuit: same list object + same tools + no context_pack → reuse last result.
        # Uses object identity (id()) which is O(1) and works reliably within one call chain.
        cache_key = (id(messages), id(tools), context_pack)
        cached = getattr(self, "_estimate_cache", None)
        if cached is not None and cached[0] == cache_key:
            return cached[1]

        total_tokens = 0
        estimator = self._estimator

        # System prompt overhead
        total_tokens += estimator.count_system_prompt_overhead()

        # Messages
        for msg in messages:
            # Message overhead (role, structure)
            total_tokens += estimator.count_message_overhead()

            # Content
            content = msg.get("content")
            if content:
                if isinstance(content, str):
                    total_tokens += estimator.count_tokens(content)
                elif isinstance(content, list):
                    # Multi-part content (images, etc.)
                    for part in content:
                        if isinstance(part, dict) and "text" in part:
                            total_tokens += estimator.count_tokens(part["text"])

            # Tool calls (if present)
            tool_calls = msg.get("tool_calls")
            if tool_calls:
                for tc in tool_calls:
                    # Tool name + arguments
                    tc_json = json.dumps(tc, ensure_ascii=False, default=str)
                    total_tokens += estimator.count_tokens(tc_json)

        # Tool schemas — cache the per-tool-list token estimate because the
        # tool list object rarely changes between calls (same list reference),
        # but json.dumps() on every tool schema is expensive with 19+ tools.
        if tools:
            tools_id = id(tools)
            cached_tools = getattr(self, "_tools_tokens_cache", None)
            if cached_tools is not None and cached_tools[0] == tools_id:
                total_tokens += cached_tools[1]
            else:
                tools_tokens = 0
                for tool in tools:
                    tools_tokens += estimator.count_tool_schema_overhead()
                    tool_json = json.dumps(tool, ensure_ascii=False, default=str)
                    tools_tokens += estimator.count_tokens(tool_json)
                self._tools_tokens_cache = (tools_id, tools_tokens)
                total_tokens += tools_tokens

        # Context pack
        if context_pack:
            total_tokens += estimator.count_tokens(context_pack)

        self.logger.debug(
            "tokens_estimated",
            messages_count=len(messages),
            tools_count=len(tools) if tools else 0,
            context_pack_length=len(context_pack) if context_pack else 0,
            estimated_tokens=total_tokens,
        )

        # Cache result keyed by object identity for same-iteration reuse
        self._estimate_cache = (cache_key, total_tokens)

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
