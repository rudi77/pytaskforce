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
import re
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

# HTTP status codes that indicate permanent failures, matched with
# word boundaries so a transient 503 carrying e.g. "billing service
# degraded, retry in 30s" in the body does NOT trip the non-retryable
# branch (issue #191 sub-item c).
_NON_RETRYABLE_STATUS_PATTERN = re.compile(r"\b(401|402|403|404|410)\b")

# Specific phrases (substring match) that indicate permanent failures.
# Each phrase must be distinctive enough that no plausible retryable
# 5xx error body would contain it.
#
# Deliberately REMOVED in #191 sub-item (c) compared to the original
# _NON_RETRYABLE_KEYWORDS list:
#   - "billing"   — false-positive on "billing service degraded, retry
#     in 30s" (transient 503); 402 status code via the regex above
#     covers the real billing-rejection case.
#   - "forbidden" — false-positive on "forbidden character in stream,
#     retrying" (transient stream glitch); 403 via the regex covers
#     the real "forbidden by ACL" case.
#   - "not found" — too generic, false-positives on "tool 'X' not
#     found in registry" and similar; 404 via the regex covers the
#     real "model/endpoint not found" case.
#
# Auth + quota errors won't recover by retrying and burn through retry
# budget on a Butler daemon running 24/7 (issue #156), so they stay
# hard-classified as non-retryable here.
_NON_RETRYABLE_PHRASES = (
    "invalid api key",
    "authentication",
    "unauthorized",
    "permission denied",
    "invalid model",
    "invalid request",
    "insufficient_quota",
    "quota exceeded",
)

# Keywords that indicate content filter — recoverable by stripping history
_CONTENT_FILTER_KEYWORDS = ("content_policy", "contentpolicy", "content filter", "content manage")

