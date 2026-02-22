"""
Application Layer - Agent Executor Service

This module provides the service layer orchestrating agent execution.
Both CLI and API entrypoints use this unified execution logic.

The AgentExecutor:
- Creates agents using AgentFactory based on profile
- Manages session lifecycle (load/create state)
- Executes agent ReAct loop
- Provides progress tracking via callbacks or streaming
- Handles comprehensive structured logging
- Provides error handling with clear messages
"""

import asyncio
import uuid
from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Any

import structlog

from taskforce.application.factory import AgentFactory
from taskforce.application.task_complexity_classifier import TaskComplexityClassifier
from taskforce.core.domain.agent import Agent
from taskforce.core.domain.agent_models import (
    CustomAgentDefinition,
    PluginAgentDefinition,
)
from taskforce.core.domain.config_schema import AutoEpicConfig
from taskforce.core.domain.enums import EventType, ExecutionStatus
from taskforce.core.domain.epic import TaskComplexity
from taskforce.core.domain.errors import (
    CancelledError,
    NotFoundError,
    TaskforceError,
    ValidationError,
)
from taskforce.core.domain.exceptions import AgentExecutionError
from taskforce.core.domain.models import ExecutionResult, StreamEvent

logger = structlog.get_logger()


@dataclass
class ProgressUpdate:
    """Progress update during execution.

    Represents a single event during agent execution that can be
    streamed to consumers for real-time progress tracking.

    Attributes:
        timestamp: When this update occurred
        event_type: Type of event (see EventType enum)
        message: Human-readable message describing the event
        details: Additional structured data about the event
    """

    timestamp: datetime
    event_type: EventType | str  # Allow string for backward compatibility
    message: str
    details: dict[str, Any]

    @property
    def event_type_value(self) -> str:
        """Get event type as string value."""
        if isinstance(self.event_type, EventType):
            return self.event_type.value
        return self.event_type


