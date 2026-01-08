"""
Zai LLM Service for centralized LLM interactions.

This module provides a dedicated service for Zai LLM API with support
for model-aware parameter mapping, retry logic, and configuration management.

Key features:
- Model alias resolution (main, fast, powerful)
- Configurable retry logic with exponential backoff
- Structured logging with structlog
- Streaming support for real-time token delivery
- Tool calling support (function calling)

Uses zai-sdk directly for API calls.
"""

import asyncio
import os
import time
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import structlog
import yaml

from taskforce.core.interfaces.llm import LLMProviderProtocol


@dataclass
class RetryPolicy:
    """Retry policy configuration for Zai API calls."""

    max_attempts: int = 3
    backoff_multiplier: float = 2.0
    timeout: float = 300.0
    connect_timeout: float = 8.0
    retry_on_errors: list[str] = field(default_factory=list)


class ZaiService(LLMProviderProtocol):
    """
    Zai LLM service implementing LLMProviderProtocol.

    Uses zai-sdk directly for API calls. Supports:
    - Multiple model aliases (main, fast, powerful)
    - Tool calling (function calling)
    - Streaming responses
    - Configurable retry logic

    Note: zai-sdk is synchronous, so all API calls are wrapped
    with asyncio.to_thread() to avoid blocking the event loop.
    """

    def __init__(self, config_path: str = "configs/llm_config.yaml"):
        """
        Initialize ZaiService with configuration.

        Args:
            config_path: Path to YAML configuration file

        Raises:
            FileNotFoundError: If config file doesn't exist
            ValueError: If config is invalid
        """
        self.logger = structlog.get_logger()
        self._load_config(config_path)
        self._initialize_client()

        self.logger.info(
            "zai_service_initialized",
            default_model=self.default_model,
            model_aliases=list(self.models.keys()),
        )

    def _load_config(self, config_path: str) -> None:
        """
        Load and validate configuration from YAML file.

        Args:
            config_path: Path to YAML configuration file

        Raises:
            FileNotFoundError: If config file doesn't exist
            ValueError: If config is invalid
        """
        config_file = Path(config_path)
        if not config_file.exists():
            raise FileNotFoundError(f"LLM config not found: {config_path}")

        with open(config_file, encoding="utf-8") as f:
            config = yaml.safe_load(f)

        if config is None:
            raise ValueError(f"Config file is empty or invalid: {config_path}")

        # Extract configuration sections
        self.default_model = config.get("default_model", "main")
        self.models = config.get("models", {})
        self.model_params = config.get("model_params", {})
        self.default_params = config.get("default_params", {})

        if not self.models:
            raise ValueError("Config must define at least one model in 'models' section")

        # Retry policy
        retry_config = config.get("retry_policy", {})
        self.retry_policy = RetryPolicy(
            max_attempts=retry_config.get("max_attempts", 3),
            backoff_multiplier=retry_config.get("backoff_multiplier", 2.0),
            timeout=retry_config.get("timeout", 300.0),
            connect_timeout=retry_config.get("connect_timeout", 8.0),
            retry_on_errors=retry_config.get("retry_on_errors", []),
        )

        # Logging preferences
        self.logging_config = config.get("logging", {})

        # Zai provider config
        provider_config = config.get("providers", {}).get("zai", {})
        self.api_key_env = provider_config.get("api_key_env", "ZAI_API_KEY")
        self.base_url = provider_config.get("base_url", "https://api.z.ai/api/paas/v4/")

        # Model mapping for Zai (optional, falls back to global models)
        self.zai_model_mapping = provider_config.get("model_mapping", {})

    def _initialize_client(self) -> None:
        """
        Initialize Zai client with credentials from environment.

        Raises:
            ImportError: If zai-sdk is not installed
        """
        try:
            from zai import ZaiClient
            import httpx
        except ImportError as e:
            raise ImportError(
                "zai-sdk is not installed. Install it with: pip install zai-sdk"
            ) from e

        api_key = os.getenv(self.api_key_env)

        if not api_key:
            self.logger.warning(
                "zai_api_key_missing",
                env_var=self.api_key_env,
                hint="Set environment variable for API access",
            )

        # Create client with custom configuration
        self.client = ZaiClient(
            api_key=api_key,
            base_url=self.base_url,
            timeout=httpx.Timeout(
                timeout=self.retry_policy.timeout,
                connect=self.retry_policy.connect_timeout,
            ),
            max_retries=0,  # Handle retries ourselves for consistency
        )

        self.logger.info(
            "zai_client_initialized",
            base_url=self.base_url,
            api_key_set=bool(api_key),
        )

    def _resolve_model(self, model_alias: str | None) -> str:
        """
        Resolve model alias to actual Zai model name.

        Args:
            model_alias: Model alias (e.g., "main", "fast") or None for default

        Returns:
            Actual Zai model name (e.g., "glm-4.7")
        """
        if model_alias is None:
            model_alias = self.default_model

        # First check Zai-specific model mapping
        if model_alias in self.zai_model_mapping:
            return str(self.zai_model_mapping[model_alias])

        # Fall back to global models mapping
        if model_alias in self.models:
            # For Zai, we need to map to Zai model names
            # If the global model is an OpenAI model, use the Zai mapping
            # Otherwise, return as-is (it might be a Zai model name directly)
            zai_model = self.zai_model_mapping.get(model_alias)
            if zai_model:
                return str(zai_model)
            global_model = self.models.get(model_alias)
            if global_model:
                return str(global_model)

        # Return as-is (might be a direct model name like "glm-4.7")
        return model_alias

    def _get_model_parameters(self, model: str) -> dict[str, Any]:
        """
        Get parameters for specific model.

        Args:
            model: Actual model name

        Returns:
            Model-specific parameters or defaults
        """
        # Check for exact model match
        if model in self.model_params:
            return dict(self.model_params[model])

        # Check for model family match
        for model_key, params in self.model_params.items():
            if model.startswith(model_key):
                return dict(params)

        # Fallback to defaults (filter to supported params)
        defaults = self.default_params.copy()
        # Zai supports standard parameters: temperature, max_tokens, top_p
        allowed = ["temperature", "max_tokens", "top_p"]
        return {k: v for k, v in defaults.items() if k in allowed}

    def _sanitize_messages_for_zai(
        self, messages: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        """
        Sanitize messages for ZAI API compatibility.

        ZAI API has stricter message format requirements than OpenAI:
        - Assistant messages with tool_calls must have content as string (not None)
        - Empty content should be "" not None

        Args:
            messages: List of message dicts

        Returns:
            Sanitized messages compatible with ZAI API
        """
        sanitized = []
        for msg in messages:
            msg_copy = msg.copy()
            # ZAI doesn't accept content: None for assistant messages
            if msg_copy.get("role") == "assistant":
                if msg_copy.get("content") is None:
                    # Set to empty string instead of None
                    msg_copy["content"] = ""
            sanitized.append(msg_copy)
        return sanitized

    async def complete(
        self,
        messages: list[dict[str, Any]],
        model: str | None = None,
        tools: list[dict[str, Any]] | None = None,
        tool_choice: str | dict[str, Any] | None = None,
        **kwargs,
    ) -> dict[str, Any]:
        """
        Perform Zai completion with retry logic and native tool calling support.

        Args:
            messages: List of message dicts with 'role' and 'content'
            model: Model alias or None (uses default)
            tools: Optional list of tool definitions in OpenAI function calling format
            tool_choice: Optional tool choice strategy ("auto", "none", "required")
            **kwargs: Additional parameters (temperature, max_tokens, etc.)

        Returns:
            Dict with:
            - success: bool
            - content: str | None (if no tool calls)
            - tool_calls: list[dict] | None (if model invoked tools)
            - usage: Dict with token counts
            - model: str - Actual model used
            - latency_ms: int
            - error: str (if failed)
            - error_type: str (if failed)
        """
        actual_model = self._resolve_model(model)
        base_params = self._get_model_parameters(actual_model)

        # Merge with provided kwargs (kwargs override base_params)
        merged_params = {**base_params, **kwargs}

        # Sanitize messages for ZAI API compatibility
        sanitized_messages = self._sanitize_messages_for_zai(messages)

        # Build API call kwargs
        api_kwargs: dict[str, Any] = {
            "model": actual_model,
            "messages": sanitized_messages,
        }

        # Add supported parameters
        for param in ["temperature", "max_tokens", "top_p"]:
            if param in merged_params:
                api_kwargs[param] = merged_params[param]

        # Zai API doesn't accept top_p >= 1.0
        if "top_p" in api_kwargs and api_kwargs["top_p"] >= 1.0:
            api_kwargs["top_p"] = 0.99

        # Add tools if provided
        if tools:
            api_kwargs["tools"] = tools
            if tool_choice:
                api_kwargs["tool_choice"] = tool_choice
            else:
                api_kwargs["tool_choice"] = "auto"

        # Retry logic
        for attempt in range(self.retry_policy.max_attempts):
            try:
                start_time = time.time()

                self.logger.info(
                    "zai_completion_started",
                    model=actual_model,
                    attempt=attempt + 1,
                    message_count=len(messages),
                    tools_count=len(tools) if tools else 0,
                )

                # zai-sdk is synchronous - run in thread pool
                response = await asyncio.to_thread(
                    self.client.chat.completions.create,
                    **api_kwargs,
                )

                # Extract response data
                # Note: For non-streaming calls, response is always Completion type
                message = response.choices[0].message  # type: ignore[union-attr]
                content = message.content

                # Extract tool_calls if present
                tool_calls = None
                if hasattr(message, "tool_calls") and message.tool_calls:
                    tool_calls = []
                    for tc in message.tool_calls:
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
                usage = response.usage  # type: ignore[union-attr]
                token_stats = {
                    "total_tokens": getattr(usage, "total_tokens", 0),
                    "prompt_tokens": getattr(usage, "prompt_tokens", 0),
                    "completion_tokens": getattr(usage, "completion_tokens", 0),
                }

                latency_ms = int((time.time() - start_time) * 1000)

                if self.logging_config.get("log_token_usage", True):
                    self.logger.info(
                        "zai_completion_success",
                        model=actual_model,
                        tokens=token_stats.get("total_tokens", 0),
                        latency_ms=latency_ms,
                        tool_calls_count=len(tool_calls) if tool_calls else 0,
                    )

                return {
                    "success": True,
                    "content": content,
                    "tool_calls": tool_calls,
                    "usage": token_stats,
                    "model": actual_model,
                    "latency_ms": latency_ms,
                }

            except Exception as e:
                error_type = type(e).__name__
                error_msg = str(e)

                # Check if should retry
                should_retry = attempt < self.retry_policy.max_attempts - 1 and any(
                    err_type in error_type or err_type in error_msg
                    for err_type in self.retry_policy.retry_on_errors
                )

                if should_retry:
                    backoff_time = self.retry_policy.backoff_multiplier**attempt

                    self.logger.warning(
                        "zai_completion_retry",
                        model=actual_model,
                        error_type=error_type,
                        attempt=attempt + 1,
                        backoff_seconds=backoff_time,
                    )
                    await asyncio.sleep(backoff_time)
                else:
                    self.logger.error(
                        "zai_completion_failed",
                        model=actual_model,
                        error_type=error_type,
                        error=error_msg[:200],
                        attempts=attempt + 1,
                    )

                    return {
                        "success": False,
                        "error": error_msg,
                        "error_type": error_type,
                        "model": actual_model,
                    }

        # Should not reach here, but handle anyway
        return {
            "success": False,
            "error": "Max retries exceeded",
            "model": actual_model,
        }

    async def generate(
        self,
        prompt: str,
        context: dict[str, Any] | None = None,
        model: str | None = None,
        **kwargs,
    ) -> dict[str, Any]:
        """
        Generate text from a single prompt (convenience wrapper around complete).

        Args:
            prompt: The prompt text
            context: Optional structured context to include
            model: Model alias or None (uses default)
            **kwargs: Additional parameters

        Returns:
            Same as complete(), with additional 'generated_text' field
        """
        # Format prompt with context if provided
        if context:
            context_str = yaml.dump(context, default_flow_style=False)
            full_prompt = f"""Context:
{context_str}

Task: {prompt}
"""
        else:
            full_prompt = prompt

        # Use complete() method
        messages = [{"role": "user", "content": full_prompt}]
        result = await self.complete(messages, model=model, **kwargs)

        # Alias 'content' to 'generated_text' for compatibility
        if result.get("success"):
            result["generated_text"] = result["content"]

        return result

    async def complete_stream(
        self,
        messages: list[dict[str, Any]],
        model: str | None = None,
        tools: list[dict[str, Any]] | None = None,
        tool_choice: str | dict[str, Any] | None = None,
        **kwargs,
    ) -> AsyncIterator[dict[str, Any]]:
        """
        Stream Zai completion with real-time token delivery.

        Yields normalized events as chunks arrive from the Zai API.
        Uses asyncio.Queue to stream tokens live from the synchronous SDK.
        Errors are yielded as events, NOT raised as exceptions.

        Args:
            messages: List of message dicts with 'role' and 'content'
            model: Model alias or None (uses default)
            tools: Optional list of tool definitions
            tool_choice: Optional tool choice strategy
            **kwargs: Additional parameters (temperature, max_tokens, etc.)

        Yields:
            Event dictionaries:
            - {"type": "token", "content": "..."} - Text chunk
            - {"type": "tool_call_start", "id": "...", "name": "...", "index": N}
            - {"type": "tool_call_delta", "id": "...", "arguments_delta": "...", "index": N}
            - {"type": "tool_call_end", "id": "...", "name": "...", "arguments": "...", "index": N}
            - {"type": "done", "usage": {...}} - Stream complete
            - {"type": "error", "message": "..."} - Error occurred
        """
        # Resolve model
        try:
            actual_model = self._resolve_model(model)
        except ValueError as e:
            self.logger.error("zai_stream_model_resolution_failed", error=str(e))
            yield {"type": "error", "message": str(e)}
            return

        base_params = self._get_model_parameters(actual_model)
        merged_params = {**base_params, **kwargs}

        # Sanitize messages for ZAI API compatibility
        sanitized_messages = self._sanitize_messages_for_zai(messages)

        # Build API call kwargs
        api_kwargs: dict[str, Any] = {
            "model": actual_model,
            "messages": sanitized_messages,
            "stream": True,
        }

        # Add supported parameters
        for param in ["temperature", "max_tokens", "top_p"]:
            if param in merged_params:
                api_kwargs[param] = merged_params[param]

        # Zai API doesn't accept top_p >= 1.0
        if "top_p" in api_kwargs and api_kwargs["top_p"] >= 1.0:
            api_kwargs["top_p"] = 0.99

        # Add tools if provided
        if tools:
            api_kwargs["tools"] = tools
            if tool_choice:
                api_kwargs["tool_choice"] = tool_choice
            else:
                api_kwargs["tool_choice"] = "auto"

        self.logger.debug(
            "zai_stream_started",
            model=actual_model,
            message_count=len(sanitized_messages),
            tools_count=len(tools) if tools else 0,
        )

        # Use queue for live streaming from sync SDK to async generator
        chunk_queue: asyncio.Queue[dict[str, Any] | None] = asyncio.Queue()
        stream_error: list[Exception] = []  # Mutable container for error from thread

        # Get event loop reference before starting thread
        loop = asyncio.get_running_loop()

        def stream_worker() -> None:
            """
            Worker function that runs in a thread.
            Iterates the synchronous stream and puts chunks on the queue.
            """
            try:
                # Create streaming response
                response = self.client.chat.completions.create(**api_kwargs)

                # Iterate and put each chunk on queue
                for chunk in response:
                    # Use call_soon_threadsafe to put on queue from thread
                    loop.call_soon_threadsafe(
                        chunk_queue.put_nowait, {"chunk": chunk}
                    )

                # Signal completion
                loop.call_soon_threadsafe(chunk_queue.put_nowait, None)

            except Exception as e:
                stream_error.append(e)
                # Signal error completion
                loop.call_soon_threadsafe(chunk_queue.put_nowait, None)

        try:
            start_time = time.time()

            # Start stream worker in thread pool
            stream_future = loop.run_in_executor(None, stream_worker)

            # Track tool calls across chunks
            current_tool_calls: dict[int, dict[str, Any]] = {}

            # Per-chunk timeout (60 seconds between chunks should be plenty)
            chunk_timeout = 60.0

            # Process chunks as they arrive
            while True:
                try:
                    # Wait for next chunk with timeout
                    item = await asyncio.wait_for(
                        chunk_queue.get(), timeout=chunk_timeout
                    )

                    # None signals end of stream
                    if item is None:
                        break

                    chunk = item["chunk"]

                    # Safety check for valid chunk structure
                    if not chunk.choices:
                        continue

                    delta = chunk.choices[0].delta
                    finish_reason = chunk.choices[0].finish_reason

                    # Handle content tokens
                    if hasattr(delta, "content") and delta.content:
                        self.logger.debug(
                            "zai_stream_token",
                            content_length=len(delta.content),
                        )
                        yield {"type": "token", "content": delta.content}

                    # Handle tool calls
                    if hasattr(delta, "tool_calls") and delta.tool_calls:
                        for tc in delta.tool_calls:
                            idx = tc.index

                            # New tool call starting
                            if idx not in current_tool_calls:
                                tool_id = getattr(tc, "id", "") or ""
                                tool_name = ""
                                if hasattr(tc, "function") and tc.function:
                                    tool_name = getattr(tc.function, "name", "") or ""

                                current_tool_calls[idx] = {
                                    "id": tool_id,
                                    "name": tool_name,
                                    "arguments": "",
                                }

                                # Only emit start if we have meaningful data
                                if tool_id or tool_name:
                                    self.logger.debug(
                                        "zai_stream_tool_call_start",
                                        tool_id=tool_id,
                                        tool_name=tool_name,
                                        index=idx,
                                    )
                                    yield {
                                        "type": "tool_call_start",
                                        "id": tool_id,
                                        "name": tool_name,
                                        "index": idx,
                                    }

                            # Update tool call id/name if provided in later chunks
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
                                    self.logger.debug(
                                        "zai_stream_tool_call_delta",
                                        tool_id=current_tool_calls[idx]["id"],
                                        delta_length=len(args_delta),
                                        index=idx,
                                    )
                                    yield {
                                        "type": "tool_call_delta",
                                        "id": current_tool_calls[idx]["id"],
                                        "arguments_delta": args_delta,
                                        "index": idx,
                                    }

                    # Check for finish
                    if finish_reason:
                        # Emit tool_call_end for all accumulated tool calls
                        for idx, tc_data in current_tool_calls.items():
                            self.logger.debug(
                                "zai_stream_tool_call_end",
                                tool_id=tc_data["id"],
                                tool_name=tc_data["name"],
                                arguments_length=len(tc_data["arguments"]),
                                index=idx,
                            )
                            yield {
                                "type": "tool_call_end",
                                "id": tc_data["id"],
                                "name": tc_data["name"],
                                "arguments": tc_data["arguments"],
                                "index": idx,
                            }

                except asyncio.TimeoutError:
                    self.logger.error(
                        "zai_stream_chunk_timeout",
                        model=actual_model,
                        timeout_seconds=chunk_timeout,
                    )
                    yield {
                        "type": "error",
                        "message": f"Stream timeout: no data received for {chunk_timeout}s",
                    }
                    # Cancel the stream worker
                    stream_future.cancel()
                    return

            # Wait for worker to complete (should be immediate since we got None)
            try:
                await asyncio.wait_for(stream_future, timeout=5.0)
            except asyncio.TimeoutError:
                self.logger.warning("zai_stream_worker_timeout")
            except asyncio.CancelledError:
                pass

            # Check if there was an error in the stream worker
            if stream_error:
                error = stream_error[0]
                error_msg = str(error)
                error_type = type(error).__name__

                self.logger.error(
                    "zai_stream_failed",
                    model=actual_model,
                    error_type=error_type,
                    error=error_msg[:200],
                )

                yield {"type": "error", "message": error_msg}
                return

            # Final done event
            latency_ms = int((time.time() - start_time) * 1000)

            # Streaming responses may not always have usage data
            usage: dict[str, Any] = {}

            self.logger.info(
                "zai_stream_completed",
                model=actual_model,
                latency_ms=latency_ms,
                tool_calls_count=len(current_tool_calls),
            )

            yield {"type": "done", "usage": usage}

        except Exception as e:
            error_msg = str(e)
            error_type = type(e).__name__

            self.logger.error(
                "zai_stream_failed",
                model=actual_model,
                error_type=error_type,
                error=error_msg[:200],
            )

            yield {"type": "error", "message": error_msg}
