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
from typing import Any, Optional

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
from taskforce.core.domain.enums import EventType, ExecutionStatus
from taskforce.core.domain.models import ExecutionResult, StreamEvent
from taskforce.core.domain.planning_strategy import (
    NativeReActStrategy,
    PlanningStrategy,
)
from taskforce.core.domain.token_budgeter import TokenBudgeter
from taskforce.core.interfaces.llm import LLMProviderProtocol
from taskforce.core.interfaces.logging import LoggerProtocol
from taskforce.core.interfaces.runtime import AgentRuntimeTrackerProtocol
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
    DEFAULT_SUMMARY_THRESHOLD = 20  # Compress when exceeding this message count (legacy fallback)
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
        runtime_tracker: AgentRuntimeTrackerProtocol | None = None,
        skill_manager: Any | None = None,
        intent_router: Any | None = None,
        summary_threshold: int | None = None,
    ):
        """
        Initialize Agent with injected dependencies.

        Args:
            state_manager: Protocol for session state persistence
            llm_provider: Protocol for LLM completions (must support tools parameter)
            tools: List of available tools (PlannerTool should be included)
            logger: Logger instance (created in factory and always required).
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
            runtime_tracker: Optional runtime tracker for heartbeats/checkpoints.
            skill_manager: Optional SkillManager for plugin-based skill activation
                          and automatic skill switching based on tool outputs.
            intent_router: Optional FastIntentRouter for pre-LLM intent classification.
                          When provided, allows skipping planning for well-defined intents.
            summary_threshold: Message count threshold for triggering compression
                              (default: 20, lower values compress more aggressively).
        """
        self.state_manager = state_manager
        self.llm_provider = llm_provider
        self._base_system_prompt = system_prompt or LEAN_KERNEL_PROMPT
        self.model_alias = model_alias
        self.tool_result_store = tool_result_store
        self.logger = logger
        self.runtime_tracker = runtime_tracker
        self.skill_manager = skill_manager
        self.intent_router = intent_router
        self._skill_switch_pending = False  # Flag for skill switch during execution

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

        # Message history configuration
        self.summary_threshold = summary_threshold or self.DEFAULT_SUMMARY_THRESHOLD

        # Message history manager (compression, budget checks)
        self.message_history_manager = MessageHistoryManager(
            token_budgeter=self.token_budgeter,
            openai_tools=self._openai_tools,
            llm_provider=self.llm_provider,
            model_alias=self.model_alias,
            summary_threshold=self.summary_threshold,
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
            runtime_tracker=self.runtime_tracker,
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
        """Build system prompt with dynamic plan, context, and skill injection."""
        base_prompt = self.prompt_builder.build_system_prompt(
            mission=mission,
            state=state,
            messages=messages,
        )

        # Inject active skill instructions if skill manager is configured
        if self.skill_manager and self.skill_manager.active_skill_name:
            skill_instructions = self.skill_manager.get_active_instructions()
            if skill_instructions:
                base_prompt = f"""{base_prompt}

# ACTIVE SKILL: {self.skill_manager.active_skill_name}

{skill_instructions}
"""

        return base_prompt

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
        await self.record_heartbeat(
            session_id,
            "starting",
            {"mission_length": len(mission)},
        )
        result = await self.planning_strategy.execute(self, mission, session_id)
        await self.mark_finished(
            session_id,
            result.status,
            {"final_message_length": len(result.final_message or "")},
        )
        return result

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
        1. Fast intent routing (skip planning for well-defined intents)
        2. Load state (restore PlannerTool state if exists)
        3. Build initial messages with system prompt and mission
        4. Loop: Stream LLM with tools → yield events → handle tool_calls or final content
        5. Persist state and yield final_answer event

        Args:
            mission: User's mission description
            session_id: Unique session identifier for state persistence

        Yields:
            StreamEvent objects for each significant execution event:
            - skill_auto_activated: Skill activated via fast intent routing
            - step_start: New loop iteration begins
            - llm_token: Token chunk from LLM response
            - tool_call: Tool invocation starting
            - tool_result: Tool execution completed
            - plan_updated: PlannerTool modified the plan
            - final_answer: Agent completed with final response
            - error: Error occurred during execution
        """
        await self.record_heartbeat(
            session_id,
            "starting",
            {"mission_length": len(mission)},
        )

        # Fast Intent Routing: classify intent and activate skill BEFORE planning
        if self.intent_router and self.skill_manager:
            match = self.intent_router.classify(mission)
            if match:  # classify() already checks min_confidence threshold
                # Activate skill directly, skip planning overhead
                activated = self.skill_manager.activate_skill(match.skill_name)
                if activated:
                    self.logger.info(
                        "fast_intent_routing",
                        intent=match.intent,
                        skill=match.skill_name,
                        confidence=match.confidence,
                    )
                    yield StreamEvent(
                        event_type=EventType.SKILL_AUTO_ACTIVATED,
                        data={
                            "intent": match.intent,
                            "skill": match.skill_name,
                            "confidence": match.confidence,
                        },
                    )

        final_message = ""
        status = ExecutionStatus.COMPLETED.value
        async for event in self.planning_strategy.execute_stream(
            self, mission, session_id
        ):
            yield event
            # Track final answer content for COMPLETE event
            if event.event_type == EventType.FINAL_ANSWER:
                final_message = event.data.get("content", "")
            elif event.event_type == EventType.ERROR:
                status = ExecutionStatus.FAILED.value

        # Yield COMPLETE event for executor.execute_mission() compatibility
        yield StreamEvent(
            event_type=EventType.COMPLETE,
            data={
                "status": status,
                "session_id": session_id,
                "final_message": final_message,
            },
        )
        await self.mark_finished(session_id, "stream_complete", None)

    def _truncate_output(self, output: str, max_length: int = 4000) -> str:
        """
        Truncate output for streaming events.

        Args:
            output: The output string to truncate
            max_length: Maximum length before truncation (default: 4000)
                       Increased from 200 to preserve useful data like
                       booking_proposals in tool results.

        Returns:
            Truncated string with "..." suffix if truncated.
        """
        if len(output) <= max_length:
            return output
        return output[:max_length] + "..."

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
        session_id: Optional[str] = None,
    ) -> dict[str, Any]:
        """
        Execute a tool by name with given arguments.

        Args:
            tool_name: Name of the tool to execute
            tool_args: Arguments to pass to the tool
            session_id: Optional session ID (injected for call_agent orchestration)

        Returns:
            Tool execution result dictionary
        """
        # Inject parent session ID for AgentTool (multi-agent orchestration)
        if tool_name == "call_agent" and session_id:
            tool_args = {**tool_args, "_parent_session_id": session_id}

        result = await self.tool_executor.execute(tool_name, tool_args)

        # Check for skill switch after tool execution
        if self.skill_manager and isinstance(result, dict):
            switch_result = self.skill_manager.check_skill_switch(tool_name, result)
            if switch_result.switched:
                self.logger.info(
                    "skill_switched",
                    from_skill=switch_result.from_skill,
                    to_skill=switch_result.to_skill,
                    trigger_tool=tool_name,
                )
                # Mark that prompt needs refresh
                self._skill_switch_pending = True

        return result

    def get_effective_system_prompt(self) -> str:
        """
        Get the effective system prompt, including active skill instructions.

        If a skill manager is configured and has an active skill, the skill
        instructions are appended to the base system prompt.

        Returns:
            The complete system prompt with skill instructions
        """
        if not self.skill_manager:
            return self._base_system_prompt

        return self.skill_manager.enhance_prompt(self._base_system_prompt)

    def activate_skill_by_intent(self, intent: str) -> bool:
        """
        Activate a skill based on user intent.

        Args:
            intent: User intent string (e.g., "INVOICE_PROCESSING")

        Returns:
            True if a skill was activated, False otherwise
        """
        if not self.skill_manager:
            return False

        skill = self.skill_manager.activate_by_intent(intent)
        if skill:
            self.logger.info(
                "skill_activated_by_intent",
                intent=intent,
                skill=skill.name,
            )
            return True
        return False

    def activate_skill(self, skill_name: str) -> bool:
        """
        Activate a specific skill by name.

        Args:
            skill_name: Name of the skill to activate

        Returns:
            True if skill was activated, False otherwise
        """
        if not self.skill_manager:
            return False

        skill = self.skill_manager.activate_skill(skill_name)
        if skill:
            self.logger.info(
                "skill_activated",
                skill=skill.name,
            )
            return True
        return False

    def get_active_skill_name(self) -> str | None:
        """Get the name of the currently active skill."""
        if not self.skill_manager:
            return None
        return self.skill_manager.active_skill_name

    async def _save_state(self, session_id: str, state: dict[str, Any]) -> None:
        """Save state including PlannerTool state."""
        await self.state_store.save(
            session_id=session_id,
            state=state,
            planner=self._planner,
        )

    async def record_heartbeat(
        self,
        session_id: str,
        status: str,
        details: dict[str, Any] | None = None,
    ) -> None:
        """Record a runtime heartbeat when tracking is enabled."""
        if not self.runtime_tracker:
            return
        await self.runtime_tracker.record_heartbeat(session_id, status, details)

    async def mark_finished(
        self,
        session_id: str,
        status: str,
        details: dict[str, Any] | None = None,
    ) -> None:
        """Record final status for runtime tracking."""
        if not self.runtime_tracker:
            return
        await self.runtime_tracker.mark_finished(session_id, status, details)

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