# Markers of a structural / schema BadRequest (malformed messages array, e.g.
# a tool_call whose function.name is not a string). LiteLLM sometimes wraps
# these Azure 400s as ``ContentPolicyViolationError`` whose class name contains
# "contentpolicy" — without this guard they would be misclassified as content
# filters and trigger the (destructive) tool-result-stripping recovery loop
# (issue #455). A genuine Azure content-policy violation never references the
# request schema, so these markers do not overlap with real filter messages.
_STRUCTURAL_REQUEST_ERROR_MARKERS = (
    "invalid type for",
    "expected a string",
    "is not of type",
    "invalid_request_error",
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

    def __init__(
        self,
        config_path: str = "src/taskforce/configs/llm_config.yaml",
        *,
        recover_via_rephrase: bool = True,
        recovery_keep_last_n: int = 2,
    ) -> None:
        self.logger = structlog.get_logger(__name__)
        self._config = LLMConfigLoader(config_path)
        self._parser = LLMResponseParser()
        # ON by default since #274 — content-filter recovery escalates to
        # a neutral-rephrase stage if straight history-stripping also
        # fails. Costs one extra small LLM call ONLY on the failure path
        # (no overhead on successful streams). The recurring pain of
        # losing an entire run to an Azure content filter is bigger than
        # one summary-class call's worth of latency / cost.
        self._recover_via_rephrase = recover_via_rephrase
        self._recovery_keep_last_n = max(1, recovery_keep_last_n)
        # Local sanitizer for the recovery path — keeps the LLM-side
        # strip aware of tool-call/tool-reply pairing without leaking
        # MessageHistoryManager into this layer.
        from taskforce.core.domain.lean_agent_components.message_sanitizer import (
            MessageSanitizer,
        )

        self._sanitizer = MessageSanitizer(self.logger)

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

    @property
    def task_complexity_config(self) -> dict[str, Any]:
        """Task complexity classification config from YAML."""
        return self._config.task_complexity_config

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
        await self._trace_success(messages, result, resolved_model, latency_ms)

        return result

    def _log_completion_success(self, result: dict[str, Any], model: str, latency_ms: int) -> None:
        """Log successful completion metrics if token logging is enabled."""
        if self._config.logging_config.get("log_token_usage", True):
            self.logger.info(
                "llm_completion_success",
                model=model,
                actual_model=result.get("actual_model"),
                tokens=result.get("usage", {}).get("total_tokens", 0),
                latency_ms=latency_ms,
                tool_calls_count=len(result.get("tool_calls") or []),
            )

    async def _trace_success(
        self,
        messages: list[dict[str, Any]],
        result: dict[str, Any],
        model: str,
        latency_ms: int,
    ) -> None:
        """Trace a successful completion."""
        await self._trace_interaction(
            messages=messages,
            response_content=result.get("content"),
            model=model,
            token_stats=result.get("usage", {}),
            latency_ms=latency_ms,
            success=True,
        )

    async def _trace_failure(
        self,
        messages: list[dict[str, Any]],
        model: str,
        latency_ms: int,
        error: str,
    ) -> None:
        """Trace a failed completion."""
        await self._trace_interaction(
            messages=messages,
            response_content=None,
            model=model,
            token_stats={},
            latency_ms=latency_ms,
            success=False,
            error=error,
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
        await self._trace_failure(messages, resolved_model, latency_ms, str(error))
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

        # Content-policy recovery: strip old messages and retry once
        if last_error and self._is_content_filter_error(last_error):
            recovery_result = await self._recover_from_content_filter(
                messages, model, tools, tool_choice, resolved_model, **kwargs
            )
            if recovery_result is not None:
                return recovery_result

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
        content_accumulated: str,
        current_tool_calls: dict[int, dict[str, Any]],
        start_time: float,
        usage: dict[str, Any] | None = None,
        actual_model: str | None = None,
    ) -> dict[str, Any]:
        """Build the final ``done`` event dict (no I/O).

        Tracing is handled separately by the caller to avoid blocking
        the stream consumer.

        Args:
            resolved_model: Resolved model string for logging.
            content_accumulated: Accumulated content from stream.
            current_tool_calls: Accumulated tool calls from stream.
            start_time: Request start time for latency calculation.
            usage: Token usage captured from the stream.
            actual_model: The model string reported by the provider in stream chunks.

        Returns:
            The ``done`` event dict with ``usage``.
        """
        latency_ms = int((time.time() - start_time) * 1000)
        usage = usage or {}

        self.logger.info(
            "llm_stream_completed",
            model=resolved_model,
            actual_model=actual_model,
            latency_ms=latency_ms,
            tool_calls_count=len(current_tool_calls),
        )

        # Verify model match
        LLMResponseParser._check_model_mismatch(resolved_model, actual_model)

        return {"type": "done", "usage": usage}

    async def _handle_stream_error(
        self,
        error: Exception,
        resolved_model: str,
        messages: list[dict[str, Any]],
        *,
        force_content_filter: bool = False,
    ) -> dict[str, Any]:
        """Log and trace a stream-level error, returning the error event.

        Tags content-filter and other non-retryable errors so the consumer
        (e.g. the ReAct loop) can short-circuit instead of blindly retrying
        the same blocked request.

        Args:
            force_content_filter: When True, mark the event with
                ``error_kind="content_filter"`` even when ``error`` itself
                is not a content-filter exception. Used by the recovery
                code-path so that a transient secondary failure mid-recovery
                still surfaces the content-filter root cause to the user
                instead of a bare "etwas ging schief" fallback
                (issue #190 sub-item b).

        Returns:
            An ``error`` event dict with optional ``non_retryable`` /
            ``error_kind`` hints.
        """
        is_content_filter = force_content_filter or self._is_content_filter_error(error)
        self.logger.error(
            "llm_stream_failed",
            model=resolved_model,
            error_type=type(error).__name__,
            error=str(error)[:200],
            content_filter=is_content_filter,
            forced_content_filter=force_content_filter and not self._is_content_filter_error(error),
        )
        # Fire-and-forget: trace without blocking the stream consumer
        asyncio.create_task(self._trace_failure(messages, resolved_model, 0, str(error)))
        event: dict[str, Any] = {"type": "error", "message": str(error)}
        if is_content_filter:
            event["error_kind"] = "content_filter"
            event["non_retryable"] = True
        return event

    async def _run_stream_attempt(
        self,
        messages: list[dict[str, Any]],
        resolved_model: str,
        litellm_kwargs: dict[str, Any],
    ) -> AsyncIterator[dict[str, Any]]:
        """Consume one streaming completion attempt.

        Yields the same event types as :meth:`complete_stream` (``token``,
        ``tool_call_start``, ``tool_call_delta``, ``tool_call_end``, ``done``)
        and a single ``error`` event for chunk timeouts. Lets *any other*
        provider exception propagate so the orchestrating
        :meth:`complete_stream` can decide whether to retry on stripped
        history (content-filter recovery) or surface the error.
        """
        response = await litellm.acompletion(**litellm_kwargs)

        current_tool_calls: dict[int, dict[str, Any]] = {}
        content_accumulated = ""
        start_time = time.time()

        stream_usage: dict[str, Any] = {}
        stream_actual_model: str | None = None

        # Per-chunk timeout: detect mid-stream hangs where the API
        # stops sending data. Reuses the connection timeout value so
        # operators only need a single knob.
        stream_chunk_timeout = float(self._config.retry_policy.timeout)
        chunk_iter = response.__aiter__()
        while True:
            try:
                chunk = await asyncio.wait_for(chunk_iter.__anext__(), timeout=stream_chunk_timeout)
            except StopAsyncIteration:
                break
            except TimeoutError:
                latency_ms = int((time.time() - start_time) * 1000)
                self.logger.warning(
                    "llm_stream_chunk_timeout",
                    model=resolved_model,
                    timeout_seconds=stream_chunk_timeout,
                    latency_ms=latency_ms,
                    content_so_far=len(content_accumulated),
                )
                yield {
                    "type": "error",
                    "message": (
                        f"Stream timed out after {stream_chunk_timeout}s" " between chunks"
                    ),
                }
                asyncio.create_task(
                    self._trace_failure(
                        messages,
                        resolved_model,
                        latency_ms,
                        "stream_chunk_timeout",
                    )
                )
                return

            chunk_usage = LLMResponseParser.extract_usage(chunk)
            if chunk_usage:
                stream_usage = chunk_usage

            if stream_actual_model is None:
                chunk_model = LLMResponseParser.extract_actual_model_from_chunk(chunk)
                if chunk_model:
                    stream_actual_model = chunk_model

            if not chunk.choices:
                continue

            delta = chunk.choices[0].delta
            finish_reason = chunk.choices[0].finish_reason

            if hasattr(delta, "content") and delta.content:
                content_accumulated += delta.content
                yield {"type": "token", "content": delta.content}

            if hasattr(delta, "tool_calls") and delta.tool_calls:
                for tc in delta.tool_calls:
                    async for evt in self._process_tool_call_delta(tc, current_tool_calls):
                        yield evt

            if finish_reason:
                for tc_idx, tc_data in current_tool_calls.items():
                    yield {
                        "type": "tool_call_end",
                        "id": tc_data["id"],
                        "name": tc_data["name"],
                        "arguments": tc_data["arguments"],
                        "index": tc_idx,
                    }

        latency_ms = int((time.time() - start_time) * 1000)
        done_event = self._build_stream_done_event(
            resolved_model,
            content_accumulated,
            current_tool_calls,
            start_time,
            stream_usage,
            actual_model=stream_actual_model,
        )
        yield done_event

        asyncio.create_task(
            self._trace_success(
                messages,
                {"content": content_accumulated or None, "usage": stream_usage},
                resolved_model,
                latency_ms,
            )
        )

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

        Recovers transparently from Azure content-policy violations by
        stripping the conversation history (system + last 2 user/assistant
        messages, no tool messages) and retrying *once*. Mirrors the
        non-streaming :meth:`complete` recovery path so the streaming
        consumer benefits from the same protection. If recovery also
        fails, the original error is surfaced as an ``error`` event with
        ``error_kind=content_filter`` and ``non_retryable=True`` so the
        ReAct loop knows to abort.

        Args:
            messages: List of message dicts with 'role' and 'content'.
            model: Model alias or None for default.
            tools: Optional tool definitions.
            tool_choice: Optional tool choice strategy.
            **kwargs: Additional parameters.

        Yields:
            Event dicts: token, tool_call_start, tool_call_delta,
            tool_call_end, done, error, stream_restart. A
            ``stream_restart`` event is emitted before each
            content-filter recovery retry so consumers that accumulate
            tokens can discard the partial output from the failed
            attempt and only retain tokens from the successful retry.
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
            async for event in self._run_stream_attempt(messages, resolved_model, litellm_kwargs):
                yield event
            return
        except Exception as primary_error:
            if not self._is_content_filter_error(primary_error):
                error_event = await self._handle_stream_error(
                    primary_error, resolved_model, messages
                )
                yield error_event
                return

            # Multi-stage content-filter recovery. Each stage rebuilds
            # the message list with progressively more aggressive
            # context stripping and re-streams once. The trigger
            # usually sits in older tool-result chunks (e.g. web-fetch
            # snippets), not the latest user turn — so the cheaper
            # stages run first.
            stages: list[tuple[str, list[dict[str, Any]]]] = []

            tool_only = self._strip_messages_for_content_recovery(
                messages, mode="tool_results_only"
            )
            if len(tool_only) < len(messages):
                stages.append(("tool_results_only", tool_only))

            aggressive = self._strip_messages_for_content_recovery(messages, mode="aggressive")
            if len(aggressive) < len(messages) and (
                not stages or len(aggressive) < len(stages[-1][1])
            ):
                stages.append(("aggressive", aggressive))

            if not stages:
                error_event = await self._handle_stream_error(
                    primary_error, resolved_model, messages
                )
                yield error_event
                return

            last_recovery_error: Exception | None = None
            for stage_name, candidate in stages:
                self.logger.warning(
                    "llm_stream_content_filter_recovery",
                    stage=stage_name,
                    original_messages=len(messages),
                    stripped_messages=len(candidate),
                    model=resolved_model,
                )
                _, recovery_kwargs = self._prepare_stream_request(
                    candidate, model, tools, tool_choice, **kwargs
                )
                # Signal consumers (UI / ReAct loop) to discard any
                # tokens accumulated from the failed attempt before the
                # retry tokens land. Without this, half-completion
                # fragments and the fresh response get concatenated.
                yield {
                    "type": "stream_restart",
                    "reason": "content_filter",
                    "stage": stage_name,
                }
                try:
                    async for event in self._run_stream_attempt(
                        candidate, resolved_model, recovery_kwargs
                    ):
                        yield event
                    self.logger.info(
                        "llm_stream_content_filter_recovery_success",
                        stage=stage_name,
                        model=resolved_model,
                    )
                    return
                except Exception as recovery_error:
                    last_recovery_error = recovery_error
                    self.logger.warning(
                        "llm_stream_content_filter_recovery_stage_failed",
                        stage=stage_name,
                        model=resolved_model,
                        error=str(recovery_error)[:200],
                    )
                    if not self._is_content_filter_error(recovery_error):
                        # A non-filter error means recovery itself
                        # broke; do not keep escalating. The user-visible
                        # root cause is still content_filter — we entered
                        # this loop because the primary attempt got
                        # filtered — so flag it as such even though the
                        # proximate exception is e.g. a TimeoutError.
                        # Without ``force_content_filter`` the consumer
                        # would render the generic "etwas ging schief"
                        # fallback instead of the actionable filter
                        # message (issue #190 sub-item b).
                        error_event = await self._handle_stream_error(
                            recovery_error,
                            resolved_model,
                            candidate,
                            force_content_filter=True,
                        )
                        yield error_event
                        return

            # Fallback for *output*-side filter triggers: the LLM may
            # be producing a tool_call whose arguments hit the content
            # policy (e.g. a shell command, web-search query, or
            # generated text inside tool args). History-stripping
            # cannot fix that — but disabling tools forces a text-only
            # response that cannot carry policy-flagged tool payloads.
            # Only run when tools were originally provided AND at
            # least one strip stage was attempted (so we know the
            # primary error is genuinely content-filter).
            if tools and stages:
                base = stages[-1][1]
                _, no_tools_kwargs = self._prepare_stream_request(base, model, None, None, **kwargs)
                self.logger.warning(
                    "llm_stream_content_filter_recovery",
                    stage="no_tools",
                    original_messages=len(messages),
                    stripped_messages=len(base),
                    model=resolved_model,
                )
                yield {
                    "type": "stream_restart",
                    "reason": "content_filter",
                    "stage": "no_tools",
                }
                try:
                    async for event in self._run_stream_attempt(
                        base, resolved_model, no_tools_kwargs
                    ):
                        yield event
                    self.logger.info(
                        "llm_stream_content_filter_recovery_success",
                        stage="no_tools",
                        model=resolved_model,
                    )
                    return
                except Exception as recovery_error:
                    last_recovery_error = recovery_error
                    self.logger.warning(
                        "llm_stream_content_filter_recovery_stage_failed",
                        stage="no_tools",
                        model=resolved_model,
                        error=str(recovery_error)[:200],
                    )
                    if not self._is_content_filter_error(recovery_error):
                        # Same reasoning as the strip-stage branch: keep
                        # the content_filter classification even when the
                        # proximate failure is something else.
                        error_event = await self._handle_stream_error(
                            recovery_error,
                            resolved_model,
                            base,
                            force_content_filter=True,
                        )
                        yield error_event
                        return

            # Optional final stage: rephrase the user turn neutrally
            # and try once more. Off by default — costs one extra
            # small LLM call and changes the user's wording.
            if self._recover_via_rephrase and stages:
                base = stages[-1][1]
                rephrased = await self._rephrase_user_message_for_recovery(base, resolved_model)
                if rephrased is not None:
                    self.logger.warning(
                        "llm_stream_content_filter_recovery",
                        stage="rephrase",
                        original_messages=len(messages),
                        stripped_messages=len(rephrased),
                        model=resolved_model,
                    )
                    _, recovery_kwargs = self._prepare_stream_request(
                        rephrased, model, tools, tool_choice, **kwargs
                    )
                    yield {
                        "type": "stream_restart",
                        "reason": "content_filter",
                        "stage": "rephrase",
                    }
                    try:
                        async for event in self._run_stream_attempt(
                            rephrased, resolved_model, recovery_kwargs
                        ):
                            yield event
                        self.logger.info(
                            "llm_stream_content_filter_recovery_success",
                            stage="rephrase",
                            model=resolved_model,
                        )
                        return
                    except Exception as recovery_error:
                        last_recovery_error = recovery_error
                        self.logger.warning(
                            "llm_stream_content_filter_recovery_stage_failed",
                            stage="rephrase",
                            model=resolved_model,
                            error=str(recovery_error)[:200],
                        )

            self.logger.error(
                "llm_stream_content_filter_recovery_failed",
                model=resolved_model,
                error=str(last_recovery_error or primary_error)[:200],
            )
            # Surface the *recovery* failure so the ReAct loop sees
            # the same content_filter signal and aborts cleanly. Force
            # the content_filter classification — even if rephrase
            # blew up with a non-filter error (e.g. transient timeout),
            # the user-visible root cause is content_filter and we want
            # the actionable filter message, not the generic fallback
            # (issue #190 sub-item b).
            error_event = await self._handle_stream_error(
                last_recovery_error or primary_error,
                resolved_model,
                stages[-1][1],
                force_content_filter=True,
            )
            yield error_event

    async def _process_tool_call_delta(
        self,
        tc: Any,
        current_tool_calls: dict[int, dict[str, Any]],
    ) -> AsyncIterator[dict[str, Any]]:
        """Process a single tool-call delta from a stream chunk.

        Initializes the tool-call accumulator on first sight, updates metadata,
        and yields ``tool_call_start`` and ``tool_call_delta`` events.

        ``tool_call_start`` is emitted as soon as we know the tool's ``id`` or
        ``name``, even if that information arrives in a later delta than the
        first one for the same ``index`` (issue #155 — Telegram action gap).
        Without this, a provider that streams a tool call as
        ``index+arguments`` first and ``id+name`` second would never produce
        a ``tool_call_start`` event, causing the consumer in
        :func:`taskforce.core.domain.planning.react_loop._react_loop` to drop
        every ``tool_call_delta`` / ``tool_call_end`` for that index and the
        tool would silently never run — the agent would commit to an action
        in chat without firing the matching tool.

        Args:
            tc: A tool-call delta object from the stream.
            current_tool_calls: Mutable accumulator dict (index -> tool data).

        Yields:
            ``tool_call_start`` and/or ``tool_call_delta`` event dicts.
        """
        idx = tc.index

        if idx not in current_tool_calls:
            entry = LLMResponseParser.init_tool_call_entry(tc)
            entry["start_emitted"] = False
            current_tool_calls[idx] = entry

        LLMResponseParser.update_tool_call_metadata(tc, current_tool_calls[idx])

        # Emit ``tool_call_start`` the first time we have id or name — which
        # may be on the *first* delta for this index, or on a later one if
        # the provider front-loaded the arguments.
        entry = current_tool_calls[idx]
        if not entry.get("start_emitted") and (entry["id"] or entry["name"]):
            entry["start_emitted"] = True
            yield {
                "type": "tool_call_start",
                "id": entry["id"],
                "name": entry["name"],
                "index": idx,
            }

        args_delta = LLMResponseParser.extract_arguments_delta(tc)
        if args_delta:
            entry["arguments"] += args_delta
            yield {
                "type": "tool_call_delta",
                "id": entry["id"],
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

        # Non-retryable status codes take priority — word-boundary
        # regex so a transient 503 carrying a 4xx-mentioning body
        # (e.g. log lines, retry advice) doesn't false-positive.
        if _NON_RETRYABLE_STATUS_PATTERN.search(error_msg):
            return False

        # Non-retryable phrase fallback — distinctive auth / quota
        # wording. Kept narrow on purpose (see _NON_RETRYABLE_PHRASES
        # comment) so spurious-keyword 5xx bodies stay retryable.
        if any(phrase in error_msg for phrase in _NON_RETRYABLE_PHRASES):
            return False

        # Check error type name
        if type(error).__name__ in _RETRYABLE_ERROR_TYPES:
            return True

        # Check error message keywords
        return any(kw in error_msg for kw in _RETRYABLE_KEYWORDS)

    @staticmethod
    def _is_content_filter_error(error: Exception) -> bool:
        """Check if an error is an Azure content-policy violation.

        Structural BadRequests (malformed messages array — e.g. a tool_call
        with a non-string ``function.name``) are explicitly excluded: LiteLLM
        may wrap them as ``ContentPolicyViolationError``, but stripping tool
        results does not fix a schema error — it just loops (issue #455).
        """
        error_msg = str(error).lower()
        if any(m in error_msg for m in _STRUCTURAL_REQUEST_ERROR_MARKERS):
            return False
        return any(kw in error_msg for kw in _CONTENT_FILTER_KEYWORDS)

    def _strip_messages_for_content_recovery(
        self,
        messages: list[dict[str, Any]],
        *,
        mode: str = "aggressive",
    ) -> list[dict[str, Any]]:
        """Strip conversation history to recover from content-filter blocks.

        Azure's content filter often triggers on accumulated tool results
        or long conversation histories — not on the latest user message.

        Modes:
          * ``"tool_results_only"`` — drop only ``role="tool"`` messages
            and assistant messages that carry ``tool_calls``. Cheaper
            first attempt that preserves multi-turn conversation flow.
          * ``"aggressive"`` (default) — keep system prompt plus the
            last ``recovery_keep_last_n`` plain user/assistant turns.
        """
        if not messages:
            return messages

        if mode == "tool_results_only":
            kept: list[dict[str, Any]] = []
            for msg in messages:
                role = msg.get("role")
                if role == "tool":
                    continue
                if role == "assistant" and msg.get("tool_calls"):
                    # An assistant turn whose only purpose was to call
                    # tools — without the matching tool replies it would
                    # be an orphaned tool_call, so drop it too.
                    continue
                kept.append(msg)
            # Defensive: if the input had pre-existing orphans (e.g. a
            # ``role="tool"`` message whose matching assistant turn was
            # dropped earlier), they could survive this strip in
            # principle. We don't keep tool messages here, so the only
            # remaining failure mode is an assistant message whose
            # ``tool_calls`` reference IDs that no longer have replies
            # — which we just guaranteed by dropping every tool reply.
            # ``drop_orphan_tool_messages`` covers the symmetric case
            # for callers that pass us already-stripped histories.
            return self._sanitizer.drop_orphan_tool_messages(kept)

        system = [m for m in messages if m.get("role") == "system"]
        non_system = [
            m
            for m in messages
            if m.get("role") in ("user", "assistant") and not m.get("tool_calls")
        ]
        keep = max(1, self._recovery_keep_last_n)
        recent = non_system[-keep:] if len(non_system) > keep else non_system
        return system + recent

    async def _rephrase_user_message_for_recovery(
        self,
        messages: list[dict[str, Any]],
        resolved_model: str,
    ) -> list[dict[str, Any]] | None:
        """Replace the latest user turn with a neutralised paraphrase.

        Final fallback when straight history-stripping cannot pass the
        content filter — typically because the user's mission text
        itself carries trigger language. Costs one small no-tools LLM
        call. Returns ``None`` when rephrasing is not possible (no
        user turn) or the rephrase call itself fails.
        """
        last_user_idx = next(
            (i for i in range(len(messages) - 1, -1, -1) if messages[i].get("role") == "user"),
            None,
        )
        if last_user_idx is None:
            return None
        original = messages[last_user_idx].get("content")
        if not isinstance(original, str) or not original.strip():
            return None

        rephrase_prompt = (
            "Reformulate the following user request in neutral, "
            "factual language suitable for downstream processing. "
            "Strip any politically loaded, violent, or weapons-related "
            "framing. Preserve the actual information goal. Reply "
            "with only the reformulated text, no preamble.\n\n"
            f"Request:\n{original.strip()}"
        )
        try:
            # Explicit phase metadata so observability hooks (and the
            # test suite) can recognise this as the recovery rephrase
            # call rather than a normal completion. The dynamic-LLM
            # router can also key on ``phase=filter_recovery_rephrase``
            # to route this to a cheap model in future.
            response = await litellm.acompletion(
                model=resolved_model,
                messages=[{"role": "user", "content": rephrase_prompt}],
                max_tokens=200,
                temperature=0.0,
                metadata={"phase": "filter_recovery_rephrase"},
            )
            new_text = response.choices[0].message.content
        except Exception as exc:  # noqa: BLE001
            self.logger.warning(
                "llm_content_filter_rephrase_failed",
                error=str(exc)[:200],
            )
            return None

        if not isinstance(new_text, str) or not new_text.strip():
            return None

        rebuilt = list(messages)
        rebuilt[last_user_idx] = {**messages[last_user_idx], "content": new_text.strip()}
        return rebuilt

    async def _recover_from_content_filter(
        self,
        messages: list[dict[str, Any]],
        model: str | None,
        tools: list[dict[str, Any]] | None,
        tool_choice: str | dict[str, Any] | None,
        resolved_model: str,
        **kwargs: Any,
    ) -> dict[str, Any] | None:
        """Attempt recovery from Azure content-policy violation.

        Mirrors the four-stage cascade used in the streaming path so a
        blocking ``complete()`` caller sees the same recovery shape as a
        ``complete_stream()`` caller. Stages, in order:

        1. ``tool_results_only`` — drop ``role="tool"`` and tool-call-only
           assistant turns (cheapest; the filter usually sits in older
           tool output).
        2. ``aggressive`` — keep system prompt plus the last
           ``recovery_keep_last_n`` plain user/assistant turns.
        3. ``no_tools`` — re-run on the most-stripped message list with
           ``tools=None``; only attempted when tools were originally
           supplied AND at least one strip stage shrank the history,
           because an output-side filter (e.g. flagged tool-call args)
           cannot be fixed by history stripping alone.
        4. ``rephrase`` — neutralise the last user turn via a small LLM
           call and retry once. Opt-out via ``recover_via_rephrase=False``.

        Returns the LLM result on the first successful stage, or
        ``None`` if every stage fails.
        """
        # Build the candidate list of history-stripping stages, mirroring
        # complete_stream's logic (each stage must shrink further than the
        # previous one to be worth attempting).
        stages: list[tuple[str, list[dict[str, Any]]]] = []

        tool_only = self._strip_messages_for_content_recovery(messages, mode="tool_results_only")
        if len(tool_only) < len(messages):
            stages.append(("tool_results_only", tool_only))

        aggressive = self._strip_messages_for_content_recovery(messages, mode="aggressive")
        if len(aggressive) < len(messages) and (not stages or len(aggressive) < len(stages[-1][1])):
            stages.append(("aggressive", aggressive))

        last_recovery_error: Exception | None = None

        for stage_name, candidate in stages:
            logger.warning(
                "llm_content_filter_recovery",
                stage=stage_name,
                original_messages=len(messages),
                stripped_messages=len(candidate),
                model=resolved_model,
            )
            _, _, litellm_kwargs = self._prepare_request(
                candidate, model, tools, tool_choice, **kwargs
            )
            try:
                result = await self._attempt_completion(
                    litellm_kwargs, resolved_model, candidate, tools, attempt=1
                )
                logger.info(
                    "llm_content_filter_recovery_success",
                    stage=stage_name,
                    model=resolved_model,
                )
                return result
            except Exception as recovery_error:
                last_recovery_error = recovery_error
                logger.warning(
                    "llm_content_filter_recovery_stage_failed",
                    stage=stage_name,
                    model=resolved_model,
                    error=str(recovery_error)[:200],
                )
                if not self._is_content_filter_error(recovery_error):
                    # Non-filter error during recovery means the pipeline
                    # itself broke; stop escalating. The user-visible root
                    # cause is still content_filter (we only entered this
                    # branch because the primary attempt got filtered), so
                    # callers/UI should still render the actionable filter
                    # message rather than the generic fallback.
                    return None

        # Stage 3: tools-off fallback. Output-side filter triggers (the
        # LLM emitting a flagged tool_call) cannot be fixed by stripping
        # the input history. Re-attempting without tools forces a plain
        # text response that cannot carry policy-flagged tool payloads.
        # Only run when tools were originally provided AND at least one
        # strip stage ran (so we know the primary error really was
        # content-filter, not a malformed request).
        if tools and stages:
            base = stages[-1][1]
            logger.warning(
                "llm_content_filter_recovery",
                stage="no_tools",
                original_messages=len(messages),
                stripped_messages=len(base),
                model=resolved_model,
            )
            _, _, no_tools_kwargs = self._prepare_request(base, model, None, None, **kwargs)
            try:
                result = await self._attempt_completion(
                    no_tools_kwargs, resolved_model, base, None, attempt=1
                )
                logger.info(
                    "llm_content_filter_recovery_success",
                    stage="no_tools",
                    model=resolved_model,
                )
                return result
            except Exception as recovery_error:
                last_recovery_error = recovery_error
                logger.warning(
                    "llm_content_filter_recovery_stage_failed",
                    stage="no_tools",
                    model=resolved_model,
                    error=str(recovery_error)[:200],
                )
                if not self._is_content_filter_error(recovery_error):
                    return None

        # Stage 4: rephrase the last user turn neutrally and retry once.
        # Off-switchable via recover_via_rephrase=False (costs one extra
        # small LLM call and changes the user's wording).
        if not self._recover_via_rephrase:
            logger.error(
                "llm_content_filter_recovery_failed",
                model=resolved_model,
                error=str(last_recovery_error)[:200] if last_recovery_error else None,
            )
            return None

        base = stages[-1][1] if stages else messages
        rephrased = await self._rephrase_user_message_for_recovery(base, resolved_model)
        if rephrased is None:
            logger.error(
                "llm_content_filter_recovery_failed",
                stage="rephrase",
                model=resolved_model,
                reason="no_rephrase_available",
            )
            return None

        logger.warning(
            "llm_content_filter_recovery",
            stage="rephrase",
            original_messages=len(messages),
            stripped_messages=len(rephrased),
            model=resolved_model,
        )
        _, _, litellm_kwargs = self._prepare_request(rephrased, model, tools, tool_choice, **kwargs)
        try:
            result = await self._attempt_completion(
                litellm_kwargs, resolved_model, rephrased, tools, attempt=1
            )
            logger.info(
                "llm_content_filter_recovery_success",
                stage="rephrase",
                model=resolved_model,
            )
            return result
        except Exception as recovery_error:
            logger.error(
                "llm_content_filter_recovery_failed",
                stage="rephrase",
                model=resolved_model,
                error=str(recovery_error)[:200],
            )
            return None

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
