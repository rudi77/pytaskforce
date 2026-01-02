"""
Lean Agent - Simplified ReAct Agent with Native Tool Calling

A lightweight agent implementing a single execution loop using native LLM
tool calling capabilities (OpenAI/Anthropic function calling).

Key features:
- Native tool calling (no custom JSON parsing)
- PlannerTool as first-class tool for plan management
- Dynamic context injection: plan status injected into system prompt each loop
- Robust error handling with automatic retry context
- Clean message history management

Key differences from legacy Agent:
- No TodoListManager dependency
- No QueryRouter or fast-path logic
- No ReplanStrategy
- No JSON parsing for action extraction
- Native function calling for tool invocation
"""

import json
from collections.abc import AsyncIterator
from typing import Any

import structlog

from taskforce.core.domain.context_builder import ContextBuilder
from taskforce.core.domain.context_policy import ContextPolicy
from taskforce.core.domain.models import ExecutionResult, StreamEvent
from taskforce.core.domain.planning_strategy import (
    NativeReActStrategy,
    PlanningStrategy,
)
from taskforce.core.domain.token_budgeter import TokenBudgeter
from taskforce.core.interfaces.llm import LLMProviderProtocol
from taskforce.core.interfaces.state import StateManagerProtocol
from taskforce.core.interfaces.tool_result_store import ToolResultStoreProtocol
from taskforce.core.interfaces.tools import ToolProtocol
from taskforce.core.prompts.autonomous_prompts import LEAN_KERNEL_PROMPT
from taskforce.core.tools.planner_tool import PlannerTool
from taskforce.infrastructure.tools.tool_converter import (
    create_tool_result_preview,
    tool_result_preview_to_message,
    tool_result_to_message,
    tools_to_openai_format,
)


