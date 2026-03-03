"""
LLM response parsing and normalization.

Internal helper for LiteLLMService. Not part of the public API.

Handles:
- Non-streaming completion response parsing
- Token usage extraction (dict and object forms)
- Tool call extraction and normalization
- Streaming tool-call delta accumulation helpers
- Actual model verification (requested vs. provider-reported)
"""

from __future__ import annotations

from typing import Any

import structlog

logger = structlog.get_logger(__name__)


class LLMResponseParser:
    """Parses and normalizes LLM responses from LiteLLM.

    Provides static/class methods for extracting content, tool calls,
    and usage data from both streaming and non-streaming LLM responses.
    """

    @staticmethod
    def parse_response(response: Any, model: str, latency_ms: int) -> dict[str, Any]:
        """Extract normalized result from a LiteLLM completion response.

        Args:
            response: Raw LiteLLM response object.
            model: Resolved model string (what was requested).
            latency_ms: Request latency in milliseconds.

        Returns:
            Normalized response dict with success, content, tool_calls, usage,
            model (requested), and actual_model (provider-reported).
        """
        choice = response.choices[0]
        message = choice.message

        content = message.content or ""

        # Reasoning models may put content in reasoning_content
        if not content:
            reasoning_content = getattr(message, "reasoning_content", None)
            if reasoning_content:
                content = reasoning_content
            elif hasattr(message, "refusal") and message.refusal:
                content = f"[Model refused: {message.refusal}]"

        # Extract tool calls
        tool_calls = LLMResponseParser._extract_tool_calls(message)

        # Extract usage
        usage = LLMResponseParser.extract_usage(response)

        # Extract the actual model reported by the provider
        raw_model = getattr(response, "model", None)
        actual_model = raw_model if isinstance(raw_model, str) else None
        LLMResponseParser._check_model_mismatch(model, actual_model)

        return {
            "success": True,
            "content": content if content else None,
            "tool_calls": tool_calls,
            "usage": usage,
            "model": model,
            "actual_model": actual_model,
            "latency_ms": latency_ms,
        }

    @staticmethod
    def _check_model_mismatch(requested: str, actual: str | None) -> None:
        """Log the actual model and warn if it differs from what was requested.

        Compares the bare model name (without provider prefix) to account for
        provider-specific response formats. Handles two common patterns:

        - **Provider prefix**: Azure returns ``gpt-5-nano`` for ``azure/gpt-5-nano``
        - **Version suffix**: Azure returns ``gpt-5-nano-2025-08-07`` for ``gpt-5-nano``

        A match is declared when the actual bare name starts with the requested
        bare name (prefix match), which covers both exact matches and
        version-suffixed responses.

        Args:
            requested: The model string that was sent to LiteLLM.
            actual: The model string reported back by the provider (may be None).
        """
        if not actual:
            logger.debug("llm_response.no_actual_model", requested_model=requested)
            return

        # Strip provider prefix for comparison (azure/gpt-5-nano → gpt-5-nano)
        requested_bare = requested.split("/", 1)[-1] if "/" in requested else requested
        actual_bare = actual.split("/", 1)[-1] if "/" in actual else actual

        # Prefix match handles version suffixes (gpt-5-nano vs gpt-5-nano-2025-08-07)
        if actual_bare.lower().startswith(requested_bare.lower()):
            logger.info(
                "llm_response.model_verified",
                requested_model=requested,
                actual_model=actual,
            )
        else:
            logger.warning(
                "llm_response.model_mismatch",
                requested_model=requested,
                actual_model=actual,
                msg="Provider returned a different model than requested!",
            )

    @staticmethod
    def extract_actual_model_from_chunk(chunk: Any) -> str | None:
        """Extract the model name from a streaming chunk.

        Args:
            chunk: A single streaming chunk from LiteLLM.

        Returns:
            The model string from the chunk, or None if not a real string value.
        """
        raw = getattr(chunk, "model", None)
        return raw if isinstance(raw, str) else None

    @staticmethod
    def _extract_tool_calls(message: Any) -> list[dict[str, Any]] | None:
        """Extract and normalize tool calls from a completion message.

        Args:
            message: The message object from the LLM response choice.

        Returns:
            List of normalized tool call dicts, or None if no tool calls.
        """
        tool_calls_raw = getattr(message, "tool_calls", None)
        if not tool_calls_raw:
            return None

        tool_calls = []
        for tc in tool_calls_raw:
            tool_calls.append(
                {
                    "id": tc.id,
                    "type": getattr(tc, "type", "function"),
                    "function": {
                        "name": tc.function.name,
                        "arguments": tc.function.arguments,
                    },
                }
            )
        return tool_calls

    @staticmethod
    def extract_usage(response: Any) -> dict[str, int]:
        """Extract token usage from response (handles both dict and object forms).

        Args:
            response: Raw LiteLLM response object.

        Returns:
            Dict with total_tokens, prompt_tokens, completion_tokens (or empty dict).
        """
        raw_usage = getattr(response, "usage", None)
        if raw_usage is None:
            return {}
        if isinstance(raw_usage, dict):
            return raw_usage
        return {
            "total_tokens": getattr(raw_usage, "total_tokens", 0) or 0,
            "prompt_tokens": getattr(raw_usage, "prompt_tokens", 0) or 0,
            "completion_tokens": getattr(raw_usage, "completion_tokens", 0) or 0,
        }

    @staticmethod
    def init_tool_call_entry(tc: Any) -> dict[str, Any]:
        """Create an initial tool-call accumulator from a streaming delta.

        Args:
            tc: A single tool-call delta object from the stream chunk.

        Returns:
            Dict with ``id``, ``name``, and empty ``arguments`` string.
        """
        tool_id = getattr(tc, "id", None) or ""
        tool_name = ""
        if hasattr(tc, "function") and tc.function:
            tool_name = getattr(tc.function, "name", None) or ""
        return {"id": tool_id, "name": tool_name, "arguments": ""}

    @staticmethod
    def update_tool_call_metadata(tc: Any, entry: dict[str, Any]) -> None:
        """Update tool-call id/name from later streaming chunks.

        Args:
            tc: Tool-call delta with potentially updated id/name.
            entry: The accumulator dict to update in place.
        """
        if hasattr(tc, "id") and tc.id:
            entry["id"] = tc.id
        if hasattr(tc, "function") and tc.function:
            if hasattr(tc.function, "name") and tc.function.name:
                entry["name"] = tc.function.name

    @staticmethod
    def extract_arguments_delta(tc: Any) -> str | None:
        """Extract the arguments delta string from a tool-call chunk.

        Args:
            tc: A tool-call delta from a streaming chunk.

        Returns:
            The arguments fragment, or ``None`` if not present.
        """
        if hasattr(tc, "function") and tc.function:
            return getattr(tc.function, "arguments", None) or None
        return None
