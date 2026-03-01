"""
Unified LLM Service using LiteLLM for multi-provider support.

This module provides a single, provider-agnostic LLM service that leverages LiteLLM
to support any LLM provider (OpenAI, Anthropic, Google, Azure, Ollama, etc.)
through model string prefixes.

Key features:
- Provider-agnostic: Provider is determined by model string prefix (e.g., "anthropic/", "azure/")
- Model alias resolution from YAML configuration
- Per-model default parameters with merge semantics
- Configurable retry logic with exponential backoff
- Streaming support for real-time token delivery
- Optional file-based tracing

Configuration loading and model resolution are handled by ``LLMConfigLoader``.
Response parsing and normalization are handled by ``LLMResponseParser``.

Supported providers (via LiteLLM):
- OpenAI: "gpt-4.1", "gpt-4.1-mini" (no prefix needed)
- Anthropic: "anthropic/claude-sonnet-4-20250514"
- Google: "gemini/gemini-2.5-pro"
- Azure OpenAI: "azure/<deployment-name>"
- Ollama: "ollama/llama3"
- Any OpenAI-compatible API: "openai/<model>" with api_base override

Environment variables are read natively by LiteLLM per provider:
- OpenAI: OPENAI_API_KEY
- Anthropic: ANTHROPIC_API_KEY
- Google: GEMINI_API_KEY
- Azure: AZURE_API_KEY, AZURE_API_BASE, AZURE_API_VERSION
"""

import asyncio
import json
import logging
import os
import time
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

# Suppress LiteLLM verbose logging before import
os.environ.setdefault("LITELLM_LOG_LEVEL", "ERROR")
os.environ.setdefault("LITELLM_LOGGING", "off")
os.environ.setdefault("HTTPX_LOG_LEVEL", "warning")

# Map AZURE_OPENAI_* to AZURE_* for LiteLLM compatibility.
# LiteLLM expects AZURE_API_KEY, AZURE_API_BASE, AZURE_API_VERSION.
# Many projects use AZURE_OPENAI_API_KEY, AZURE_OPENAI_ENDPOINT (Microsoft convention).
# Without this, api_base=None causes: "argument of type 'NoneType' is not iterable".
if not os.environ.get("AZURE_API_KEY") and os.environ.get("AZURE_OPENAI_API_KEY"):
    os.environ["AZURE_API_KEY"] = os.environ["AZURE_OPENAI_API_KEY"]
if not os.environ.get("AZURE_API_BASE") and os.environ.get("AZURE_OPENAI_ENDPOINT"):
    endpoint = os.environ["AZURE_OPENAI_ENDPOINT"].rstrip("/")
    os.environ["AZURE_API_BASE"] = f"{endpoint}/"
if not os.environ.get("AZURE_API_VERSION") and os.environ.get("AZURE_OPENAI_API_VERSION"):
    os.environ["AZURE_API_VERSION"] = os.environ["AZURE_OPENAI_API_VERSION"]

for _ln in ["LiteLLM", "litellm", "httpcore", "httpx", "aiohttp", "openai"]:
    logging.getLogger(_ln).setLevel(logging.ERROR)

import aiofiles  # noqa: E402
import litellm  # noqa: E402
import structlog  # noqa: E402
import yaml  # noqa: E402

from taskforce.infrastructure.llm.llm_config_loader import (  # noqa: E402
    LLMConfigLoader,
    RetryPolicy,
)
from taskforce.infrastructure.llm.llm_response_parser import LLMResponseParser  # noqa: E402

litellm.suppress_debug_info = True
litellm.drop_params = True

logger = structlog.get_logger(__name__)

# Error type names that indicate transient failures worth retrying
_RETRYABLE_ERROR_TYPES = frozenset(
    {"RateLimitError", "APIConnectionError", "Timeout", "ServiceUnavailableError"}
)

# Keywords in error messages that indicate transient failures
_RETRYABLE_KEYWORDS = ("rate limit", "timeout", "503", "502", "429", "overloaded")

# Keywords that indicate permanent failures (never retry)
_NON_RETRYABLE_KEYWORDS = (
    "invalid api key",
    "authentication",
    "not found",
    "invalid model",
    "invalid request",
)