class AgentExecutor:
    """Service layer orchestrating agent execution.

    Provides unified execution logic used by both CLI and API entrypoints.
    Handles agent creation, session management, execution orchestration,
    progress tracking, and comprehensive logging.

    This service layer decouples the domain logic (Agent) from the
    presentation layer (CLI/API), enabling consistent behavior across
    different interfaces.
    """

    def __init__(self, factory: AgentFactory | None = None):
        """Initialize AgentExecutor with optional factory.

        Args:
            factory: Optional AgentFactory instance. If not provided,
                    creates a default factory.
        """
        self.factory = factory or AgentFactory()
        self.logger = logger.bind(component="agent_executor")

    async def execute_mission(
        self,
        mission: str,
        profile: str = "dev",
        session_id: str | None = None,
        conversation_history: list[dict[str, Any]] | None = None,
        progress_callback: Callable[[ProgressUpdate], None] | None = None,
        user_context: dict[str, Any] | None = None,
        agent_id: str | None = None,
        planning_strategy: str | None = None,
        planning_strategy_params: dict[str, Any] | None = None,
        plugin_path: str | None = None,
        auto_epic: bool | None = None,
    ) -> ExecutionResult:
        """Execute Agent mission with comprehensive orchestration.

        Main entry point for mission execution. Orchestrates the complete
        workflow from agent creation through execution to result delivery.

        Workflow:
        1. Create Agent using factory based on profile
        2. Generate or use provided session ID
        3. Execute Agent ReAct loop with progress tracking
        4. Log execution metrics and status
        5. Return execution result

        Args:
            mission: Mission description (what to accomplish)
            profile: Configuration profile (dev/staging/prod)
            session_id: Optional existing session to resume
            conversation_history: Optional conversation history for chat context
            progress_callback: Optional callback for progress updates
            user_context: Optional user context for RAG security filtering
                         (user_id, org_id, scope)
            agent_id: Optional custom agent ID. If provided, loads agent
                     definition from configs/custom/{agent_id}.yaml
            planning_strategy: Optional planning strategy override
                              (native_react, plan_and_execute, plan_and_react, spar)
            planning_strategy_params: Optional params for planning strategy
            plugin_path: Optional path to external plugin directory
                        (e.g., examples/accounting_agent)
            auto_epic: Auto-epic detection. None=read from profile config,
                      True=force enabled, False=force disabled.

        Returns:
            ExecutionResult with completion status and history

        Raises:
            Exception: If agent creation or execution fails
        """
        # Delegate to streaming implementation and collect result
        result: ExecutionResult | None = None
        async for update in self.execute_mission_streaming(
            mission=mission,
            profile=profile,
            session_id=session_id,
            conversation_history=conversation_history,
            user_context=user_context,
            agent_id=agent_id,
            planning_strategy=planning_strategy,
            planning_strategy_params=planning_strategy_params,
            plugin_path=plugin_path,
            auto_epic=auto_epic,
        ):
            # Forward progress updates to callback if provided
            if progress_callback:
                progress_callback(update)

            # Extract result from complete event
            event_type = update.event_type if isinstance(update.event_type, EventType) else update.event_type
            if event_type == EventType.COMPLETE or event_type == EventType.COMPLETE.value:
                result = ExecutionResult(
                    status=update.details.get("status", ExecutionStatus.COMPLETED.value),
                    final_message=update.message,
                    session_id=update.details.get("session_id", ""),
                    todolist_id=update.details.get("todolist_id"),
                    execution_history=[],
                )

        if result is None:
            raise AgentExecutionError(
                "No completion event received from streaming execution",
                session_id=session_id,
            )

        return result

    async def execute_mission_streaming(
        self,
        mission: str,
        profile: str = "dev",
        session_id: str | None = None,
        conversation_history: list[dict[str, Any]] | None = None,
        user_context: dict[str, Any] | None = None,
        agent_id: str | None = None,
        planning_strategy: str | None = None,
        planning_strategy_params: dict[str, Any] | None = None,
        agent: Agent | None = None,
        plugin_path: str | None = None,
        auto_epic: bool | None = None,
    ) -> AsyncIterator[ProgressUpdate]:
        """Execute Agent mission with streaming progress updates.

        Yields ProgressUpdate objects as execution progresses, enabling
        real-time feedback to consumers (CLI progress bars, API SSE, etc).

        When auto_epic is enabled, the mission is first classified for
        complexity. If classified as epic with sufficient confidence,
        execution is delegated to the EpicOrchestrator instead.

        Args:
            mission: Mission description
            profile: Configuration profile (dev/staging/prod)
            session_id: Optional existing session to resume
            conversation_history: Optional conversation history for chat context
            user_context: Optional user context for RAG security filtering
            agent_id: Optional custom agent ID. If provided, loads agent
                     definition from configs/custom/{agent_id}.yaml
            planning_strategy: Optional planning strategy override
            planning_strategy_params: Optional params for planning strategy
            agent: Optional pre-created Agent instance. If provided, skips
                  agent creation and uses this agent directly.
            plugin_path: Optional path to external plugin directory
                        (e.g., examples/accounting_agent)
            auto_epic: Auto-epic detection. None=read from profile config,
                      True=force enabled, False=force disabled.

        Yields:
            ProgressUpdate objects for each execution event

        Raises:
            Exception: If agent creation or execution fails
        """
        resolved_session_id = self._resolve_session_id(session_id)
        owns_agent = agent is None

        yield ProgressUpdate(
            timestamp=datetime.now(),
            event_type=EventType.STARTED,
            message=f"Starting mission: {mission[:80]}",
            details={
                "session_id": resolved_session_id,
                "profile": profile,
                "agent_id": agent_id,
                "plugin_path": plugin_path,
            },
        )

        self.logger.info(
            "mission.streaming.started",
            mission=mission[:100],
            profile=profile,
            session_id=resolved_session_id,
            has_user_context=user_context is not None,
            agent_id=agent_id,
            plugin_path=plugin_path,
        )

        # --- Auto-epic classification ---
        # Only classify when no pre-created agent is passed (avoids
        # double-classification when called from epic orchestrator itself).
        if agent is None and auto_epic is not False:
            epic_update = await self._classify_and_route_epic(
                mission=mission,
                profile=profile,
                auto_epic=auto_epic,
            )
            if epic_update is not None:
                # Mission classified as epic — yield escalation event,
                # then delegate to epic orchestrator.
                yield epic_update
                async for update in self._execute_epic_streaming(
                    mission=mission,
                    profile=profile,
                    auto_epic_config=self._resolve_auto_epic_config(profile),
                ):
                    yield update
                return

        if agent is None:
            agent = await self._create_agent(
                profile,
                user_context=user_context,
                agent_id=agent_id,
                planning_strategy=planning_strategy,
                planning_strategy_params=planning_strategy_params,
                plugin_path=plugin_path,
            )

        await self._maybe_store_conversation_history(
            agent=agent,
            session_id=resolved_session_id,
            conversation_history=conversation_history,
        )

        try:
            async for update in self._execute_streaming(
                agent, mission, resolved_session_id
            ):
                yield update

            self.logger.info(
                "mission.streaming.completed",
                session_id=resolved_session_id,
                agent_id=agent_id,
                plugin_path=plugin_path,
            )

        except asyncio.CancelledError as e:
            self.logger.warning(
                "mission.streaming.cancelled",
                session_id=resolved_session_id,
                error=str(e),
                agent_id=agent_id,
                plugin_path=plugin_path,
            )

            yield ProgressUpdate(
                timestamp=datetime.now(),
                event_type=EventType.ERROR,
                message=f"Execution cancelled: {str(e)}",
                details={"error": str(e), "error_type": type(e).__name__},
            )

            raise CancelledError(
                f"Mission streaming cancelled: {str(e)}",
                details={"session_id": resolved_session_id},
            ) from e
        except Exception as e:
            self._log_execution_failure(
                event_name="mission.streaming.failed",
                error=e,
                session_id=resolved_session_id,
                agent_id=agent_id,
                plugin_path=plugin_path,
            )

            # Yield error event
            yield ProgressUpdate(
                timestamp=datetime.now(),
                event_type=EventType.ERROR,
                message=f"Execution failed: {str(e)}",
                details={"error": str(e), "error_type": type(e).__name__},
            )

            raise self._wrap_exception(
                e,
                context="Mission streaming failed",
                session_id=resolved_session_id,
                agent_id=agent_id,
            ) from e

        finally:
            # Clean up MCP connections if we created the agent
            if agent and owns_agent:
                await agent.close()

    async def _create_agent(
        self,
        profile: str,
        user_context: dict[str, Any] | None = None,
        agent_id: str | None = None,
        planning_strategy: str | None = None,
        planning_strategy_params: dict[str, Any] | None = None,
        plugin_path: str | None = None,
    ) -> Agent:
        """Create Agent using factory.

        Creates Agent instance using native tool calling and PlannerTool:
        - plugin_path provided: Creates agent with plugin tools
        - agent_id provided: Loads custom agent definition from registry
        - Otherwise: Creates standard Agent with optional user_context for RAG

        Args:
            profile: Configuration profile name
            user_context: Optional user context for RAG security filtering
            agent_id: Optional custom agent ID to load from registry
            planning_strategy: Optional planning strategy override
            planning_strategy_params: Optional planning strategy parameters
            plugin_path: Optional path to external plugin directory

        Returns:
            Agent instance with injected dependencies

        Raises:
            FileNotFoundError: If agent_id provided but not found (404)
            ValueError: If agent definition is invalid/corrupt (400)
        """
        self.logger.debug(
            "creating_lean_agent",
            profile=profile,
            has_user_context=user_context is not None,
            agent_id=agent_id,
            planning_strategy=planning_strategy,
            plugin_path=plugin_path,
        )

        # plugin_path takes highest priority - create agent with plugin
        if plugin_path:
            self.logger.info(
                "creating_agent_with_plugin",
                plugin_path=plugin_path,
                profile=profile,
            )
            return await self.factory.create_agent_with_plugin(
                plugin_path=plugin_path,
                profile=profile,
                user_context=user_context,
                planning_strategy=planning_strategy,
                planning_strategy_params=planning_strategy_params,
            )

        # agent_id takes second priority - load agent definition from registry
        if agent_id:
            # Validate agent_id format: reject slashes
            if "/" in agent_id:
                raise ValidationError(
                    f"Invalid agent_id format: '{agent_id}'. "
                    f"Agent IDs cannot contain slashes. "
                    f"Use 'profile' parameter instead (e.g., profile='{agent_id.split('/')[0]}').",
                    details={"agent_id": agent_id},
                )

            from taskforce.application.factory import get_base_path
            from taskforce.infrastructure.persistence.file_agent_registry import (
                FileAgentRegistry,
            )

            registry = FileAgentRegistry(base_path=get_base_path())
            agent_response = registry.get_agent(agent_id)

            if not agent_response:
                raise NotFoundError(
                    f"Agent '{agent_id}' not found",
                    details={"agent_id": agent_id},
                )

            # Handle plugin agents
            if isinstance(agent_response, PluginAgentDefinition):
                # Resolve relative plugin_path to absolute path
                base_path = get_base_path()
                plugin_path_abs = (base_path / agent_response.plugin_path).resolve()

                self.logger.info(
                    "loading_plugin_agent",
                    agent_id=agent_id,
                    plugin_path=str(plugin_path_abs),
                )

                return await self.factory.create_agent_with_plugin(
                    plugin_path=str(plugin_path_abs),
                    profile=profile,
                    user_context=user_context,
                    planning_strategy=planning_strategy,
                    planning_strategy_params=planning_strategy_params,
                )

            # Handle custom agents
            if isinstance(agent_response, CustomAgentDefinition):
                self.logger.info(
                    "loading_custom_agent",
                    agent_id=agent_id,
                    agent_name=agent_response.name,
                    tool_count=len(agent_response.tool_allowlist),
                )

                # Use new unified API with inline parameters
                return await self.factory.create_agent(
                    system_prompt=agent_response.system_prompt,
                    tools=agent_response.tool_allowlist,
                    mcp_servers=agent_response.mcp_servers,
                    planning_strategy=planning_strategy,
                    planning_strategy_params=planning_strategy_params,
                )

            # Profile agents should use profile parameter
            raise ValidationError(
                f"Agent '{agent_id}' is a profile agent, not a custom or plugin agent. "
                "Use 'profile' parameter for profile agents.",
                details={"agent_id": agent_id, "source": agent_response.source},
            )

        # Standard Agent creation - but first check if profile name matches a plugin agent
        # This allows using profile="accounting_agent" instead of agent_id="accounting_agent"
        from taskforce.application.factory import get_base_path
        from taskforce.infrastructure.persistence.file_agent_registry import (
            FileAgentRegistry,
        )

        registry = FileAgentRegistry(base_path=get_base_path())
        agent_response = registry.get_agent(profile)

        # If profile name matches a plugin agent, use it as plugin
        if isinstance(agent_response, PluginAgentDefinition):
            base_path = get_base_path()
            plugin_path_abs = (base_path / agent_response.plugin_path).resolve()

            self.logger.info(
                "profile_matches_plugin_agent",
                profile=profile,
                plugin_path=str(plugin_path_abs),
                hint=(
                    "Using profile name as plugin agent. "
                    "Consider using agent_id parameter instead."
                ),
            )

            # Use "dev" as infrastructure profile since the plugin name
            # doesn't correspond to a real profile
            return await self.factory.create_agent_with_plugin(
                plugin_path=str(plugin_path_abs),
                profile="dev",  # Use default profile for infrastructure
                user_context=user_context,
                planning_strategy=planning_strategy,
                planning_strategy_params=planning_strategy_params,
            )

        # Standard Agent creation with config file
        return await self.factory.create_agent(
            config=profile,
            user_context=user_context,
            planning_strategy=planning_strategy,
            planning_strategy_params=planning_strategy_params,
        )

    async def _execute_with_progress(
        self,
        agent: Agent,
        mission: str,
        session_id: str,
        progress_callback: Callable[[ProgressUpdate], None] | None,
    ) -> ExecutionResult:
        """Execute agent with progress tracking via callback.

        Wraps agent execution to intercept events and send progress updates
        through the provided callback function.

        Args:
            agent: Agent instance to execute
            mission: Mission description
            session_id: Session identifier
            progress_callback: Optional callback for progress updates

        Returns:
            ExecutionResult from agent execution
        """
        # If no callback provided, execute directly
        if not progress_callback:
            return await agent.execute(mission=mission, session_id=session_id)

        # Execute agent and track progress
        # Note: Current Agent implementation doesn't support event_callback
        # For now, we execute directly and send completion update
        result = await agent.execute(mission=mission, session_id=session_id)

        # Send completion update
        progress_callback(
            ProgressUpdate(
                timestamp=datetime.now(),
                event_type=EventType.COMPLETE,
                message=result.final_message,
                details={
                    "status": result.status_value if hasattr(result, "status_value") else result.status,
                    "session_id": result.session_id,
                    "todolist_id": result.todolist_id,
                },
            )
        )

        return result

    async def _execute_streaming(
        self, agent: Agent, mission: str, session_id: str
    ) -> AsyncIterator[ProgressUpdate]:
        """Execute agent with streaming progress updates.

        Uses true streaming if agent supports execute_stream(), otherwise
        falls back to post-hoc streaming from execution history.

        Args:
            agent: Agent instance to execute
            mission: Mission description
            session_id: Session identifier

        Yields:
            ProgressUpdate objects for execution events
        """
        # Check if agent supports streaming (Agent has execute_stream)
        # Also verify it's a real method, not a Mock attribute
        execute_stream_method = getattr(agent, "execute_stream", None)
        is_real_method = (
            execute_stream_method is not None
            and callable(execute_stream_method)
            and not str(type(execute_stream_method).__module__).startswith("unittest.mock")
        )

        if is_real_method:
            # True streaming: yield events as they happen
            async for event in agent.execute_stream(mission, session_id):
                yield self._stream_event_to_progress_update(event)
        else:
            # Fallback: post-hoc streaming from execution history
            result = await agent.execute(mission=mission, session_id=session_id)

            # Yield updates based on execution history
            for event in result.execution_history:
                # execution_history items are dicts
                if isinstance(event, dict):
                    event_type_str = event.get("type", "unknown")
                    step = event.get("step", "?")
                    data: dict[str, Any] = event.get("data", {})
                else:
                    et = event.event_type
                    event_type_str = et.value if isinstance(et, EventType) else str(et)
                    step = "?"
                    data = event.data

                if event_type_str == "thought":
                    rationale = data.get("rationale", "") if isinstance(data, dict) else ""
                    yield ProgressUpdate(
                        timestamp=datetime.now(),
                        event_type="thought",
                        message=f"Step {step}: {rationale[:80]}",
                        details=data,
                    )

                elif event_type_str == "observation":
                    success = (
                        data.get("success", False) if isinstance(data, dict) else False
                    )
                    obs_status = (
                        ExecutionStatus.COMPLETED.value
                        if success
                        else ExecutionStatus.FAILED.value
                    )
                    yield ProgressUpdate(
                        timestamp=datetime.now(),
                        event_type="observation",
                        message=f"Step {step}: {obs_status}",
                        details=data,
                    )

            # Yield final completion update
            status_value = (
                result.status_value
                if hasattr(result, "status_value")
                else result.status
            )
            yield ProgressUpdate(
                timestamp=datetime.now(),
                event_type=EventType.COMPLETE,
                message=result.final_message,
                details={
                    "status": status_value,
                    "session_id": result.session_id,
                    "todolist_id": result.todolist_id,
                },
            )

    def _stream_event_to_progress_update(self, event: StreamEvent) -> ProgressUpdate:
        """Convert StreamEvent to ProgressUpdate for API consumers.

        Maps Agent StreamEvent types to human-readable messages
        for CLI and API streaming consumers.

        Args:
            event: StreamEvent from agent execution

        Returns:
            ProgressUpdate for consumer display
        """
        message_map = {
            EventType.STEP_START.value: lambda d: f"Step {d.get('step', '?')} starting...",
            EventType.LLM_TOKEN.value: lambda d: d.get("content", ""),
            EventType.TOOL_CALL.value: lambda d: f"🔧 Calling: {d.get('tool', 'unknown')}",
            EventType.TOOL_RESULT.value: lambda d: (
                f"{'✅' if d.get('success') else '❌'} "
                f"{d.get('tool', 'unknown')}: {str(d.get('output', ''))[:50]}"
            ),
            EventType.ASK_USER.value: lambda d: f"❓ {d.get('question', 'User input required')}",
            EventType.PLAN_UPDATED.value: lambda d: f"📋 Plan updated ({d.get('action', 'unknown')})",
            EventType.TOKEN_USAGE.value: lambda d: f"🎯 Tokens: {d.get('total_tokens', 0)}",
            EventType.FINAL_ANSWER.value: lambda d: d.get("content", ""),
            EventType.COMPLETE.value: lambda d: (
                f"✅ Execution completed. Status: {d.get('status', 'unknown')}"
            ),
            EventType.ERROR.value: lambda d: f"⚠️ Error: {d.get('message', 'unknown')}",
        }

        event_type_value = (
            event.event_type.value
            if isinstance(event.event_type, EventType)
            else event.event_type
        )
        message_fn = message_map.get(event_type_value, lambda d: str(d))

        return ProgressUpdate(
            timestamp=event.timestamp,
            event_type=event.event_type,
            message=message_fn(event.data),
            details=event.data,
        )

    # ------------------------------------------------------------------
    # Auto-epic helpers
    # ------------------------------------------------------------------

    def _resolve_auto_epic_config(self, profile: str) -> AutoEpicConfig | None:
        """Load auto-epic configuration from profile YAML.

        Args:
            profile: Profile name to load.

        Returns:
            AutoEpicConfig if the profile has orchestration.auto_epic settings,
            otherwise None.
        """
        try:
            config = self.factory.profile_loader.load_safe(profile)
        except Exception:
            return None

        orchestration = config.get("orchestration", {}) or {}
        auto_epic_raw = orchestration.get("auto_epic")
        if not auto_epic_raw or not isinstance(auto_epic_raw, dict):
            return None

        try:
            return AutoEpicConfig(**auto_epic_raw)
        except Exception:
            self.logger.warning("auto_epic.config_parse_error", profile=profile)
            return None

    async def _classify_and_route_epic(
        self,
        mission: str,
        profile: str,
        auto_epic: bool | None,
    ) -> ProgressUpdate | None:
        """Classify mission complexity and decide whether to escalate to epic.

        Args:
            mission: The mission text.
            profile: Active profile name (for loading config).
            auto_epic: Explicit override (True=force, False=skip, None=from config).

        Returns:
            A ProgressUpdate with EPIC_ESCALATION event if escalation is warranted,
            or None to continue with standard execution.
        """
        epic_config = self._resolve_auto_epic_config(profile)

        # Determine effective enabled state
        if auto_epic is True:
            # Forced on — use defaults if no config present
            if epic_config is None:
                epic_config = AutoEpicConfig(enabled=True)
        elif epic_config is None or not epic_config.enabled:
            return None

        # Create a lightweight LLM provider for classification
        try:
            profile_config = self.factory.profile_loader.load_safe(profile)
            llm_provider = self.factory._create_llm_provider(profile_config)
        except Exception:
            self.logger.warning("auto_epic.llm_creation_failed", profile=profile)
            return None

        classifier = TaskComplexityClassifier(
            llm_provider=llm_provider,
            model=epic_config.classifier_model,
        )
        classification = await classifier.classify(mission)

        self.logger.info(
            "auto_epic.classification_result",
            complexity=classification.complexity.value,
            confidence=classification.confidence,
            reasoning=classification.reasoning,
            threshold=epic_config.confidence_threshold,
        )

        if (
            classification.complexity != TaskComplexity.EPIC
            or classification.confidence < epic_config.confidence_threshold
        ):
            return None

        worker_count = classification.suggested_worker_count or epic_config.default_worker_count

        return ProgressUpdate(
            timestamp=datetime.now(),
            event_type=EventType.EPIC_ESCALATION,
            message=(
                f"Mission classified as complex — escalating to Epic Orchestration "
                f"({classification.reasoning})"
            ),
            details={
                "complexity": classification.complexity.value,
                "confidence": classification.confidence,
                "reasoning": classification.reasoning,
                "worker_count": worker_count,
                "estimated_tasks": classification.estimated_task_count,
            },
        )

    async def _execute_epic_streaming(
        self,
        mission: str,
        profile: str,
        auto_epic_config: AutoEpicConfig | None,
    ) -> AsyncIterator[ProgressUpdate]:
        """Execute mission via EpicOrchestrator and yield progress updates.

        Args:
            mission: The mission text.
            profile: Active profile name.
            auto_epic_config: Resolved auto-epic configuration.

        Yields:
            ProgressUpdate events for the epic execution.
        """
        from taskforce.application.epic_orchestrator import EpicOrchestrator

        cfg = auto_epic_config or AutoEpicConfig(enabled=True)
        orchestrator = EpicOrchestrator(factory=self.factory)

        try:
            result = await orchestrator.run_epic(
                mission=mission,
                planner_profile=cfg.planner_profile,
                worker_profile=cfg.worker_profile,
                judge_profile=cfg.judge_profile,
                worker_count=cfg.default_worker_count,
                max_rounds=cfg.default_max_rounds,
            )

            completed_count = sum(
                1 for r in result.worker_results if r.status == "completed"
            )

            yield ProgressUpdate(
                timestamp=datetime.now(),
                event_type=EventType.COMPLETE,
                message=result.judge_summary or "Epic orchestration completed",
                details={
                    "status": result.status,
                    "session_id": result.run_id,
                    "run_id": result.run_id,
                    "tasks_completed": completed_count,
                    "tasks_total": len(result.tasks),
                    "rounds": len(result.round_summaries),
                    "epic_mode": True,
                },
            )
        except Exception as e:
            self.logger.exception("auto_epic.execution_failed", error=str(e))
            yield ProgressUpdate(
                timestamp=datetime.now(),
                event_type=EventType.ERROR,
                message=f"Epic orchestration failed: {e}",
                details={"error": str(e), "error_type": type(e).__name__},
            )

    def _log_execution_failure(
        self,
        event_name: str,
        error: Exception,
        session_id: str,
        agent_id: str | None,
        duration_seconds: float | None = None,
        plugin_path: str | None = None,
    ) -> None:
        error_context = self._extract_error_context(
            error=error, session_id=session_id, agent_id=agent_id
        )

        log_payload: dict[str, Any] = {
            "session_id": error_context["session_id"],
            "agent_id": error_context["agent_id"],
            "tool_name": error_context["tool_name"],
            "error_code": error_context["error_code"],
            "error": str(error),
            "error_type": type(error).__name__,
        }

        if duration_seconds is not None:
            log_payload["duration_seconds"] = duration_seconds
        if plugin_path is not None:
            log_payload["plugin_path"] = plugin_path

        self.logger.exception(event_name, **log_payload)

    def _extract_error_context(
        self,
        error: Exception,
        session_id: str,
        agent_id: str | None,
    ) -> dict[str, str | None]:
        return {
            "session_id": getattr(error, "session_id", None) or session_id,
            "agent_id": getattr(error, "agent_id", None) or agent_id,
            "tool_name": getattr(error, "tool_name", None),
            "error_code": getattr(error, "error_code", None),
        }

    def _generate_session_id(self) -> str:
        """Generate unique session ID.

        Returns:
            UUID-based session identifier
        """
        return str(uuid.uuid4())

    def _resolve_session_id(self, session_id: str | None) -> str:
        """Return an existing session ID or generate a new one."""
        if session_id is not None:
            return session_id
        return self._generate_session_id()

    async def _maybe_store_conversation_history(
        self,
        agent: Agent,
        session_id: str,
        conversation_history: list[dict[str, Any]] | None,
    ) -> None:
        """Store conversation history in agent state when provided."""
        if not conversation_history:
            return

        state = await agent.state_manager.load_state(session_id) or {}
        state["conversation_history"] = conversation_history
        await agent.state_manager.save_state(session_id, state)

    def _wrap_exception(
        self,
        error: Exception,
        *,
        context: str,
        session_id: str,
        agent_id: str | None,
    ) -> TaskforceError:
        """Wrap unknown exceptions into AgentExecutionError."""
        if isinstance(error, TaskforceError):
            return error
        if isinstance(error, asyncio.CancelledError):
            return CancelledError(
                f"{context}: {str(error)}",
                details={"session_id": session_id},
            )
        error_context = self._extract_error_context(
            error=error, session_id=session_id, agent_id=agent_id
        )
        details = {
            "session_id": error_context["session_id"],
            "agent_id": error_context["agent_id"],
            "tool_name": error_context["tool_name"],
            "error_code": error_context["error_code"],
            "error_type": type(error).__name__,
        }
        # Always return AgentExecutionError for the Agent flow
        return AgentExecutionError(
            f"{context}: {str(error)}",
            session_id=error_context["session_id"],
            agent_id=error_context["agent_id"] or agent_id,
            tool_name=error_context["tool_name"],
            error_code=error_context["error_code"],
            status_code=500,
            details=details,
        )
