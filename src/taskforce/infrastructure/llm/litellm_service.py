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
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

# Suppress LiteLLM verbose logging before import
os.environ.setdefault("LITELLM_LOG_LEVEL", "ERROR")
os.environ.setdefault("LITELLM_LOGGING", "off")
os.environ.setdefault("HTTPX_LOG_LEVEL", "warning")

for _ln in ["LiteLLM", "litellm", "httpcore", "httpx", "aiohttp", "openai"]:
    logging.getLogger(_ln).setLevel(logging.ERROR)

import aiofiles  # noqa: E402
import litellm  # noqa: E402
import structlog  # noqa: E402
import yaml  # noqa: E402

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


@dataclass
class RetryPolicy:
    """Retry policy configuration for LLM API calls."""

    max_attempts: int = 3
    backoff_multiplier: float = 2.0
    timeout: int = 60


class LiteLLMService:
    """
    Provider-agnostic LLM service powered by LiteLLM.

    Supports any provider that LiteLLM supports through model string prefixes.
    Implements LLMProviderProtocol for dependency injection.

    Configuration is loaded from a YAML file with model aliases, per-model
    parameters, and retry policy. The provider is determined entirely by the
    model string — no provider-specific code paths.

    Args:
        config_path: Path to YAML configuration file.

    Raises:
        FileNotFoundError: If config file doesn't exist.
        ValueError: If config is invalid (empty or missing models section).
    """

    def __init__(
        self, config_path: str = "src/taskforce_extensions/configs/llm_config.yaml"
    ) -> None:
        self.logger = structlog.get_logger(__name__)
        self._load_config(config_path)

        self.logger.info(
            "llm_service_initialized",
            default_model=self.default_model,
            model_aliases=list(self.models.keys()),
        )

    def _load_config(self, config_path: str) -> None:
        """Load and validate configuration from YAML file.

        Args:
            config_path: Path to YAML configuration file.

        Raises:
            FileNotFoundError: If config file doesn't exist.
            ValueError: If config is empty or missing models section.
        """
        config_file = Path(config_path)

        # Backward compatibility: try src/taskforce_extensions/configs/ as fallback
        if (
            not config_file.exists()
            and not config_file.is_absolute()
            and "configs/" in str(config_path)
        ):
            project_root = Path(__file__).parent.parent.parent.parent.parent
            new_path = project_root / "src" / "taskforce_extensions" / config_path
            if new_path.exists():
                config_file = new_path

        if not config_file.exists():
            raise FileNotFoundError(f"LLM config not found: {config_path}")

        with open(config_file, encoding="utf-8") as f:
            config = yaml.safe_load(f)

        if config is None:
            raise ValueError(f"Config file is empty or invalid: {config_path}")

        self.default_model: str = config.get("default_model", "main")
        self.models: dict[str, str] = config.get("models", {})
        self.model_params: dict[str, dict[str, Any]] = config.get("model_params", {})
        self.default_params: dict[str, Any] = config.get("default_params", {})

        if not self.models:
            raise ValueError("Config must define at least one model in 'models' section")

        # Retry policy
        retry_cfg = config.get("retry", config.get("retry_policy", {}))
        self.retry_policy = RetryPolicy(
            max_attempts=retry_cfg.get("max_attempts", 3),
            backoff_multiplier=retry_cfg.get("backoff_multiplier", 2.0),
            timeout=retry_cfg.get("timeout", 60),
        )

        # Logging preferences
        self.logging_config: dict[str, Any] = config.get("logging", {})

        # Tracing configuration
        self.tracing_config: dict[str, Any] = config.get("tracing", {})

        # Routing configuration (consumed by LLMRouter wrapper)
        self.routing_config: dict[str, Any] = config.get("routing", {})

    def _resolve_model(self, model_alias: str | None) -> str:
        """Resolve model alias to LiteLLM model string.

        If the alias exists in the models dict, returns the mapped value.
        Otherwise returns the alias as-is (allows direct model strings).

        Args:
            model_alias: Model alias (e.g., "main") or None for default.

        Returns:
            LiteLLM model string (e.g., "gpt-4.1", "anthropic/claude-sonnet-4-20250514").
        """
        alias = model_alias or self.default_model
        resolved = self.models.get(alias, alias)
        self.logger.debug("model_resolved", alias=alias, resolved=resolved)
        return resolved

    def _get_params(self, model_alias: str, **kwargs: Any) -> dict[str, Any]:
        """Build parameter dict by merging defaults, model params, and call kwargs.

        Merge order (later overrides earlier):
        1. default_params from config
        2. model_params for the resolved model or alias
        3. kwargs from the caller

        Args:
            model_alias: The alias used for lookup in model_params.
            **kwargs: Additional parameters from the caller.

        Returns:
            Merged parameter dictionary.
        """
        params: dict[str, Any] = {**self.default_params}

        # Try exact alias match first, then resolved model name
        resolved = self.models.get(model_alias, model_alias)
        if model_alias in self.model_params:
            params.update(self.model_params[model_alias])
        elif resolved in self.model_params:
            params.update(self.model_params[resolved])
        else:
            # Try prefix match (e.g., "gpt-4" matches "gpt-4-turbo")
            for key, model_cfg in self.model_params.items():
                if resolved.startswith(key):
                    params.update(model_cfg)
                    break

        # Caller kwargs override everything
        params.update({k: v for k, v in kwargs.items() if v is not None})
        return params

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
        alias = model or self.default_model
        resolved_model = self._resolve_model(model)
        params = self._get_params(alias, **kwargs)

        litellm_kwargs: dict[str, Any] = {
            "model": resolved_model,
            "messages": messages,
            "timeout": self.retry_policy.timeout,
            "drop_params": True,
            **params,
        }

        if tools:
            litellm_kwargs["tools"] = tools
            litellm_kwargs["tool_choice"] = tool_choice or "auto"

        last_error: Exception | None = None
        for attempt in range(self.retry_policy.max_attempts):
            try:
                start_time = time.time()

                self.logger.info(
                    "llm_completion_started",
                    model=resolved_model,
                    attempt=attempt + 1,
                    message_count=len(messages),
                    tools_count=len(tools) if tools else 0,
                )

                response = await litellm.acompletion(**litellm_kwargs)
                latency_ms = int((time.time() - start_time) * 1000)
                result = self._parse_response(response, resolved_model, latency_ms)

                if self.logging_config.get("log_token_usage", True):
                    self.logger.info(
                        "llm_completion_success",
                        model=resolved_model,
                        tokens=result.get("usage", {}).get("total_tokens", 0),
                        latency_ms=latency_ms,
                        tool_calls_count=len(result.get("tool_calls") or []),
                    )

                # Trace interaction asynchronously
                asyncio.create_task(
                    self._trace_interaction(
                        messages=messages,
                        response_content=result.get("content"),
                        model=resolved_model,
                        token_stats=result.get("usage", {}),
                        latency_ms=latency_ms,
                        success=True,
                    )
                )

                return result

            except Exception as e:
                last_error = e
                if attempt < self.retry_policy.max_attempts - 1 and self._should_retry(e):
                    backoff_time = self.retry_policy.backoff_multiplier**attempt
                    self.logger.warning(
                        "llm_completion_retry",
                        model=resolved_model,
                        error_type=type(e).__name__,
                        attempt=attempt + 1,
                        backoff_seconds=backoff_time,
                    )
                    await asyncio.sleep(backoff_time)
                else:
                    self.logger.error(
                        "llm_completion_failed",
                        model=resolved_model,
                        error_type=type(e).__name__,
                        error=str(e)[:200],
                        attempts=attempt + 1,
                    )

                    # Trace failure
                    asyncio.create_task(
                        self._trace_interaction(
                            messages=messages,
                            response_content=None,
                            model=resolved_model,
                            token_stats={},
                            latency_ms=int((time.time() - start_time) * 1000),
                            success=False,
                            error=str(e),
                        )
                    )
                    break

        return {
            "success": False,
            "error": str(last_error),
            "error_type": type(last_error).__name__ if last_error else "Unknown",
            "model": resolved_model,
        }

    def _parse_response(self, response: Any, model: str, latency_ms: int) -> dict[str, Any]:
        """Extract normalized result from LiteLLM response.

        Args:
            response: Raw LiteLLM response object.
            model: Resolved model string.
            latency_ms: Request latency in milliseconds.

        Returns:
            Normalized response dict with success, content, tool_calls, usage.
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
        tool_calls_raw = getattr(message, "tool_calls", None)
        tool_calls = None
        if tool_calls_raw:
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

        # Extract usage
        usage = self._extract_usage(response)

        return {
            "success": True,
            "content": content if content else None,
            "tool_calls": tool_calls,
            "usage": usage,
            "model": model,
            "latency_ms": latency_ms,
        }

    @staticmethod
    def _extract_usage(response: Any) -> dict[str, int]:
        """Extract token usage from response (handles both dict and object forms)."""
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
        alias = model or self.default_model
        resolved_model = self._resolve_model(model)
        params = self._get_params(alias, **kwargs)

        litellm_kwargs: dict[str, Any] = {
            "model": resolved_model,
            "messages": messages,
            "stream": True,
            "timeout": self.retry_policy.timeout,
            "drop_params": True,
            **params,
        }

        if tools:
            litellm_kwargs["tools"] = tools
            litellm_kwargs["tool_choice"] = tool_choice or "auto"

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

            async for chunk in response:
                if not chunk.choices:
                    continue

                delta = chunk.choices[0].delta
                finish_reason = chunk.choices[0].finish_reason

                # Token content
                if hasattr(delta, "content") and delta.content:
                    content_accumulated += delta.content
                    yield {"type": "token", "content": delta.content}

                # Tool calls
                if hasattr(delta, "tool_calls") and delta.tool_calls:
                    for tc in delta.tool_calls:
                        idx = tc.index

                        if idx not in current_tool_calls:
                            tool_id = getattr(tc, "id", None) or ""
                            tool_name = ""
                            if hasattr(tc, "function") and tc.function:
                                tool_name = getattr(tc.function, "name", None) or ""

                            current_tool_calls[idx] = {
                                "id": tool_id,
                                "name": tool_name,
                                "arguments": "",
                            }

                            if tool_id or tool_name:
                                yield {
                                    "type": "tool_call_start",
                                    "id": tool_id,
                                    "name": tool_name,
                                    "index": idx,
                                }

                        # Update id/name if provided in later chunks
                        if hasattr(tc, "id") and tc.id:
                            current_tool_calls[idx]["id"] = tc.id
                        if hasattr(tc, "function") and tc.function:
                            if hasattr(tc.function, "name") and tc.function.name:
                                current_tool_calls[idx]["name"] = tc.function.name

                        # Argument delta
                        if hasattr(tc, "function") and tc.function:
                            args_delta = getattr(tc.function, "arguments", None)
                            if args_delta:
                                current_tool_calls[idx]["arguments"] += args_delta
                                yield {
                                    "type": "tool_call_delta",
                                    "id": current_tool_calls[idx]["id"],
                                    "arguments_delta": args_delta,
                                    "index": idx,
                                }

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

            # Done event
            latency_ms = int((time.time() - start_time) * 1000)
            usage = self._extract_usage(response) if hasattr(response, "usage") else {}

            self.logger.info(
                "llm_stream_completed",
                model=resolved_model,
                latency_ms=latency_ms,
                tool_calls_count=len(current_tool_calls),
            )

            asyncio.create_task(
                self._trace_interaction(
                    messages=messages,
                    response_content=content_accumulated or None,
                    model=resolved_model,
                    token_stats=usage,
                    latency_ms=latency_ms,
                    success=True,
                )
            )

            yield {"type": "done", "usage": usage}

        except Exception as e:
            self.logger.error(
                "llm_stream_failed",
                model=resolved_model,
                error_type=type(e).__name__,
                error=str(e)[:200],
            )

            asyncio.create_task(
                self._trace_interaction(
                    messages=messages,
                    response_content=None,
                    model=resolved_model,
                    token_stats={},
                    latency_ms=0,
                    success=False,
                    error=str(e),
                )
            )

            yield {"type": "error", "message": str(e)}

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
        if not self.tracing_config.get("enabled", False):
            return

        mode = self.tracing_config.get("mode", "file")
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
            file_config = self.tracing_config.get("file_config", {})
            file_path = file_config.get("path", "traces/llm_traces.jsonl")

            path = Path(file_path)
            if not path.parent.exists():
                path.parent.mkdir(parents=True, exist_ok=True)

            async with aiofiles.open(path, mode="a", encoding="utf-8") as f:
                await f.write(json.dumps(trace_data) + "\n")

        except Exception as e:
            self.logger.error("trace_file_write_failed", error=str(e))
