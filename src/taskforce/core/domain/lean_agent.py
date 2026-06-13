"""
Agent - ReAct Agent with Native Tool Calling

An agent implementing a single execution loop using native LLM
tool calling capabilities (OpenAI/Anthropic function calling).

Key features:
- Native tool calling (no custom JSON parsing)
- PlannerTool as first-class tool for plan management
- Dynamic context injection: plan status injected into system prompt each loop
- Robust error handling with automatic retry context
- Clean message history management
"""

import asyncio
from collections.abc import AsyncIterator, Callable
from typing import Any

from taskforce.core.domain.context_builder import ContextBuilder
from taskforce.core.domain.context_policy import ContextPolicy
from taskforce.core.domain.enums import EventType, ExecutionStatus
from taskforce.core.domain.lean_agent_components.context_manager import (
    ContextManager,
)
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
from taskforce.core.domain.lean_agent_components.wiki_context_loader import (
    WikiContextConfig,
    WikiContextLoader,
)
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
from taskforce.core.interfaces.wiki_store import WikiStoreProtocol
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
    # Tool result storage thresholds.
    # 2000 chars (~500 tokens) keeps web_search/web_fetch snippets out of the
    # LLM message log by default. Tools can override per-tool by setting
    # ``tool_result_store_threshold`` (see BaseTool).
    TOOL_RESULT_STORE_THRESHOLD = 2000
    DEFAULT_MAX_PARALLEL_TOOLS = 4  # Conservative parallelism limit for tool execution
    # Token budget defaults
    DEFAULT_MAX_INPUT_TOKENS = 100000  # ~100k tokens for input
    DEFAULT_COMPRESSION_TRIGGER = 40000  # Trigger compression at 40% - keep history lean
    # ReAct stall detection defaults — override per agent for workloads
    # that legitimately need many low-progress steps (browser DOM
    # exploration, multi-stage RAG retrieval, …).
    DEFAULT_REACT_NO_PROGRESS_THRESHOLD = 2
    DEFAULT_REACT_SIGNATURE_REPEAT_THRESHOLD = 3

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
        summary_threshold: int | None = None,
        wiki_store: WikiStoreProtocol | None = None,
        wiki_context_config: WikiContextConfig | None = None,
        tool_result_store_threshold: int | None = None,
        tool_message_max_chars: int | None = None,
        assistant_message_max_chars: int | None = None,
        approval_bypass_tools: list[str] | None = None,
        approval_service_provider: Callable[[], Any | None] | None = None,
        approval_bypass_provider: Callable[[], frozenset[str]] | None = None,
        react_no_progress_threshold: int | None = None,
        react_signature_repeat_threshold: int | None = None,
        context_manager_factory: Callable[..., Any] | None = None,
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
            summary_threshold: Message count threshold for triggering compression
                              (default: 20, lower values compress more aggressively).
            wiki_store: Optional wiki store for automatic index injection.
                         When provided, the wiki index is loaded at session
                         start and injected into the system prompt so the
                         agent knows what pages exist.
            wiki_context_config: Optional configuration for wiki context
                                 injection budget (char limits, top-k).
        """
        self.state_manager = state_manager
        self.llm_provider = llm_provider
        self._base_system_prompt = system_prompt or LEAN_KERNEL_PROMPT
        self.model_alias = model_alias
        self.tool_result_store = tool_result_store
        self.logger = logger
        self.runtime_tracker = runtime_tracker
        self.skill_manager = skill_manager

        # Wiki auto-injection (long-term memory as markdown pages)
        self._wiki_store = wiki_store
        self._wiki_context_config = wiki_context_config or WikiContextConfig()
        self._wiki_context: str | None = None

        # Skill suffix cache: (active_skill_name, suffix_string)
        self._cached_skill_suffix: tuple[str | None, str] | None = None

        # Execution limits configuration
        self.max_steps = max_steps or self.DEFAULT_MAX_STEPS
        self.max_parallel_tools = max_parallel_tools or self.DEFAULT_MAX_PARALLEL_TOOLS
        self.planning_strategy = planning_strategy or NativeReActStrategy()
        self._tool_result_store_threshold = (
            tool_result_store_threshold
            if tool_result_store_threshold is not None
            else self.TOOL_RESULT_STORE_THRESHOLD
        )

        # ReAct stall detection thresholds (read by react_loop via
        # getattr — keeps the loop loosely coupled to the agent class).
        self.react_no_progress_threshold = (
            react_no_progress_threshold
            if react_no_progress_threshold is not None
            else self.DEFAULT_REACT_NO_PROGRESS_THRESHOLD
        )
        self.react_signature_repeat_threshold = (
            react_signature_repeat_threshold
            if react_signature_repeat_threshold is not None
            else self.DEFAULT_REACT_SIGNATURE_REPEAT_THRESHOLD
        )

        # Profile-level approval bypass: tool short-names listed here
        # skip the ApprovalServiceProtocol gate even when their
        # ``requires_approval`` is True. Use for trusted single-user
        # workflows (local dev, scheduled butler runs) where a tool's
        # default HIGH risk level is overkill. The existing
        # ``auto_approve_for_origins`` trigger-origin path is unchanged.
        self._approval_bypass_tools: frozenset[str] = frozenset(approval_bypass_tools or ())

        # Approval gate dependencies are passed in as callables (not
        # service-located via application.infrastructure_overrides) to
        # keep core/domain free of application-layer imports. The
        # factory wires these to the global override lookups so tenant
        # admins can still change approval policy at runtime — the
        # callable is evaluated fresh on every gate check.
        self._approval_service_provider: Callable[[], Any | None] = (
            approval_service_provider if approval_service_provider is not None else lambda: None
        )
        self._approval_bypass_provider: Callable[[], frozenset[str]] = (
            approval_bypass_provider
            if approval_bypass_provider is not None
            else lambda: frozenset()
        )

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
            tool_message_max_chars=tool_message_max_chars,
            assistant_message_max_chars=assistant_message_max_chars,
        )

        # Context manager — single source of truth for the LLM context.
        # An injected factory (hexagonal seam) may swap in an alternative
        # backend (e.g. the ctxman service adapter); the default path is
        # the local ContextManager, unchanged.
        _context_factory = context_manager_factory or (lambda **kwargs: ContextManager(**kwargs))
        self.context = _context_factory(
            message_history_manager=self.message_history_manager,
            openai_tools=self._openai_tools,
            token_budgeter=self.token_budgeter,
            logger=self.logger,
            build_system_prompt_fn=self._build_system_prompt,
        )

        # Tool execution helpers
        self.tool_executor = ToolExecutor(
            tools=self.tools,
            logger=self.logger,
        )
        self.tool_result_message_factory = ToolResultMessageFactory(
            tool_result_store=self.tool_result_store,
            result_store_threshold=self._tool_result_store_threshold,
            logger=self.logger,
            tools=self.tools,
        )

        # State persistence helper
        self.state_store = LeanAgentStateStore(
            state_manager=self.state_manager,
            logger=self.logger,
            runtime_tracker=self.runtime_tracker,
        )

        # Resource cleanup helper
        self.resource_closer = ResourceCloser(logger=self.logger)

        # Cooperative interrupt flag.  Checked at the top of the ReAct loop so
        # callers (CLI Ctrl+C, REST cancel endpoint) can pause execution
        # between steps without losing state.  Created lazily on first access
        # because an event loop may not exist at __init__ time (e.g. when the
        # agent is constructed from sync code).
        self._interrupt_event: asyncio.Event | None = None

        # Hooks invoked synchronously when ``request_interrupt`` is called.
        # The sub-agent spawner registers a callback per spawned child so a
        # parent's interrupt propagates to running sub-agents — kept as a
        # plain callback list to avoid importing application-layer types
        # into the core (Clean Architecture).
        self._on_interrupt_callbacks: list[Callable[[], None]] = []

        # Sub-agent event forwarding.  When this agent runs as a sub-agent
        # the parent injects an asyncio.Queue here so this agent's tool
        # calls (and nested sub-agent events) get streamed back up the
        # hierarchy.  ``_agent_path`` carries the chain of specialist names
        # leading to this agent; the root agent has an empty path.
        self._sub_agent_event_sink: asyncio.Queue | None = None
        self._agent_path: list[str] = []

    def _get_interrupt_event(self) -> asyncio.Event:
        """Return (lazily creating) the asyncio.Event used for cooperative interruption."""
        if self._interrupt_event is None:
            self._interrupt_event = asyncio.Event()
        return self._interrupt_event

    def request_interrupt(self) -> None:
        """Request a cooperative pause at the next ReAct loop boundary.

        Safe to call from any coroutine on the same event loop.  The effect
        is observed at the top of the loop iteration in ``react_loop`` —
        the agent finishes the current in-flight step (LLM call + tool
        calls), persists state via the same mechanism used by ``ask_user``
        and exits gracefully with an ``INTERRUPTED`` event.

        Also fires every registered ``_on_interrupt_callbacks`` hook so
        spawned sub-agents (registered by the SubAgentSpawner) receive the
        interrupt and pause at their own loop boundary.
        """
        self._get_interrupt_event().set()
        # Defensive ``getattr`` so call sites that bypass ``__init__``
        # (test fixtures using ``Agent.__new__``) still get the legacy
        # single-flag behaviour without crashing on a missing attribute.
        callbacks = getattr(self, "_on_interrupt_callbacks", None) or []
        for callback in list(callbacks):
            try:
                callback()
            except Exception:  # pragma: no cover — best-effort propagation
                if hasattr(self, "logger"):
                    self.logger.warning(
                        "interrupt.callback_failed",
                        exc_info=True,
                    )

    def add_interrupt_callback(self, callback: Callable[[], None]) -> None:
        """Register a hook fired by :meth:`request_interrupt`.

        Used by :class:`SubAgentSpawner` to forward the parent's interrupt
        signal to children.  Returns nothing; pair every ``add_`` with a
        matching :meth:`remove_interrupt_callback` in a ``finally`` block.
        """
        self._on_interrupt_callbacks.append(callback)

    def remove_interrupt_callback(self, callback: Callable[[], None]) -> None:
        """Remove a previously registered interrupt callback.

        Silently ignores callbacks that are not registered so callers can
        deregister unconditionally in ``finally`` blocks.
        """
        try:
            self._on_interrupt_callbacks.remove(callback)
        except ValueError:
            pass

    def clear_interrupt(self) -> None:
        """Clear a pending interrupt request (called after handling it)."""
        if self._interrupt_event is not None:
            self._interrupt_event.clear()

    def is_interrupt_requested(self) -> bool:
        """Return True if an interrupt has been requested and not yet handled."""
        return self._interrupt_event is not None and self._interrupt_event.is_set()

    @property
    def system_prompt(self) -> str:
        """Return base system prompt (backward compatibility)."""
        return self._base_system_prompt

    @property
    def planner(self) -> PlannerTool | None:
        """Expose the planner instance for persistence helpers."""
        return self._planner

    async def load_memory_context(self, mission: str | None = None) -> None:
        """Load the wiki index and cache it for prompt injection.

        Called once at session start. The wiki index is small (always a
        single markdown file) so we load it unconditionally when a wiki
        store is configured — no keyword-gating needed.
        """
        if not self._wiki_store:
            return
        loader = WikiContextLoader(
            wiki_store=self._wiki_store,
            config=self._wiki_context_config,
            logger=self.logger,
        )
        self._wiki_context = await loader.load_wiki_context(mission=mission)

    def _build_system_prompt(
        self,
        mission: str | None = None,
        state: dict[str, Any] | None = None,
        messages: list[dict[str, Any]] | None = None,
    ) -> str:
        """Build system prompt with dynamic plan, context, memory, and skill injection."""
        base_prompt = self.prompt_builder.build_system_prompt(
            mission=mission,
            state=state,
            messages=messages,
        )

        # Inject cached wiki index section (long-term memory)
        if self._wiki_context:
            base_prompt += self._wiki_context

        # Inject active skill instructions if skill manager is configured
        # Uses a cache keyed on the active skill name to avoid rebuilding
        # the suffix on every ReAct iteration when the skill hasn't changed.
        if self.skill_manager:
            active_name = self.skill_manager.active_skill_name
            if (
                self._cached_skill_suffix is not None
                and self._cached_skill_suffix[0] == active_name
            ):
                base_prompt += self._cached_skill_suffix[1]
            else:
                suffix = self._build_skill_suffix(active_name)
                self._cached_skill_suffix = (active_name, suffix)
                base_prompt += suffix

        return base_prompt

    def _build_skill_suffix(self, active_skill_name: str | None) -> str:
        """Build the skill instructions suffix for the system prompt.

        Args:
            active_skill_name: Name of the currently active skill, or None.

        Returns:
            Skill suffix string to append to the system prompt.
        """
        if active_skill_name:
            skill_instructions = self.skill_manager.get_active_instructions()
            if skill_instructions:
                return (
                    f"\n\n# ACTIVE SKILL: {active_skill_name}\n\n"
                    "Follow the skill instructions below. When the skill provides "
                    "bundled resource files, use them directly via their absolute "
                    "paths instead of reimplementing their logic.\n\n"
                    f"{skill_instructions}\n"
                )
        elif self.skill_manager.has_skills:
            available = self.skill_manager.list_skills()
            skill_list = ", ".join(f"`{s}`" for s in available)
            return (
                f"\n\n# AVAILABLE SKILLS\n\n"
                f"You have {len(available)} skill(s) available that you can activate "
                f"using the `activate_skill` tool: {skill_list}\n"
                f"Activate a skill when the user's request matches its capabilities.\n"
            )
        return ""

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
        # Flush the context backend synchronously at turn end (see
        # execute_stream for the rationale — #465).
        await self._flush_context_backend()
        await self.mark_finished(
            session_id,
            result.status,
            {"final_message_length": len(result.final_message or "")},
        )
        return result

    async def _flush_context_backend(self) -> None:
        """Best-effort flush of the context manager's pending remote state.

        No-op for context backends that don't expose ``flush`` (the local
        ContextManager keeps everything in-process). Flushing must never break
        the turn, so all errors are swallowed and logged.
        """
        context = getattr(self, "context", None)
        flush = getattr(context, "flush", None)
        if not callable(flush):
            return
        try:
            await flush()
        except Exception as exc:  # noqa: BLE001 — flush must never break the turn
            self.logger.warning("context_flush_failed", error=str(exc))

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

        final_message = ""
        status = ExecutionStatus.COMPLETED.value
        interrupt_info: dict[str, Any] | None = None
        last_error_message: str = ""
        last_error_kind: str = ""
        stream = self.planning_strategy.execute_stream(self, mission, session_id)
        async for event in stream:  # type: ignore[union-attr]
            yield event
            # Track final answer content for COMPLETE event
            if event.event_type == EventType.FINAL_ANSWER:
                final_message = event.data.get("content", "")
            elif event.event_type == EventType.ERROR:
                status = ExecutionStatus.FAILED.value
                msg = event.data.get("message")
                if isinstance(msg, str) and msg:
                    last_error_message = msg
                kind = event.data.get("error_kind")
                if isinstance(kind, str) and kind:
                    last_error_kind = kind
            elif event.event_type == EventType.INTERRUPTED:
                status = ExecutionStatus.PAUSED.value
                interrupt_info = dict(event.data)
                final_message = final_message or "Execution paused by user."

        # Flush the context backend's pending segments now — synchronously, at
        # turn end — so the final assistant answer reaches the session before
        # post-mission work / the deferred close, which can hang or be
        # cancelled when the next turn arrives and would then drop the reply
        # (#465). No-op for the in-process local backend.
        await self._flush_context_backend()

        # When the planning strategy errored without producing a
        # FINAL_ANSWER, build a user-facing message from the structured
        # error so downstream consumers (gateway → user) see the real
        # cause instead of falling back to a generic "etwas ist
        # schiefgelaufen" line.
        if not final_message and last_error_message:
            from taskforce.core.domain.planning.react_loop import (
                build_user_message_for_error,
            )

            final_message = build_user_message_for_error(last_error_kind, last_error_message)

        complete_data: dict[str, Any] = {
            "status": status,
            "session_id": session_id,
            "final_message": final_message,
        }
        if last_error_kind:
            complete_data["error_kind"] = last_error_kind
        if interrupt_info is not None:
            complete_data["interrupt"] = interrupt_info

        # Yield COMPLETE event for executor.execute_mission() compatibility
        yield StreamEvent(
            event_type=EventType.COMPLETE,
            data=complete_data,
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
        session_id: str | None = None,
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
        # Inject parent session ID for orchestration tools (AgentTool, SubAgentTool)
        tool = self.tool_executor.get_tool(tool_name)
        if tool and getattr(tool, "requires_parent_session", False) and session_id:
            tool_args = {
                **tool_args,
                "_parent_session_id": session_id,
                # Forward the active event sink and agent path so nested
                # sub-agents can stream their tool calls back to the root.
                "_parent_event_sink": self._sub_agent_event_sink,
                "_parent_agent_path": list(self._agent_path),
            }

        # Approval gate: when an ``ApprovalServiceProtocol`` is
        # installed and the tool declares ``requires_approval=True``,
        # block on the service's decision before invoking the tool.
        # Rejected attempts return a structured error payload with
        # ``approval_status`` so the LLM sees the denial as a normal
        # tool result and can react in its next turn.
        approval_block = await self._maybe_request_approval(
            tool=tool,
            tool_name=tool_name,
            tool_args=tool_args,
            session_id=session_id,
        )
        if approval_block is not None:
            return approval_block

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

        return result

    async def _maybe_request_approval(
        self,
        *,
        tool: Any,
        tool_name: str,
        tool_args: dict[str, Any],
        session_id: str | None,
    ) -> dict[str, Any] | None:
        """Run the approval gate for ``tool``. Returns ``None`` to proceed.

        Returns a structured deny/timeout/error payload when the gate
        refuses to grant. The result distinguishes three failure
        modes via ``approval_status``:

        * ``denied`` — a human said no.
        * ``timed_out`` — no admin acted in time.
        * ``error`` — the approval service itself failed (queue full,
          network, programmer error). Distinct so an LLM / forensic
          reviewer can tell "user said no" apart from "the pipeline
          broke".

        All deny/timeout/error payloads carry ``terminal_failure: True``
        so a planning loop knows the tool will not succeed by retry.
        Tools whose params fail ``validate_params`` are rejected
        without bothering the admin (a malformed call cannot be
        granted meaningfully).

        When no service is installed or the tool does not require
        approval, the gate is skipped and ``None`` is returned.
        """
        if tool is None:
            return None
        if not getattr(tool, "requires_approval", False):
            return None

        # Two-source bypass:
        #   1. Per-agent profile YAML (``agent.approval_bypass_tools``)
        #   2. Tenant-level settings store (``approval`` section), UI-edited
        # UNION semantics: a tool short-name in EITHER set skips the gate.
        # ``getattr`` tolerates stubs / tests that don't construct the
        # full Agent. The tenant-level override is read here (not cached
        # at __init__) so UI edits take effect on the next tool call.
        profile_bypass = getattr(self, "_approval_bypass_tools", frozenset())
        # Stubs / subclasses that omit the provider default to "no
        # tenant-level bypass" — same defensive pattern as
        # ``_approval_bypass_tools`` above.
        bypass_provider = getattr(self, "_approval_bypass_provider", None)
        tenant_bypass = bypass_provider() if bypass_provider is not None else frozenset()
        if tool_name in profile_bypass or tool_name in tenant_bypass:
            self.logger.info(
                "tool.approval.bypassed_by_profile",
                tool_name=tool_name,
                reason=(
                    "profile_approval_bypass_list"
                    if tool_name in profile_bypass
                    else "tenant_approval_bypass_settings"
                ),
            )
            return None

        service_provider = getattr(self, "_approval_service_provider", None)
        service = service_provider() if service_provider is not None else None
        if service is None:
            self.logger.debug(
                "tool.approval.no_service_installed",
                tool_name=tool_name,
            )
            return None

        # Validate params *before* asking the admin. A malformed call
        # cannot be granted meaningfully — surface the validation
        # error to the LLM right away so a retry with corrected args
        # can re-enter the gate cleanly.
        validate = getattr(tool, "validate_params", None)
        if callable(validate):
            try:
                outcome = validate(**tool_args)
            except Exception as exc:  # noqa: BLE001 — surface to LLM
                self.logger.info(
                    "tool.approval.params_invalid",
                    tool_name=tool_name,
                    error=str(exc),
                )
                return {
                    "success": False,
                    "tool_name": tool_name,
                    "error": f"invalid params: {exc}",
                    "error_kind": "invalid_params",
                    "terminal_failure": False,
                }
            # ToolProtocol.validate_params returns (is_valid, error_msg).
            # Older custom tools may return None / a bool — accept both.
            valid = True
            error_msg: str | None = None
            if isinstance(outcome, tuple) and len(outcome) == 2:
                valid, error_msg = bool(outcome[0]), outcome[1]
            elif isinstance(outcome, bool):
                valid = outcome
            if not valid:
                self.logger.info(
                    "tool.approval.params_invalid",
                    tool_name=tool_name,
                    error=error_msg,
                )
                return {
                    "success": False,
                    "tool_name": tool_name,
                    "error": f"invalid params: {error_msg or 'validation failed'}",
                    "error_kind": "invalid_params",
                    "terminal_failure": False,
                }

        from taskforce.core.domain.approval import (
            ApprovalRequest,
            ApprovalStatus,
        )
        from taskforce.core.domain.trigger_context import get_trigger_origin
        from taskforce.core.interfaces.tools import ApprovalRiskLevel

        risk = getattr(tool, "approval_risk_level", ApprovalRiskLevel.LOW)
        try:
            preview_method = getattr(tool, "get_approval_preview", None)
            preview = preview_method(**tool_args) if callable(preview_method) else tool_name
        except Exception:  # noqa: BLE001 — preview is best-effort
            preview = tool_name

        # Auto-approve path (issue #177): when the active execution
        # carries a trigger origin (typically scheduler-fired workflow)
        # and the tool opted in via ``auto_approve_for_origins``, skip
        # the human-decision queue. Interactive flows have no origin
        # set and continue to hit the queue unchanged.
        origin = get_trigger_origin()
        auto_origins = getattr(tool, "auto_approve_for_origins", frozenset()) or frozenset()
        if origin is not None and origin in auto_origins:
            self.logger.info(
                "tool.approval.auto_granted",
                tool_name=tool_name,
                trigger_origin=origin,
                reason="trigger_origin_whitelisted",
            )
            return None

        import uuid

        metadata: dict[str, Any] = {}
        if origin is not None:
            metadata["trigger_origin"] = origin

        request = ApprovalRequest(
            request_id=str(uuid.uuid4()),
            session_id=session_id or "",
            tool_name=tool_name,
            tool_params=dict(tool_args),
            risk_level=risk,
            preview=str(preview),
            metadata=metadata,
        )
        try:
            decision = await service.request_approval(request)
        except Exception as exc:  # noqa: BLE001 — service must not break the agent
            self.logger.error(
                "tool.approval.service_failed",
                tool_name=tool_name,
                error=str(exc),
            )
            return {
                "success": False,
                "tool_name": tool_name,
                "error": f"approval service failed: {exc}",
                "approval_status": ApprovalStatus.ERROR.value,
                "error_kind": "approval_error",
                "approval_reason": str(exc),
                "terminal_failure": True,
            }

        if decision.granted:
            self.logger.info(
                "tool.approval.granted",
                tool_name=tool_name,
                request_id=request.request_id,
                decided_by=decision.decided_by,
            )
            return None

        # Not granted — surface the reason to the LLM via the result
        # dict and signal terminal failure so the planning loop does
        # not retry the same forbidden action.
        self.logger.info(
            "tool.approval.refused",
            tool_name=tool_name,
            request_id=request.request_id,
            status=decision.status.value,
            decided_by=decision.decided_by,
            reason=decision.reason,
        )
        if decision.status is ApprovalStatus.DENIED:
            message = "User denied execution. Do NOT retry the same action — ask the user instead."
            error_kind = "approval_denied"
        elif decision.status is ApprovalStatus.TIMED_OUT:
            message = "Approval timed out. Do NOT retry without explicit user input."
            error_kind = "approval_timeout"
        else:  # ERROR
            message = "Approval pipeline failed. Do NOT retry; surface the failure to the user."
            error_kind = "approval_error"
        return {
            "success": False,
            "tool_name": tool_name,
            "error": message,
            "approval_status": decision.status.value,
            "error_kind": error_kind,
            "approval_decided_by": decision.decided_by,
            "approval_reason": decision.reason,
            "terminal_failure": True,
        }

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

        return str(self.skill_manager.enhance_prompt(self._base_system_prompt))

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
        name: str | None = self.skill_manager.active_skill_name
        return name

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
        # Remote context-manager backends (e.g. ctxman) hold an HTTP client
        context_aclose = getattr(self.context, "aclose", None)
        if context_aclose is not None:
            try:
                await context_aclose()
            except Exception as exc:  # noqa: BLE001 — close must not fail shutdown
                self.logger.warning("context_manager_close_failed", error=str(exc))
        self.logger.debug("agent_closed")


# Backwards-compatible alias (deprecated).
LeanAgent = Agent

__all__ = ["Agent", "LeanAgent"]