class LeanAgent:
    """
    Lightweight ReAct agent with native tool calling.

    Implements a single execution loop using LLM native function calling:
    1. Send messages with tools to LLM
    2. If LLM returns tool_calls → execute tools, add results to history, loop
    3. If LLM returns content → that's the final answer, return

    No JSON parsing, no custom action schemas - relies entirely on native
    tool calling capabilities of modern LLMs.
    """

    # Default limits (can be overridden per agent type)
    DEFAULT_MAX_STEPS = 30  # Conservative default for simple agents
    # Message history management (inspired by agent_v2 MessageHistory)
    MAX_MESSAGES = 50  # Hard limit on message count
    SUMMARY_THRESHOLD = 20  # Compress when exceeding this message count (legacy fallback)
    # Tool result storage thresholds
    TOOL_RESULT_STORE_THRESHOLD = 5000  # Store results larger than 5000 chars
    # Token budget defaults
    DEFAULT_MAX_INPUT_TOKENS = 100000  # ~100k tokens for input
    DEFAULT_COMPRESSION_TRIGGER = 80000  # Trigger compression at 80% of max

    def __init__(
        self,
        state_manager: StateManagerProtocol,
        llm_provider: LLMProviderProtocol,
        tools: list[ToolProtocol],
        system_prompt: str | None = None,
        model_alias: str = "main",
        tool_result_store: ToolResultStoreProtocol | None = None,
        context_policy: ContextPolicy | None = None,
        max_input_tokens: int | None = None,
        compression_trigger: int | None = None,
        max_steps: int | None = None,
        planning_strategy: PlanningStrategy | None = None,
    ):
        """
        Initialize LeanAgent with injected dependencies.

        Args:
            state_manager: Protocol for session state persistence
            llm_provider: Protocol for LLM completions (must support tools parameter)
            tools: List of available tools (PlannerTool should be included)
            system_prompt: Base system prompt for LLM interactions
                          (defaults to LEAN_KERNEL_PROMPT if not provided)
            model_alias: Model alias for LLM calls (default: "main")
            tool_result_store: Optional store for large tool results (enables handle-based storage)
            context_policy: Optional policy for context pack budgeting
                          (defaults to conservative policy if not provided)
            max_input_tokens: Maximum input tokens allowed (default: 100k)
            compression_trigger: Token count to trigger compression (default: 80k)
            max_steps: Maximum execution steps allowed (default: 30 for simple agents,
                      should be higher for RAG/document agents ~50-100)
            planning_strategy: Optional planning strategy override for LeanAgent.
        """
        self.state_manager = state_manager
        self.llm_provider = llm_provider
        self._base_system_prompt = system_prompt or LEAN_KERNEL_PROMPT
        self.model_alias = model_alias
        self.tool_result_store = tool_result_store
        self.logger = structlog.get_logger().bind(component="lean_agent")

        # Execution limits configuration
        self.max_steps = max_steps or self.DEFAULT_MAX_STEPS
        self.planning_strategy = planning_strategy or NativeReActStrategy()

        # Context pack configuration (Story 9.2)
        self.context_policy = context_policy or ContextPolicy.conservative_default()
        self.context_builder = ContextBuilder(self.context_policy)

        # Token budget configuration (Story 9.3)
        self.token_budgeter = TokenBudgeter(
            max_input_tokens=max_input_tokens or self.DEFAULT_MAX_INPUT_TOKENS,
            compression_trigger=compression_trigger or self.DEFAULT_COMPRESSION_TRIGGER,
        )

        # Build tools dict, ensure PlannerTool exists
        self.tools: dict[str, ToolProtocol] = {}
        self._planner: PlannerTool | None = None

        for tool in tools:
            self.tools[tool.name] = tool
            if isinstance(tool, PlannerTool):
                self._planner = tool

        # Create PlannerTool if not provided
        if self._planner is None:
            self._planner = PlannerTool()
            self.tools[self._planner.name] = self._planner

        # Pre-convert tools to OpenAI format
        self._openai_tools = tools_to_openai_format(self.tools)

    @property
    def system_prompt(self) -> str:
        """Return base system prompt (backward compatibility)."""
        return self._base_system_prompt

    def _build_system_prompt(
        self,
        mission: str | None = None,
        state: dict[str, Any] | None = None,
        messages: list[dict[str, Any]] | None = None,
    ) -> str:
        """
        Build system prompt with dynamic plan and context pack injection.

        Reads current plan from PlannerTool and injects it into the system
        prompt. Also builds and injects a budgeted context pack with recent
        tool results and other relevant context (Story 9.2).

        Args:
            mission: Optional mission description for context pack
            state: Optional session state for context pack
            messages: Optional message history for context pack

        Returns:
            Complete system prompt with plan context and context pack.
        """
        prompt = self._base_system_prompt

        # Inject current plan status if PlannerTool exists and has a plan
        if self._planner:
            plan_result = self._planner._read_plan()
            plan_output = plan_result.get("output", "")

            # Only inject if there's an actual plan (not "No active plan.")
            if plan_output and plan_output != "No active plan.":
                plan_section = (
                    "\n\n## CURRENT PLAN STATUS\n"
                    "The following plan is currently active. "
                    "Use it to guide your next steps.\n\n"
                    f"{plan_output}"
                )
                prompt += plan_section
                self.logger.debug("plan_injected", plan_steps=plan_output.count("\n") + 1)

        # Build and inject context pack (Story 9.2)
        context_pack = self.context_builder.build_context_pack(
            mission=mission, state=state, messages=messages
        )
        if context_pack:
            prompt += f"\n\n{context_pack}"
            self.logger.debug(
                "context_pack_injected",
                pack_length=len(context_pack),
                policy_max=self.context_policy.max_total_chars,
            )

        return prompt

    async def execute(self, mission: str, session_id: str) -> ExecutionResult:
        """
        Execute mission using the configured planning strategy.

        Workflow:
        1. Load state (restore PlannerTool state if exists)
        2. Build initial messages with system prompt and mission
        3. Loop: Call LLM with tools → handle tool_calls or final content
        4. Persist state and return result

        Args:
            mission: User's mission description
            session_id: Unique session identifier for state persistence

        Returns:
            ExecutionResult with status and final message
        """
        return await self.planning_strategy.execute(self, mission, session_id)

    async def execute_stream(
        self,
        mission: str,
        session_id: str,
    ) -> AsyncIterator[StreamEvent]:
        """
        Execute mission with streaming progress events.

        Yields StreamEvent objects as execution progresses, enabling
        real-time feedback to consumers. This is the streaming counterpart
        to execute() - same functionality but with progressive events.

        Workflow:
        1. Load state (restore PlannerTool state if exists)
        2. Build initial messages with system prompt and mission
        3. Loop: Stream LLM with tools → yield events → handle tool_calls or final content
        4. Persist state and yield final_answer event

        Args:
            mission: User's mission description
            session_id: Unique session identifier for state persistence

        Yields:
            StreamEvent objects for each significant execution event:
            - step_start: New loop iteration begins
            - llm_token: Token chunk from LLM response
            - tool_call: Tool invocation starting
            - tool_result: Tool execution completed
            - plan_updated: PlannerTool modified the plan
            - final_answer: Agent completed with final response
            - error: Error occurred during execution
        """
        async for event in self.planning_strategy.execute_stream(
            self, mission, session_id
        ):
            yield event

    def _truncate_output(self, output: str, max_length: int = 200) -> str:
        """
        Truncate output for streaming events.

        Args:
            output: The output string to truncate
            max_length: Maximum length before truncation (default: 200)

        Returns:
            Truncated string with "..." suffix if truncated.
        """
        if len(output) <= max_length:
            return output
        return output[:max_length] + "..."

    async def _compress_messages(self, messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """
        Compress message history using safe LLM-based summarization.

        Strategy (Story 9.3 - Safe Compression):
        1. Trigger based on token budget (primary) or message count (fallback)
        2. Build safe summary input from sanitized message previews (NO raw dumps)
        3. Use LLM to summarize old messages (skip system prompt)
        4. Replace old messages with summary + keep recent messages
        5. Fallback: Simple truncation if LLM summarization fails

        This prevents token overflow while preserving context.
        """
        message_count = len(messages)

        # Budget-based trigger (primary)
        should_compress_budget = self.token_budgeter.should_compress(
            messages=messages,
            tools=self._openai_tools,
        )

        # Message count trigger (fallback for backward compatibility)
        should_compress_count = message_count > self.SUMMARY_THRESHOLD

        # Check if compression needed
        if not (should_compress_budget or should_compress_count):
            return messages

        self.logger.warning(
            "compressing_messages",
            message_count=message_count,
            threshold=self.SUMMARY_THRESHOLD,
            budget_trigger=should_compress_budget,
            count_trigger=should_compress_count,
        )

        # Extract old messages to summarize (skip system prompt)
        # CRITICAL: Limit to prevent explosion even in compression
        max_messages_to_summarize = min(self.SUMMARY_THRESHOLD - 1, 15)  # Cap at 15
        old_messages = messages[1 : 1 + max_messages_to_summarize]

        # Build safe summary input (NO raw JSON dumps)
        summary_input = self._build_safe_summary_input(old_messages)

        # EMERGENCY GUARD: Check if summary input itself is too large
        # If summary input > 50k chars (~12.5k tokens), use deterministic fallback
        if len(summary_input) > 50000:
            self.logger.error(
                "compression_input_too_large",
                input_length=len(summary_input),
                action="using_deterministic_fallback",
            )
            return self._deterministic_compression(messages)

        # Build summary prompt
        summary_prompt = f"""Summarize this conversation history concisely:

{summary_input}

Provide a 2-3 paragraph summary of:
- Key decisions made
- Important tool results and findings
- Context needed for understanding recent messages

Keep it factual and concise."""

        # CRITICAL: Budget-check the compression prompt itself
        compression_messages = [{"role": "user", "content": summary_prompt}]
        compression_estimated = self.token_budgeter.estimate_tokens(compression_messages)

        if compression_estimated > self.token_budgeter.max_input_tokens:
            self.logger.error(
                "compression_prompt_over_budget",
                estimated_tokens=compression_estimated,
                max_tokens=self.token_budgeter.max_input_tokens,
                action="using_deterministic_fallback",
            )
            return self._deterministic_compression(messages)

        try:
            # Use LLM to create summary
            result = await self.llm_provider.complete(
                messages=compression_messages,
                model=self.model_alias,
                temperature=0,
            )

            # Check for context length exceeded error specifically
            error = result.get("error", "")
            if "context length" in error.lower() or "token limit" in error.lower():
                self.logger.error(
                    "compression_context_length_exceeded",
                    error=error,
                    action="using_deterministic_fallback",
                )
                return self._deterministic_compression(messages)

            if not result.get("success"):
                self.logger.error(
                    "compression_failed",
                    error=error,
                )
                # Fallback: Deterministic compression
                return self._deterministic_compression(messages)

            summary = result.get("content", "")

            # Build compressed message list
            compressed = [
                messages[0],  # System prompt
                {
                    "role": "system",
                    "content": f"[Previous Context Summary]\n{summary}",
                },
                *messages[self.SUMMARY_THRESHOLD :],  # Recent messages
            ]

            self.logger.info(
                "messages_compressed_with_summary",
                original_count=message_count,
                compressed_count=len(compressed),
                summary_length=len(summary),
            )

            return compressed

        except Exception as e:
            self.logger.error("compression_exception", error=str(e))
            return self._deterministic_compression(messages)

    def _deterministic_compression(self, messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """
        Deterministic compression without LLM (emergency fallback).

        This is used when:
        - Compression prompt itself is too large
        - LLM compression fails
        - Context length exceeded errors

        Strategy:
        - Keep system prompt
        - Keep last 10 messages (hard cap)
        - Add a simple text summary of what was dropped

        This NEVER calls LLM and NEVER explodes.
        """
        self.logger.warning(
            "using_deterministic_compression",
            original_count=len(messages),
        )

        # Keep system prompt
        system_prompt = messages[0] if messages else {"role": "system", "content": ""}

        # Keep last 10 messages (excluding system prompt)
        recent_messages = messages[-10:] if len(messages) > 10 else messages[1:]

        # Create simple summary of dropped content
        dropped_count = len(messages) - len(recent_messages) - 1  # -1 for system
        if dropped_count > 0:
            summary_text = (
                f"[{dropped_count} earlier messages compressed for token budget. "
                f"Continuing from recent context.]"
            )
            compressed = [
                system_prompt,
                {"role": "system", "content": summary_text},
                *recent_messages,
            ]
        else:
            compressed = [system_prompt, *recent_messages]

        self.logger.info(
            "deterministic_compression_complete",
            original_count=len(messages),
            compressed_count=len(compressed),
            dropped_count=dropped_count,
        )

        return compressed

    def _build_safe_summary_input(self, messages: list[dict[str, Any]]) -> str:
        """
        Build safe summary input from messages without raw JSON dumps.

        Extracts only essential information from messages:
        - Role and content (sanitized)
        - Tool call names (not full arguments)
        - Tool result previews (not raw outputs)

        Args:
            messages: List of messages to summarize

        Returns:
            Safe text representation for summary prompt
        """
        summary_parts = []

        for idx, msg in enumerate(messages):
            role = msg.get("role", "unknown")
            parts = [f"[Message {idx + 1} - {role}]"]

            # Tool results (preview only, not raw output)
            if role == "tool":
                tool_name = msg.get("name", "unknown")
                parts.append(f"Tool: {tool_name}")

                # Try to parse content as JSON to extract preview
                try:
                    content_str = msg.get("content", "")
                    if content_str:
                        result_data = json.loads(content_str)
                        preview = self.token_budgeter.extract_tool_output_preview(result_data)
                        parts.append(f"Result: {preview}")
                except (json.JSONDecodeError, TypeError):
                    # If not JSON, just truncate content
                    content_str = str(msg.get("content", ""))[:500]
                    parts.append(f"Result: {content_str}")
            else:
                # Content (sanitized) - only for non-tool messages
                content = msg.get("content")
                if content:
                    # Sanitize content to prevent overflow
                    sanitized_msg = self.token_budgeter.sanitize_message(msg)
                    sanitized_content = sanitized_msg.get("content", "")
                    if sanitized_content:
                        parts.append(f"Content: {sanitized_content[:1000]}")

                # Tool calls (names only, not full arguments)
                tool_calls = msg.get("tool_calls")
                if tool_calls:
                    tool_names = [
                        tc.get("function", {}).get("name", "unknown") for tc in tool_calls
                    ]
                    parts.append(f"Tools called: {', '.join(tool_names)}")

            summary_parts.append("\n".join(parts))

        return "\n\n".join(summary_parts)

    def _fallback_compression(self, messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """
        Fallback compression when LLM summarization fails.

        DEPRECATED: Now redirects to _deterministic_compression for consistency.
        """
        self.logger.warning("fallback_compression_redirecting_to_deterministic")
        return self._deterministic_compression(messages)

    def _build_initial_messages(
        self,
        mission: str,
        state: dict[str, Any],
    ) -> list[dict[str, Any]]:
        """
        Build initial message list for LLM conversation.

        Includes conversation_history from state to support multi-turn chat.
        The history contains previous user/assistant exchanges for context.

        Note: Plan status is NOT included here - it's dynamically injected
        into the system prompt on each loop iteration via _build_system_prompt().
        """
        messages: list[dict[str, Any]] = [
            {"role": "system", "content": self._base_system_prompt},
        ]

        # Load conversation history from state for multi-turn context
        conversation_history = state.get("conversation_history", [])
        if conversation_history:
            # Add previous conversation turns (user/assistant pairs)
            for msg in conversation_history:
                role = msg.get("role")
                content = msg.get("content", "")
                if role in ("user", "assistant") and content:
                    messages.append({"role": role, "content": content})
            self.logger.debug(
                "conversation_history_loaded",
                history_length=len(conversation_history),
            )

        # Build user message with current mission and context
        user_answers = state.get("answers", {})
        answers_text = ""
        if user_answers:
            answers_text = (
                f"\n\n## User Provided Information\n" f"{json.dumps(user_answers, indent=2)}"
            )

        user_message = f"{mission}{answers_text}"

        # Add current mission as latest user message
        messages.append({"role": "user", "content": user_message})

        return messages

    async def _execute_tool(
        self,
        tool_name: str,
        tool_args: dict[str, Any],
    ) -> dict[str, Any]:
        """Execute a tool by name with given arguments."""
        tool = self.tools.get(tool_name)
        if not tool:
            return {"success": False, "error": f"Tool not found: {tool_name}"}

        try:
            self.logger.info("tool_execute", tool=tool_name, args_keys=list(tool_args.keys()))
            result = await tool.execute(**tool_args)
            self.logger.info("tool_complete", tool=tool_name, success=result.get("success"))
            return result
        except Exception as e:
            self.logger.error("tool_exception", tool=tool_name, error=str(e))
            return {"success": False, "error": str(e)}

    async def _create_tool_message(
        self,
        tool_call_id: str,
        tool_name: str,
        tool_result: dict[str, Any],
        session_id: str,
        step: int,
    ) -> dict[str, Any]:
        """
        Create a tool message for message history.

        If tool_result_store is available and the result is large, stores the
        result and returns a handle+preview message. Otherwise, returns a
        standard message with the full result (truncated).

        Args:
            tool_call_id: Tool call ID from LLM
            tool_name: Name of the executed tool
            tool_result: Full tool result dictionary
            session_id: Current session ID
            step: Current execution step

        Returns:
            Message dictionary for message history
        """
        # Calculate result size
        result_json = json.dumps(tool_result, ensure_ascii=False, default=str)
        result_size = len(result_json)

        # Use handle-based storage if store available and result is large
        if self.tool_result_store and result_size > self.TOOL_RESULT_STORE_THRESHOLD:
            # Store result and get handle
            handle = await self.tool_result_store.put(
                tool_name=tool_name,
                result=tool_result,
                session_id=session_id,
                metadata={
                    "step": step,
                    "success": tool_result.get("success", False),
                },
            )

            # Create preview
            preview = create_tool_result_preview(handle, tool_result)

            # Log handle usage
            self.logger.info(
                "tool_result_stored_with_handle",
                tool=tool_name,
                handle_id=handle.id,
                size_chars=result_size,
                preview_length=len(preview.preview_text),
            )

            # Return handle+preview message
            return tool_result_preview_to_message(tool_call_id, tool_name, preview)
        else:
            # Use standard message with truncation
            return tool_result_to_message(tool_call_id, tool_name, tool_result)

    async def _preflight_budget_check(self, messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """
        Preflight budget check before LLM call.

        If messages exceed budget even after compression, apply emergency
        sanitization and truncation to prevent token overflow errors.

        Args:
            messages: Message list to check

        Returns:
            Sanitized/truncated message list if needed, otherwise original
        """
        # Check if over budget
        if not self.token_budgeter.is_over_budget(
            messages=messages,
            tools=self._openai_tools,
        ):
            return messages

        # Emergency: Still over budget after compression
        self.logger.error(
            "emergency_budget_enforcement",
            message_count=len(messages),
            action="sanitize_and_truncate",
        )

        # Step 1: Sanitize all messages (hard caps on content)
        sanitized = self.token_budgeter.sanitize_messages(messages)

        # Step 2: If still over budget, keep only system + recent messages
        if self.token_budgeter.is_over_budget(
            messages=sanitized,
            tools=self._openai_tools,
        ):
            self.logger.error(
                "emergency_truncation",
                original_count=len(sanitized),
                action="keep_recent_only",
            )

            # Keep system prompt + last 10 messages (aggressive truncation)
            emergency_truncated = [sanitized[0]] + sanitized[-10:]

            self.logger.warning(
                "emergency_truncation_complete",
                final_count=len(emergency_truncated),
            )

            return emergency_truncated

        return sanitized

    async def _save_state(self, session_id: str, state: dict[str, Any]) -> None:
        """Save state including PlannerTool state."""
        if self._planner:
            state["planner_state"] = self._planner.get_state()
        await self.state_manager.save_state(session_id, state)

    async def close(self) -> None:
        """
        Clean up resources (MCP connections, etc).

        Called by CLI/API to gracefully shut down agent.
        For LeanAgent, this cleans up any MCP client contexts
        stored by the factory.
        """
        # Clean up MCP client contexts if they were attached by factory
        mcp_contexts = getattr(self, "_mcp_contexts", [])
        for ctx in mcp_contexts:
            try:
                await ctx.__aexit__(None, None, None)
            except Exception:
                pass  # Ignore cleanup errors
        self.logger.debug("agent_closed")
