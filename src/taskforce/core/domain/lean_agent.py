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

from collections.abc import AsyncIterator
from typing import Any

from taskforce.core.domain.context_builder import ContextBuilder
from taskforce.core.domain.context_policy import ContextPolicy
from taskforce.core.domain.lean_agent_components.message_history_manager import (
    MessageHistoryManager,
)
from taskforce.core.domain.lean_agent_components.prompt_builder import LeanPromptBuilder
from taskforce.core.domain.lean_agent_components.resource_closer import ResourceCloser
from taskforce.core.domain.lean_agent_components.state_store import LeanAgentStateStore
from taskforce.core.domain.lean_agent_components.tool_executor import (
    ToolExecutor,
    ToolResultMessageFactory,
)
from taskforce.core.domain.models import ExecutionResult, StreamEvent
from taskforce.core.domain.planning_strategy import (
    NativeReActStrategy,
    PlanningStrategy,
)
from taskforce.core.domain.token_budgeter import TokenBudgeter
from taskforce.core.interfaces.llm import LLMProviderProtocol
from taskforce.core.interfaces.logging import LoggerProtocol
from taskforce.core.interfaces.state import StateManagerProtocol
from taskforce.core.interfaces.tool_result_store import ToolResultStoreProtocol
from taskforce.core.interfaces.tools import ToolProtocol
from taskforce.core.prompts.autonomous_prompts import LEAN_KERNEL_PROMPT
from taskforce.core.tools.planner_tool import PlannerTool
from taskforce.core.tools.tool_converter import tools_to_openai_format


