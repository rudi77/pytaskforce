"""
LLM Provider Protocol

This module defines the protocol interface for LLM service implementations.
LLM providers abstract access to language models (OpenAI, Azure OpenAI, Anthropic, etc.)
with unified interfaces for completion and generation.

Protocol implementations must handle:
- Model alias resolution (e.g., "main" -> "gpt-4-turbo")
- Parameter mapping between model families (GPT-4 vs GPT-5)
- Retry logic with exponential backoff
- Structured logging with token usage tracking
- Streaming support for real-time token delivery
"""

from collections.abc import AsyncIterator
from typing import Any, Protocol


class LLMProviderProtocol(Protocol):
    """
    Protocol defining the contract for LLM service providers.

    Implementations provide unified access to language models with:
    - Model alias resolution (config-based mapping)
    - Automatic parameter mapping for different model families
    - Retry logic with configurable backoff
    - Token usage tracking and logging
    - Support for both chat completion and single-prompt generation

    Configuration:
        Implementations typically load configuration from YAML files containing:
        - default_model: Default model alias (e.g., "main")
        - models: Dict mapping aliases to actual model names
        - model_params: Default parameters per model family
        - retry_policy: Max attempts, backoff multiplier, timeout
        - providers: Provider-specific settings (API keys, endpoints)

    Thread Safety:
        Implementations must be safe for concurrent use across multiple
        async tasks (no shared mutable state without synchronization).

    Error Handling:
        Methods return Dict with "success": bool field. On failure:
        - "success": False
        - "error": Error message string
        - "error_type": Exception class name
        - Additional provider-specific error details
    """

    async def complete(
        self,
        messages: list[dict[str, Any]],
        model: str | None = None,
        tools: list[dict[str, Any]] | None = None,
        tool_choice: str | dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """
        Perform LLM chat completion with retry logic and native tool calling support.

        The implementation should:
        1. Resolve model alias to actual model name/deployment
        2. Merge default parameters with provided kwargs
        3. Map parameters for model family (GPT-4 vs GPT-5)
        4. Pass tools and tool_choice to API if provided
        5. Call LLM API with retry logic (exponential backoff)
        6. Extract content, tool_calls, and usage statistics
        7. Log token usage and latency
        8. Return standardized result dictionary

        Args:
            messages: List of message dicts with 'role' and 'content' keys.
                     Roles: "system", "user", "assistant", "tool"
            model: Model alias (e.g., "main", "fast") or None for default.
                  Resolved via configuration to actual model name.
            tools: Optional list of tool definitions in OpenAI function calling format.
                  Each tool: {"type": "function", "function": {"name": ..., "description": ..., "parameters": ...}}
            tool_choice: Optional tool choice strategy:
                        - "auto": Let model decide (default when tools provided)
                        - "none": Don't use tools
                        - "required": Must call a tool
                        - {"type": "function", "function": {"name": "tool_name"}}: Force specific tool
            **kwargs: Additional parameters (temperature, max_tokens, etc.).
                     Override default parameters for the model.

        Returns:
            Dictionary with:
            - success: bool - True if completion succeeded
            - content: str | None - Generated text (if no tool calls)
            - tool_calls: list[dict] | None - List of tool calls if model invoked tools
              Each tool call: {"id": str, "function": {"name": str, "arguments": str}}
            - usage: Dict - Token counts (total_tokens, prompt_tokens, completion_tokens)
            - model: str - Actual model name used
            - latency_ms: int - Request latency in milliseconds
            - error: str - Error message (if failed)
            - error_type: str - Exception class name (if failed)

        Example (without tools):
            >>> result = await llm_provider.complete(
            ...     messages=[
            ...         {"role": "system", "content": "You are a helpful assistant"},
            ...         {"role": "user", "content": "What is 2+2?"}
            ...     ],
            ...     model="main",
            ...     temperature=0.7
            ... )
            >>> if result["success"]:
            ...     print(f"Response: {result['content']}")

        Example (with tools):
            >>> tools = [{"type": "function", "function": {
            ...     "name": "calculator",
            ...     "description": "Perform calculations",
            ...     "parameters": {"type": "object", "properties": {"expression": {"type": "string"}}}
            ... }}]
            >>> result = await llm_provider.complete(
            ...     messages=[{"role": "user", "content": "What is 15 * 7?"}],
            ...     model="main",
            ...     tools=tools
            ... )
            >>> if result["success"] and result.get("tool_calls"):
            ...     for call in result["tool_calls"]:
            ...         print(f"Tool: {call['function']['name']}, Args: {call['function']['arguments']}")

        Parameter Mapping:
            GPT-4 models accept: temperature, top_p, max_tokens, frequency_penalty, presence_penalty
            GPT-5 models accept: effort, reasoning, max_tokens

            If temperature is provided for GPT-5, it's mapped to effort:
            - temperature < 0.3 -> effort: "low"
            - temperature 0.3-0.7 -> effort: "medium"
            - temperature > 0.7 -> effort: "high"
        """
        ...

    async def generate(
        self,
        prompt: str,
        context: dict[str, Any] | None = None,
        model: str | None = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """
        Generate text from a single prompt (convenience wrapper around complete).

        The implementation should:
        1. Format prompt with context (if provided) as YAML
        2. Create messages list with single user message
        3. Call complete() method
        4. Add "generated_text" alias for "content" field
        5. Return result dictionary

        Args:
            prompt: The prompt text (user message)
            context: Optional structured context to include before prompt.
                    Formatted as YAML and prepended to prompt.
            model: Model alias or None for default
            **kwargs: Additional parameters passed to complete()

        Returns:
            Same as complete(), with additional field:
            - generated_text: str - Alias for "content" field (if successful)

        Example:
            >>> result = await llm_provider.generate(
            ...     prompt="Summarize the following data",
            ...     context={"data": [1, 2, 3, 4, 5]},
            ...     model="fast",
            ...     max_tokens=200
            ... )
            >>> if result["success"]:
            ...     print(result["generated_text"])

        Context Formatting:
            If context is provided, the full prompt becomes:
            ```
            Context:
            <context as YAML>

            Task: <prompt>
            ```
        """
        ...

    async def complete_stream(
        self,
        messages: list[dict[str, Any]],
        model: str | None = None,
        tools: list[dict[str, Any]] | None = None,
        tool_choice: str | dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> AsyncIterator[dict[str, Any]]:
        """
        Stream LLM chat completion with real-time token delivery.

        Unlike complete(), this method yields chunks as they arrive from
        the LLM API, enabling real-time UI updates and progressive responses.

        The implementation should:
        1. Resolve model alias to actual model name/deployment
        2. Merge default parameters with provided kwargs
        3. Map parameters for model family (GPT-4 vs GPT-5)
        4. Call LLM API with stream=True
        5. Yield normalized events for each chunk
        6. Handle tool calls as progressive events
        7. Yield final done event with usage statistics

        Args:
            messages: List of message dicts with 'role' and 'content' keys.
                     Roles: "system", "user", "assistant", "tool"
            model: Model alias (e.g., "main", "fast") or None for default.
                  Resolved via configuration to actual model name.
            tools: Optional list of tool definitions in OpenAI function calling format.
            tool_choice: Optional tool choice strategy ("auto", "none", "required").
            **kwargs: Additional parameters (temperature, max_tokens, etc.).

        Yields:
            Normalized event dictionaries:

            - Token content:
              {"type": "token", "content": "..."}

            - Tool call starts:
              {"type": "tool_call_start", "id": "...", "name": "...", "index": N}

            - Tool call argument chunks:
              {"type": "tool_call_delta", "id": "...", "arguments_delta": "...", "index": N}

            - Tool call completes:
              {"type": "tool_call_end", "id": "...", "name": "...", "arguments": "...", "index": N}

            - Stream completes successfully:
              {"type": "done", "usage": {...}}

            - Error occurred:
              {"type": "error", "message": "..."}

        Note:
            - Errors are yielded as events, NOT raised as exceptions
            - No automatic retry logic for streaming (retry at consumer level)
            - Tool calls arrive progressively: start → delta(s) → end
            - done event always includes usage dict (may be empty if not available)

        Example:
            >>> async for event in llm_provider.complete_stream(
            ...     messages=[{"role": "user", "content": "Hello"}],
            ...     model="main"
            ... ):
            ...     if event["type"] == "token":
            ...         print(event["content"], end="", flush=True)
            ...     elif event["type"] == "done":
            ...         print(f"\\nTokens used: {event['usage']}")
        """
        # Yield required for AsyncIterator type hint
        yield {}  # pragma: no cover