class LiteLLMService:
    """
    Provider-agnostic LLM service powered by LiteLLM.

    Supports any provider that LiteLLM supports through model string prefixes.
    Implements LLMProviderProtocol for dependency injection.

    Configuration loading is delegated to ``LLMConfigLoader`` and response
    parsing to ``LLMResponseParser``.  Config attributes (``models``,
    ``default_model``, ``routing_config``, etc.) are exposed as properties
    that delegate to the internal config loader, preserving the existing
    public interface.

    Args:
        config_path: Path to YAML configuration file.

    Raises:
        FileNotFoundError: If config file doesn't exist (on first access).
        ValueError: If config is invalid (empty or missing models section).
    """

    def __init__(self, config_path: str = "src/taskforce/configs/llm_config.yaml") -> None:
        self.logger = structlog.get_logger(__name__)
        self._config = LLMConfigLoader(config_path)
        self._parser = LLMResponseParser()

    # ------------------------------------------------------------------
    # Config attribute delegation — preserve existing public interface
    # ------------------------------------------------------------------

    @property
    def default_model(self) -> str:
        """Default model alias from configuration."""
        return self._config.default_model

    @default_model.setter
    def default_model(self, value: str) -> None:
        self._config.default_model = value

    @property
    def models(self) -> dict[str, str]:
        """Model alias to LiteLLM model string mapping."""
        return self._config.models

    @models.setter
    def models(self, value: dict[str, str]) -> None:
        self._config.models = value

    @property
    def model_params(self) -> dict[str, dict[str, Any]]:
        """Per-model parameter overrides."""
        return self._config.model_params

    @model_params.setter
    def model_params(self, value: dict[str, dict[str, Any]]) -> None:
        self._config.model_params = value

    @property
    def default_params(self) -> dict[str, Any]:
        """Default parameters applied to all models."""
        return self._config.default_params

    @default_params.setter
    def default_params(self, value: dict[str, Any]) -> None:
        self._config.default_params = value

    @property
    def retry_policy(self) -> RetryPolicy:
        """Retry policy configuration."""
        return self._config.retry_policy

    @retry_policy.setter
    def retry_policy(self, value: RetryPolicy) -> None:
        self._config.retry_policy = value

    @property
    def logging_config(self) -> dict[str, Any]:
        """Logging configuration from YAML."""
        return self._config.logging_config

    @logging_config.setter
    def logging_config(self, value: dict[str, Any]) -> None:
        self._config.logging_config = value

    @property
    def tracing_config(self) -> dict[str, Any]:
        """Tracing configuration from YAML."""
        return self._config.tracing_config

    @tracing_config.setter
    def tracing_config(self, value: dict[str, Any]) -> None:
        self._config.tracing_config = value

    @property
    def routing_config(self) -> dict[str, Any]:
        """LLM routing configuration from YAML."""
        return self._config.routing_config

    @routing_config.setter
    def routing_config(self, value: dict[str, Any]) -> None:
        self._config.routing_config = value

    # ------------------------------------------------------------------
    # Config loading delegation
    # ------------------------------------------------------------------

    async def _ensure_config_loaded(self) -> None:
        """Ensure configuration is loaded, using async I/O if not yet loaded.

        Safe to call multiple times; only the first call performs I/O.
        """
        await self._config.ensure_config_loaded()

    # ------------------------------------------------------------------
    # Request preparation (delegates to config loader for resolution)
    # ------------------------------------------------------------------

    def _prepare_request(
        self,
        messages: list[dict[str, Any]],
        model: str | None,
        tools: list[dict[str, Any]] | None,
        tool_choice: str | dict[str, Any] | None,
        **kwargs: Any,
    ) -> tuple[str, str, dict[str, Any]]:
        """Build LiteLLM request kwargs from caller arguments.

        Returns:
            Tuple of (alias, resolved_model, litellm_kwargs).
        """
        alias = model or self._config.default_model
        resolved_model = self._config.resolve_model(model)
        params = self._config.get_params(alias, **kwargs)

        litellm_kwargs: dict[str, Any] = {
            "model": resolved_model,
            "messages": messages,
            "timeout": self._config.retry_policy.timeout,
            "drop_params": True,
            **params,
        }

        if tools:
            litellm_kwargs["tools"] = tools
            litellm_kwargs["tool_choice"] = tool_choice or "auto"

        return alias, resolved_model, litellm_kwargs

    # ------------------------------------------------------------------
    # Completion with retry logic
    # ------------------------------------------------------------------

    async def _attempt_completion(
        self,
        litellm_kwargs: dict[str, Any],
        resolved_model: str,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None,
        attempt: int,
    ) -> dict[str, Any]:
        """Execute a single LLM completion attempt.

        Args:
            litellm_kwargs: Prepared kwargs for ``litellm.acompletion``.
            resolved_model: Resolved model string for logging.
            messages: Original messages for tracing.
            tools: Original tools list for logging.
            attempt: Current attempt number (1-based).

        Returns:
            Normalized response dict on success.
        """
        start_time = time.time()

        self.logger.info(
            "llm_completion_started",
            model=resolved_model,
            attempt=attempt,
            message_count=len(messages),
            tools_count=len(tools) if tools else 0,
        )

        response = await litellm.acompletion(**litellm_kwargs)
        latency_ms = int((time.time() - start_time) * 1000)
        result = LLMResponseParser.parse_response(response, resolved_model, latency_ms)

        self._log_completion_success(result, resolved_model, latency_ms)
        self._trace_success(messages, result, resolved_model, latency_ms)

        return result

    def _log_completion_success(self, result: dict[str, Any], model: str, latency_ms: int) -> None:
        """Log successful completion metrics if token logging is enabled."""
        if self._config.logging_config.get("log_token_usage", True):
            self.logger.info(
                "llm_completion_success",
                model=model,
                tokens=result.get("usage", {}).get("total_tokens", 0),
                latency_ms=latency_ms,
                tool_calls_count=len(result.get("tool_calls") or []),
            )

    def _trace_success(
        self,
        messages: list[dict[str, Any]],
        result: dict[str, Any],
        model: str,
        latency_ms: int,
    ) -> None:
        """Fire-and-forget trace of a successful completion."""
        asyncio.create_task(
            self._trace_interaction(
                messages=messages,
                response_content=result.get("content"),
                model=model,
                token_stats=result.get("usage", {}),
                latency_ms=latency_ms,
                success=True,
            )
        )

    def _trace_failure(
        self,
        messages: list[dict[str, Any]],
        model: str,
        latency_ms: int,
        error: str,
    ) -> None:
        """Fire-and-forget trace of a failed completion."""
        asyncio.create_task(
            self._trace_interaction(
                messages=messages,
                response_content=None,
                model=model,
                token_stats={},
                latency_ms=latency_ms,
                success=False,
                error=error,
            )
        )

    async def _handle_retry_or_fail(
        self,
        error: Exception,
        attempt: int,
        resolved_model: str,
        messages: list[dict[str, Any]],
        start_time: float,
    ) -> bool:
        """Decide whether to retry or record failure after an exception.

        Returns:
            True if the caller should retry, False if it should break.
        """
        is_last = attempt >= self._config.retry_policy.max_attempts - 1
        if not is_last and self._should_retry(error):
            backoff_time = self._config.retry_policy.backoff_multiplier**attempt
            self.logger.warning(
                "llm_completion_retry",
                model=resolved_model,
                error_type=type(error).__name__,
                attempt=attempt + 1,
                backoff_seconds=backoff_time,
            )
            await asyncio.sleep(backoff_time)
            return True

        self.logger.error(
            "llm_completion_failed",
            model=resolved_model,
            error_type=type(error).__name__,
            error=str(error)[:200],
            attempts=attempt + 1,
        )
        latency_ms = int((time.time() - start_time) * 1000)
        self._trace_failure(messages, resolved_model, latency_ms, str(error))
        return False

    async def complete(
        self,
        messages: list[dict[str, Any]],
        model: str | None = None,
        tools: list[dict[str, Any]] | None = None,
        tool_choice: str | dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Perform LLM chat completion with retry logic and tool calling support.

        Args:
            messages: List of message dicts with 'role' and 'content'.
            model: Model alias or None for default.
            tools: Optional tool definitions in OpenAI function calling format.
            tool_choice: Optional tool choice strategy ("auto", "none", "required").
            **kwargs: Additional parameters (temperature, max_tokens, etc.).

        Returns:
            Dict with success, content, tool_calls, usage, model, latency_ms.
            On failure: success=False, error, error_type.
        """
        await self._ensure_config_loaded()
        _, resolved_model, litellm_kwargs = self._prepare_request(
            messages, model, tools, tool_choice, **kwargs
        )

        last_error: Exception | None = None
        for attempt in range(self._config.retry_policy.max_attempts):
            start_time = time.time()
            try:
                return await self._attempt_completion(
                    litellm_kwargs, resolved_model, messages, tools, attempt + 1
                )
            except Exception as e:
                last_error = e
                should_retry = await self._handle_retry_or_fail(
                    e, attempt, resolved_model, messages, start_time
                )
                if not should_retry:
                    break

        return {
            "success": False,
            "error": str(last_error),
            "error_type": type(last_error).__name__ if last_error else "Unknown",
            "model": resolved_model,
        }

    # ------------------------------------------------------------------
    # JSON completion (convenience wrapper)
    # ------------------------------------------------------------------

    async def complete_json(
        self,
        messages: list[dict[str, Any]] | None = None,
        prompt: str | None = None,
        system_prompt: str | None = None,
        model: str | None = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Complete with JSON response format and parse the result.

        Accepts either ``messages`` (chat-style) or ``prompt``/``system_prompt``
        (convenience style).  Returns the parsed JSON object on success, or a
        ``{"success": False, ...}`` dict on failure.

        Args:
            messages: Chat messages (takes precedence over prompt).
            prompt: Single user prompt (used when messages is None).
            system_prompt: Optional system prompt (used with prompt).
            model: Model alias or None for default.
            **kwargs: Additional parameters (temperature, etc.).

        Returns:
            Parsed JSON dict from the LLM response.
        """
        if messages is None:
            messages = []
            if system_prompt:
                messages.append({"role": "system", "content": system_prompt})
            if prompt:
                messages.append({"role": "user", "content": prompt})

        kwargs.setdefault("response_format", {"type": "json_object"})
        result = await self.complete(messages=messages, model=model, **kwargs)

        if not result.get("success"):
            return result

        try:
            parsed = json.loads(result.get("content", "{}"))
            return {"success": True, "data": parsed, "model": result.get("model")}
        except (json.JSONDecodeError, TypeError) as exc:
            return {
                "success": False,
                "error": f"Failed to parse JSON from LLM response: {exc}",
                "error_type": "JSONDecodeError",
                "raw_content": result.get("content"),
            }

    # ------------------------------------------------------------------
    # Generate (convenience wrapper)
    # ------------------------------------------------------------------

    async def generate(
        self,
        prompt: str,
        context: dict[str, Any] | None = None,
        model: str | None = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Generate text from a single prompt (convenience wrapper).

        Args:
            prompt: The prompt text.
            context: Optional structured context (formatted as YAML).
            model: Model alias or None for default.
            **kwargs: Additional parameters passed to complete().

        Returns:
            Same as complete(), with additional 'generated_text' alias for 'content'.
        """
        if context:
            context_str = yaml.dump(context, default_flow_style=False)
            full_prompt = f"Context:\n{context_str}\n\nTask: {prompt}"
        else:
            full_prompt = prompt

        messages = [{"role": "user", "content": full_prompt}]
        result = await self.complete(messages, model=model, **kwargs)

        if result.get("success"):
            result["generated_text"] = result["content"]

        return result

    # ------------------------------------------------------------------
    # Streaming
    # ------------------------------------------------------------------

    def _prepare_stream_request(
        self,
        messages: list[dict[str, Any]],
        model: str | None,
        tools: list[dict[str, Any]] | None,
        tool_choice: str | dict[str, Any] | None,
        **kwargs: Any,
    ) -> tuple[str, dict[str, Any]]:
        """Build LiteLLM streaming request kwargs.

        Returns:
            Tuple of (resolved_model, litellm_kwargs) with ``stream=True``.
        """
        _, resolved_model, litellm_kwargs = self._prepare_request(
            messages, model, tools, tool_choice, **kwargs
        )
        litellm_kwargs["stream"] = True
        litellm_kwargs.setdefault("stream_options", {"include_usage": True})
        return resolved_model, litellm_kwargs

    def _build_stream_done_event(
        self,
        resolved_model: str,
        messages: list[dict[str, Any]],
        content_accumulated: str,
        current_tool_calls: dict[int, dict[str, Any]],
        start_time: float,
        usage: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Build the final ``done`` event and fire tracing task.

        Args:
            resolved_model: Resolved model string for logging.
            messages: Original messages for tracing.
            content_accumulated: Accumulated content from stream.
            current_tool_calls: Accumulated tool calls from stream.
            start_time: Request start time for latency calculation.
            usage: Token usage captured from the stream.

        Returns:
            The ``done`` event dict with ``usage``.
        """
        latency_ms = int((time.time() - start_time) * 1000)
        usage = usage or {}

        self.logger.info(
            "llm_stream_completed",
            model=resolved_model,
            latency_ms=latency_ms,
            tool_calls_count=len(current_tool_calls),
        )

        self._trace_success(
            messages,
            {"content": content_accumulated or None, "usage": usage},
            resolved_model,
            latency_ms,
        )

        return {"type": "done", "usage": usage}

    def _handle_stream_error(
        self,
        error: Exception,
        resolved_model: str,
        messages: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """Log and trace a stream-level error, returning the error event.

        Returns:
            An ``error`` event dict.
        """
        self.logger.error(
            "llm_stream_failed",
            model=resolved_model,
            error_type=type(error).__name__,
            error=str(error)[:200],
        )
        self._trace_failure(messages, resolved_model, 0, str(error))
        return {"type": "error", "message": str(error)}

    async def complete_stream(
        self,
        messages: list[dict[str, Any]],
        model: str | None = None,
        tools: list[dict[str, Any]] | None = None,
        tool_choice: str | dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> AsyncIterator[dict[str, Any]]:
        """Stream LLM completion with real-time token delivery.

        Yields normalized events as chunks arrive. Errors are yielded as
        events, NOT raised as exceptions.

        Args:
            messages: List of message dicts with 'role' and 'content'.
            model: Model alias or None for default.
            tools: Optional tool definitions.
            tool_choice: Optional tool choice strategy.
            **kwargs: Additional parameters.

        Yields:
            Event dicts: token, tool_call_start, tool_call_delta,
            tool_call_end, done, error.
        """
        await self._ensure_config_loaded()
        resolved_model, litellm_kwargs = self._prepare_stream_request(
            messages, model, tools, tool_choice, **kwargs
        )

        self.logger.debug(
            "llm_stream_started",
            model=resolved_model,
            message_count=len(messages),
            tools_count=len(tools) if tools else 0,
        )

        try:
            response = await litellm.acompletion(**litellm_kwargs)

            current_tool_calls: dict[int, dict[str, Any]] = {}
            content_accumulated = ""
            start_time = time.time()

            stream_usage: dict[str, Any] = {}

            async for chunk in response:
                # Capture usage from any chunk that carries it.
                # Some providers send usage on the last content chunk
                # (with choices), others send a final chunk with empty
                # choices — we handle both.
                chunk_usage = LLMResponseParser.extract_usage(chunk)
                if chunk_usage:
                    stream_usage = chunk_usage

                if not chunk.choices:
                    continue

                delta = chunk.choices[0].delta
                finish_reason = chunk.choices[0].finish_reason

                # Yield token content
                if hasattr(delta, "content") and delta.content:
                    content_accumulated += delta.content
                    yield {"type": "token", "content": delta.content}

                # Process tool-call deltas
                if hasattr(delta, "tool_calls") and delta.tool_calls:
                    for tc in delta.tool_calls:
                        async for evt in self._process_tool_call_delta(tc, current_tool_calls):
                            yield evt

                # Finish: emit tool_call_end for all accumulated tool calls
                if finish_reason:
                    for tc_idx, tc_data in current_tool_calls.items():
                        yield {
                            "type": "tool_call_end",
                            "id": tc_data["id"],
                            "name": tc_data["name"],
                            "arguments": tc_data["arguments"],
                            "index": tc_idx,
                        }

            yield self._build_stream_done_event(
                resolved_model,
                messages,
                content_accumulated,
                current_tool_calls,
                start_time,
                stream_usage,
            )

        except Exception as e:
            yield self._handle_stream_error(e, resolved_model, messages)

    async def _process_tool_call_delta(
        self,
        tc: Any,
        current_tool_calls: dict[int, dict[str, Any]],
    ) -> AsyncIterator[dict[str, Any]]:
        """Process a single tool-call delta from a stream chunk.

        Initializes the tool-call accumulator on first sight, updates metadata,
        and yields ``tool_call_start`` and ``tool_call_delta`` events.

        Args:
            tc: A tool-call delta object from the stream.
            current_tool_calls: Mutable accumulator dict (index -> tool data).

        Yields:
            ``tool_call_start`` and/or ``tool_call_delta`` event dicts.
        """
        idx = tc.index

        if idx not in current_tool_calls:
            entry = LLMResponseParser.init_tool_call_entry(tc)
            current_tool_calls[idx] = entry
            if entry["id"] or entry["name"]:
                yield {
                    "type": "tool_call_start",
                    "id": entry["id"],
                    "name": entry["name"],
                    "index": idx,
                }

        LLMResponseParser.update_tool_call_metadata(tc, current_tool_calls[idx])

        args_delta = LLMResponseParser.extract_arguments_delta(tc)
        if args_delta:
            current_tool_calls[idx]["arguments"] += args_delta
            yield {
                "type": "tool_call_delta",
                "id": current_tool_calls[idx]["id"],
                "arguments_delta": args_delta,
                "index": idx,
            }

    # ------------------------------------------------------------------
    # Retry logic
    # ------------------------------------------------------------------

    @staticmethod
    def _should_retry(error: Exception) -> bool:
        """Check if an error is transient and worth retrying.

        Args:
            error: The exception to evaluate.

        Returns:
            True if the error is likely transient.
        """
        error_msg = str(error).lower()

        # Non-retryable errors take priority
        if any(kw in error_msg for kw in _NON_RETRYABLE_KEYWORDS):
            return False

        # Check error type name
        if type(error).__name__ in _RETRYABLE_ERROR_TYPES:
            return True

        # Check error message keywords
        return any(kw in error_msg for kw in _RETRYABLE_KEYWORDS)

    # ------------------------------------------------------------------
    # Tracing
    # ------------------------------------------------------------------

    async def _trace_interaction(
        self,
        messages: list[dict[str, Any]],
        response_content: str | None,
        model: str,
        token_stats: dict[str, int],
        latency_ms: int,
        success: bool,
        error: str | None = None,
    ) -> None:
        """Trace LLM interaction to configured destinations."""
        if not self._config.tracing_config.get("enabled", False):
            return

        mode = self._config.tracing_config.get("mode", "file")
        trace_data = {
            "timestamp": datetime.now(UTC).isoformat(),
            "model": model,
            "messages": messages,
            "response": response_content,
            "usage": token_stats,
            "latency_ms": latency_ms,
            "success": success,
            "error": error,
        }

        if mode in ("file", "both"):
            await self._trace_to_file(trace_data)

    async def _trace_to_file(self, trace_data: dict[str, Any]) -> None:
        """Write trace data to JSONL file."""
        try:
            file_config = self._config.tracing_config.get("file_config", {})
            file_path = file_config.get("path", "traces/llm_traces.jsonl")

            path = Path(file_path)
            if not path.parent.exists():
                path.parent.mkdir(parents=True, exist_ok=True)

            async with aiofiles.open(path, mode="a", encoding="utf-8") as f:
                await f.write(json.dumps(trace_data) + "\n")

        except Exception as e:
            self.logger.error("trace_file_write_failed", error=str(e))