class Agent:
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
    DEFAULT_MAX_PARALLEL_TOOLS = 4  # Conservative parallelism limit for tool execution
    # Token budget defaults
    DEFAULT_MAX_INPUT_TOKENS = 100000  # ~100k tokens for input
    DEFAULT_COMPRESSION_TRIGGER = 80000  # Trigger compression at 80% of max

    def __init__(
        self,
        state_manager: StateManagerProtocol,
        llm_provider: LLMProviderProtocol,
        tools: list[ToolProtocol],
        logger: LoggerProtocol,
        system_prompt: str | None = None,
        model_alias: str = "main",
        tool_result_store: ToolResultStoreProtocol | None = None,
        context_policy: ContextPolicy | None = None,
        max_input_tokens: int | None = None,
        compression_trigger: int | None = None,
        max_steps: int | None = None,
        max_parallel_tools: int | None = None,
        planning_strategy: PlanningStrategy | None = None,
    ):
        """
        Initialize Agent with injected dependencies.

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
            max_parallel_tools: Maximum number of tool calls to run concurrently
                      (default: 4)
            planning_strategy: Optional planning strategy override for Agent.
            logger: Logger instance (created in factory and always required).
        """
        self.state_manager = state_manager
        self.llm_provider = llm_provider
        self._base_system_prompt = system_prompt or LEAN_KERNEL_PROMPT
        self.model_alias = model_alias
        self.tool_result_store = tool_result_store
        self.logger = logger

        # Execution limits configuration
        self.max_steps = max_steps or self.DEFAULT_MAX_STEPS
        self.max_parallel_tools = max_parallel_tools or self.DEFAULT_MAX_PARALLEL_TOOLS
        self.planning_strategy = planning_strategy or NativeReActStrategy()

        # Context pack configuration (Story 9.2)
        self.context_policy = context_policy or ContextPolicy.conservative_default()
        self.context_builder = ContextBuilder(self.context_policy)

        # Token budget configuration (Story 9.3)
        self.token_budgeter = TokenBudgeter(
            logger=logger,
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

        # Prompt builder for plan/context injection
        self.prompt_builder = LeanPromptBuilder(
            base_system_prompt=self._base_system_prompt,
            planner=self._planner,
            context_builder=self.context_builder,
            context_policy=self.context_policy,
            logger=self.logger,
        )

        # Pre-convert tools to OpenAI format
        self._openai_tools = tools_to_openai_format(self.tools)

        # Message history manager (compression, budget checks)
        self.message_history_manager = MessageHistoryManager(
            token_budgeter=self.token_budgeter,
            openai_tools=self._openai_tools,
            llm_provider=self.llm_provider,
            model_alias=self.model_alias,
            summary_threshold=self.SUMMARY_THRESHOLD,
            logger=self.logger,
        )

        # Tool execution helpers
        self.tool_executor = ToolExecutor(
            tools=self.tools,
            logger=self.logger,
        )
        self.tool_result_message_factory = ToolResultMessageFactory(
            tool_result_store=self.tool_result_store,
            result_store_threshold=self.TOOL_RESULT_STORE_THRESHOLD,
            logger=self.logger,
        )

        # State persistence helper
        self.state_store = LeanAgentStateStore(
            state_manager=self.state_manager,
            logger=self.logger,
        )

        # Resource cleanup helper
        self.resource_closer = ResourceCloser(logger=self.logger)

    @property
    def system_prompt(self) -> str:
        """Return base system prompt (backward compatibility)."""
        return self._base_system_prompt

    @property
    def planner(self) -> PlannerTool | None:
        """Expose the planner instance for persistence helpers."""
        return self._planner

    def _build_system_prompt(
        self,
        mission: str | None = None,
        state: dict[str, Any] | None = None,
        messages: list[dict[str, Any]] | None = None,
    ) -> str:
        """Build system prompt with dynamic plan and context injection."""
        return self.prompt_builder.build_system_prompt(
            mission=mission,
            state=state,
            messages=messages,
        )

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
        """Compress message history using safe LLM-based summarization."""
        return await self.message_history_manager.compress_messages(messages)

    def _deterministic_compression(self, messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Deterministic compression without LLM (emergency fallback)."""
        return self.message_history_manager.deterministic_compression(messages)

    def _build_safe_summary_input(self, messages: list[dict[str, Any]]) -> str:
        """Build safe summary input from messages without raw JSON dumps."""
        return self.message_history_manager.build_safe_summary_input(messages)

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

        Note: Plan status is NOT included here - it's dynamically injected
        into the system prompt on each loop iteration via _build_system_prompt().
        """
        return self.message_history_manager.build_initial_messages(
            mission=mission,
            state=state,
            base_system_prompt=self._base_system_prompt,
        )

    async def _execute_tool(
        self,
        tool_name: str,
        tool_args: dict[str, Any],
    ) -> dict[str, Any]:
        """Execute a tool by name with given arguments."""
        return await self.tool_executor.execute(tool_name, tool_args)

    async def _create_tool_message(
        self,
        tool_call_id: str,
        tool_name: str,
        tool_result: dict[str, Any],
        session_id: str,
        step: int,
    ) -> dict[str, Any]:
        """Create a tool message for message history."""
        return await self.tool_result_message_factory.build_message(
            tool_call_id=tool_call_id,
            tool_name=tool_name,
            tool_result=tool_result,
            session_id=session_id,
            step=step,
        )

    async def _preflight_budget_check(self, messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Preflight budget check before LLM call."""
        return await self.message_history_manager.preflight_budget_check(messages)

    async def _save_state(self, session_id: str, state: dict[str, Any]) -> None:
        """Save state including PlannerTool state."""
        await self.state_store.save(
            session_id=session_id,
            state=state,
            planner=self._planner,
        )

    async def close(self) -> None:
        """
        Clean up resources (MCP connections, etc).

        Called by CLI/API to gracefully shut down agent.
        For Agent, this cleans up any MCP client contexts
        stored by the factory.
        """
        # Clean up MCP client contexts if they were attached by factory
        mcp_contexts = getattr(self, "_mcp_contexts", [])
        await self.resource_closer.close_mcp_contexts(mcp_contexts)
        self.logger.debug("agent_closed")


# Backwards-compatible alias (deprecated).
LeanAgent = Agent

__all__ = ["Agent", "LeanAgent"]
