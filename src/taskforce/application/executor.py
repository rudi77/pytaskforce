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
from taskforce.core.domain.agent import Agent
from taskforce.core.domain.agent_models import (
    CustomAgentDefinition,
    PluginAgentDefinition,
)
from taskforce.core.domain.enums import EventType, ExecutionStatus
from taskforce.core.domain.errors import (
    CancelledError,
    NotFoundError,
    TaskforceError,
    ValidationError,
)
from taskforce.core.domain.exceptions import AgentExecutionError
from taskforce.core.domain.models import ExecutionResult, StreamEvent, TokenUsage

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

    def __init__(
        self,
        factory: AgentFactory | None = None,
        gateway: Any | None = None,
        experience_tracker: Any | None = None,
        consolidation_service: Any | None = None,
    ):
        """Initialize AgentExecutor with optional factory and gateway.

        Args:
            factory: Optional AgentFactory instance. If not provided,
                    creates a default factory.
            gateway: Optional CommunicationGateway instance. When provided,
                    channel-targeted ``ask_user`` calls are automatically
                    routed via the gateway (send → poll → resume).
            experience_tracker: Optional ExperienceTracker for capturing
                    execution experiences into long-term memory.
            consolidation_service: Optional ConsolidationService for
                    auto-consolidation after execution.
        """
        self.factory = factory or AgentFactory()
        self._gateway = gateway
        self._experience_tracker = experience_tracker
        self._consolidation_service = consolidation_service
        self._consolidation_initialized = experience_tracker is not None
        self.logger = logger.bind(component="agent_executor")
        # Throttle: track when LLM consolidation last ran.
        self._last_llm_consolidation: datetime | None = None
        self._requests_since_consolidation: int = 0
        self._consolidation_interval_minutes: int = 5
        self._consolidation_interval_requests: int = 10

    def _ensure_consolidation_components(
        self,
        profile: str,
        config: dict[str, Any] | None = None,
    ) -> None:
        """Lazy-initialize consolidation components from profile config.

        Only runs once.  If ``experience_tracker`` was already injected
        via ``__init__``, this is a no-op.

        Args:
            profile: Profile name to load consolidation config from.
            config: Optional pre-loaded config dict. When provided (e.g.
                for plugin agents whose profile name is not loadable),
                the profile loader is skipped entirely.
        """
        if self._consolidation_initialized:
            return
        self._consolidation_initialized = True

        try:
            from taskforce.application.consolidation_service import (
                build_consolidation_components,
            )

            if config is None:
                config = self.factory.profile_loader.load(profile)

            consol_config = config.get("consolidation", {})
            if not consol_config.get("enabled", False) and not consol_config.get(
                "auto_capture", True
            ):
                return

            from taskforce.application.infrastructure_builder import (
                InfrastructureBuilder,
            )

            llm_provider = InfrastructureBuilder().build_llm_provider(config)
            tracker, service = build_consolidation_components(config, llm_provider)
            if tracker is not None:
                self._experience_tracker = tracker
            if service is not None:
                self._consolidation_service = service
        except Exception:
            self.logger.debug(
                "consolidation.init_skipped",
                reason="failed to build components",
                profile=profile,
            )

    async def execute_mission(
        self,
        mission: str,
        profile: str = "butler",
        session_id: str | None = None,
        conversation_history: list[dict[str, Any]] | None = None,
        progress_callback: Callable[[ProgressUpdate], None] | None = None,
        user_context: dict[str, Any] | None = None,
        agent_id: str | None = None,
        planning_strategy: str | None = None,
        planning_strategy_params: dict[str, Any] | None = None,
        plugin_path: str | None = None,
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
            profile: Configuration profile (butler/coding_agent/rag_agent)
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

        Returns:
            ExecutionResult with completion status and history

        Raises:
            AgentExecutionError: If agent creation or execution fails
        """
        # Delegate to streaming implementation and collect result
        result: ExecutionResult | None = None
        accumulated_usage = TokenUsage()
        latest_final_answer: str | None = None
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
        ):
            # Forward progress updates to callback if provided
            if progress_callback:
                progress_callback(update)

            # Accumulate token usage from TOKEN_USAGE events
            evt = update.event_type
            is_token_usage = (
                evt == EventType.TOKEN_USAGE or evt == EventType.TOKEN_USAGE.value
            )
            if is_token_usage:
                usage = update.details
                accumulated_usage.prompt_tokens += usage.get("prompt_tokens", 0)
                accumulated_usage.completion_tokens += usage.get("completion_tokens", 0)
                accumulated_usage.total_tokens += usage.get("total_tokens", 0)

            # Keep track of FINAL_ANSWER to avoid leaking generic COMPLETE text
            is_final_answer = (
                evt == EventType.FINAL_ANSWER or evt == EventType.FINAL_ANSWER.value
            )
            if is_final_answer:
                answer = str(update.details.get("content") or update.message or "").strip()
                if answer:
                    latest_final_answer = answer

            # Extract result from complete event
            extracted = self._extract_result_from_update(update)
            if extracted is not None:
                if latest_final_answer:
                    extracted.final_message = latest_final_answer
                result = extracted

        if result is None:
            raise AgentExecutionError(
                "No completion event received from streaming execution",
                session_id=session_id,
            )

        # Attach accumulated token usage to result
        if accumulated_usage.total_tokens > 0:
            result.token_usage = accumulated_usage

        return result

    def _extract_result_from_update(self, update: ProgressUpdate) -> ExecutionResult | None:
        """Extract an ExecutionResult from a COMPLETE progress update.

        Args:
            update: A ProgressUpdate to inspect.

        Returns:
            ExecutionResult if the update is a COMPLETE event, None otherwise.
        """
        event_type = update.event_type
        is_complete = event_type == EventType.COMPLETE or event_type == EventType.COMPLETE.value
        if not is_complete:
            return None

        final_message = str(update.details.get("final_message") or update.message or "")
        return ExecutionResult(
            status=update.details.get("status", ExecutionStatus.COMPLETED.value),
            final_message=final_message,
            session_id=update.details.get("session_id", ""),
            todolist_id=update.details.get("todolist_id"),
            execution_history=[],
        )

    async def execute_mission_streaming(
        self,
        mission: str,
        profile: str = "butler",
        session_id: str | None = None,
        conversation_history: list[dict[str, Any]] | None = None,
        user_context: dict[str, Any] | None = None,
        agent_id: str | None = None,
        planning_strategy: str | None = None,
        planning_strategy_params: dict[str, Any] | None = None,
        agent: Agent | None = None,
        plugin_path: str | None = None,
    ) -> AsyncIterator[ProgressUpdate]:
        """Execute Agent mission with streaming progress updates.

        Yields ProgressUpdate objects as execution progresses, enabling
        real-time feedback to consumers (CLI progress bars, API SSE, etc).

        Args:
            mission: Mission description
            profile: Configuration profile (butler/coding_agent/rag_agent)
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

        Yields:
            ProgressUpdate objects for each execution event

        Raises:
            AgentExecutionError: If agent creation or execution fails
            CancelledError: If the execution is cancelled
        """
        resolved_session_id = self._resolve_session_id(session_id)
        owns_agent = agent is None

        # Lazy-initialize consolidation components from profile config.
        # When a pre-created agent is passed (e.g. plugin agents), extract
        # its merged config so that the profile loader is not required.
        agent_config = getattr(agent, "_merged_config", None) if agent else None
        self._ensure_consolidation_components(profile, config=agent_config)

        # Start experience tracking (if enabled)
        if self._experience_tracker is not None:
            self._experience_tracker.start_session(resolved_session_id, mission, profile)

        yield self._build_started_update(
            mission, resolved_session_id, profile, agent_id, plugin_path
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

        execution_failed = False
        try:
            async for update in self._execute_streaming(
                agent, mission, resolved_session_id, user_context=user_context,
            ):
                yield update

            self.logger.info(
                "mission.streaming.completed",
                session_id=resolved_session_id,
                agent_id=agent_id,
                plugin_path=plugin_path,
            )

        except asyncio.CancelledError as e:
            execution_failed = True
            yield self._handle_cancellation(e, resolved_session_id, agent_id, plugin_path)

        except Exception as e:
            execution_failed = True
            error_update, wrapped_error = self._handle_streaming_failure(
                e, resolved_session_id, agent_id, plugin_path
            )
            yield error_update
            raise wrapped_error from e

        finally:
            # Finalize experience tracking with correct status.
            # Consolidation runs in background to avoid blocking the next request.
            if self._experience_tracker is not None:
                status = ExecutionStatus.FAILED.value if execution_failed else ExecutionStatus.COMPLETED.value
                experience = await self._experience_tracker.end_session(status)
                if experience and self._consolidation_service is not None:
                    self._requests_since_consolidation += 1
                    if self._should_run_llm_consolidation():
                        self._last_llm_consolidation = datetime.now()
                        self._requests_since_consolidation = 0
                        asyncio.create_task(
                            self._consolidation_service.post_execution_hook(
                                resolved_session_id, experience
                            ),
                            name="consolidation-llm",
                        )

            # Run lightweight (no-LLM) memory consolidation in background.
            if agent and not execution_failed:
                asyncio.create_task(
                    self._run_lightweight_consolidation(agent, mission),
                    name="consolidation-lightweight",
                )

            if agent and owns_agent:
                # Defer close so background consolidation tasks can still
                # access the agent's memory store.
                asyncio.create_task(
                    self._deferred_close(agent, delay=10.0),
                    name="agent-close",
                )

    async def _run_lightweight_consolidation(
        self,
        agent: Agent,
        mission: str,
    ) -> None:
        """Run lightweight memory consolidation after a successful session.

        Extracts keywords from the mission to reinforce related memories.
        Runs decay sweep, reinforcement, and association building without
        any LLM calls.  Failures are logged but never propagated.
        """
        memory_store = getattr(agent, "_memory_store", None)
        if not memory_store:
            return

        try:
            from taskforce.infrastructure.memory.lightweight_consolidation import (
                run_lightweight_consolidation,
            )

            # Extract keywords from mission for selective reinforcement.
            keywords = {w.lower() for w in mission.split() if len(w) > 2}

            # Use the agent's embedding provider if available.
            embedder = getattr(memory_store, "_embedder", None)

            result = await run_lightweight_consolidation(
                store=memory_store,
                session_keywords=keywords if keywords else None,
                embedding_provider=embedder,
            )
            self.logger.debug(
                "lightweight_consolidation.done",
                archived=result.archived,
                strengthened=result.strengthened,
                associations=result.associations_created,
                duration_ms=result.duration_ms,
            )
        except Exception:
            self.logger.debug(
                "lightweight_consolidation.skipped",
                reason="error during consolidation",
            )

    def _should_run_llm_consolidation(self) -> bool:
        """Check whether enough time or requests have passed for LLM consolidation."""
        if self._last_llm_consolidation is None:
            return True
        elapsed = (datetime.now() - self._last_llm_consolidation).total_seconds()
        if elapsed >= self._consolidation_interval_minutes * 60:
            return True
        if self._requests_since_consolidation >= self._consolidation_interval_requests:
            return True
        return False

    @staticmethod
    async def _deferred_close(agent: Agent, delay: float = 5.0) -> None:
        """Close agent after a delay so background consolidation can finish."""
        await asyncio.sleep(delay)
        try:
            await agent.close()
        except Exception:
            pass

    def _build_started_update(
        self,
        mission: str,
        session_id: str,
        profile: str,
        agent_id: str | None,
        plugin_path: str | None,
    ) -> ProgressUpdate:
        """Build the initial STARTED progress update."""
        return ProgressUpdate(
            timestamp=datetime.now(),
            event_type=EventType.STARTED,
            message=f"Starting mission: {mission[:80]}",
            details={
                "session_id": session_id,
                "profile": profile,
                "agent_id": agent_id,
                "plugin_path": plugin_path,
            },
        )

    def _handle_cancellation(
        self,
        error: asyncio.CancelledError,
        session_id: str,
        agent_id: str | None,
        plugin_path: str | None,
    ) -> ProgressUpdate:
        """Log cancellation and build error update. Re-raises as CancelledError.

        Args:
            error: The CancelledError that was caught.
            session_id: Session identifier.
            agent_id: Optional agent identifier.
            plugin_path: Optional plugin path.

        Returns:
            ProgressUpdate with ERROR event type.

        Raises:
            CancelledError: Always re-raised with context.
        """
        self.logger.warning(
            "mission.streaming.cancelled",
            session_id=session_id,
            error=str(error),
            agent_id=agent_id,
            plugin_path=plugin_path,
        )

        update = ProgressUpdate(
            timestamp=datetime.now(),
            event_type=EventType.ERROR,
            message=f"Execution cancelled: {error!s}",
            details={"error": str(error), "error_type": type(error).__name__},
        )

        raise CancelledError(
            f"Mission streaming cancelled: {error!s}",
            details={"session_id": session_id},
        ) from error

        return update  # noqa: B012 - unreachable but satisfies type checker

    def _handle_streaming_failure(
        self,
        error: Exception,
        session_id: str,
        agent_id: str | None,
        plugin_path: str | None,
    ) -> tuple[ProgressUpdate, Exception]:
        """Log failure, build error update and wrapped exception.

        Args:
            error: The exception that was caught.
            session_id: Session identifier.
            agent_id: Optional agent identifier.
            plugin_path: Optional plugin path.

        Returns:
            Tuple of (ProgressUpdate with ERROR event, wrapped exception).
        """
        self._log_execution_failure(
            event_name="mission.streaming.failed",
            error=error,
            session_id=session_id,
            agent_id=agent_id,
            plugin_path=plugin_path,
        )

        update = ProgressUpdate(
            timestamp=datetime.now(),
            event_type=EventType.ERROR,
            message=f"Execution failed: {error!s}",
            details={"error": str(error), "error_type": type(error).__name__},
        )

        wrapped = self._wrap_exception(
            error,
            context="Mission streaming failed",
            session_id=session_id,
            agent_id=agent_id,
        )

        return update, wrapped

    # ------------------------------------------------------------------
    # Agent creation (broken into focused helpers)
    # ------------------------------------------------------------------

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

        Dispatches to the appropriate creation strategy based on the
        combination of plugin_path, agent_id, and profile arguments.

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
            NotFoundError: If agent_id provided but not found
            ValidationError: If agent definition is invalid
        """
        self.logger.debug(
            "creating_lean_agent",
            profile=profile,
            has_user_context=user_context is not None,
            agent_id=agent_id,
            planning_strategy=planning_strategy,
            plugin_path=plugin_path,
        )

        if plugin_path:
            return await self._create_agent_from_plugin_path(
                plugin_path,
                profile,
                user_context,
                planning_strategy,
                planning_strategy_params,
            )

        if agent_id:
            return await self._create_agent_from_agent_id(
                agent_id,
                profile,
                user_context,
                planning_strategy,
                planning_strategy_params,
            )

        return await self._create_agent_from_profile(
            profile,
            user_context,
            planning_strategy,
            planning_strategy_params,
        )

    async def _create_agent_from_plugin_path(
        self,
        plugin_path: str,
        profile: str,
        user_context: dict[str, Any] | None,
        planning_strategy: str | None,
        planning_strategy_params: dict[str, Any] | None,
    ) -> Agent:
        """Create agent from an explicit plugin directory path.

        Args:
            plugin_path: Path to the external plugin directory.
            profile: Configuration profile name.
            user_context: Optional user context for RAG filtering.
            planning_strategy: Optional planning strategy override.
            planning_strategy_params: Optional planning strategy parameters.

        Returns:
            Agent instance configured from the plugin.
        """
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

    async def _create_agent_from_agent_id(
        self,
        agent_id: str,
        profile: str,
        user_context: dict[str, Any] | None,
        planning_strategy: str | None,
        planning_strategy_params: dict[str, Any] | None,
    ) -> Agent:
        """Create agent from a registered agent ID.

        Looks up the agent definition in the registry and dispatches
        to the appropriate creation method (plugin, custom, or profile).

        Args:
            agent_id: Registered agent identifier.
            profile: Configuration profile name.
            user_context: Optional user context for RAG filtering.
            planning_strategy: Optional planning strategy override.
            planning_strategy_params: Optional planning strategy parameters.

        Returns:
            Agent instance.

        Raises:
            ValidationError: If agent_id format is invalid or is a profile agent.
            NotFoundError: If agent_id is not found in the registry.
        """
        self._validate_agent_id_format(agent_id)

        agent_response = self._lookup_agent_definition(agent_id)
        if not agent_response:
            raise NotFoundError(
                f"Agent '{agent_id}' not found",
                details={"agent_id": agent_id},
            )

        if isinstance(agent_response, PluginAgentDefinition):
            return await self._create_plugin_agent_from_definition(
                agent_response,
                agent_id,
                profile,
                user_context,
                planning_strategy,
                planning_strategy_params,
            )

        if isinstance(agent_response, CustomAgentDefinition):
            return await self._create_custom_agent_from_definition(
                agent_response,
                agent_id,
                planning_strategy,
                planning_strategy_params,
            )

        raise ValidationError(
            f"Agent '{agent_id}' is a profile agent, not a custom or plugin agent. "
            "Use 'profile' parameter for profile agents.",
            details={"agent_id": agent_id, "source": agent_response.source},
        )

    def _validate_agent_id_format(self, agent_id: str) -> None:
        """Validate that agent_id does not contain slashes.

        Args:
            agent_id: The agent identifier to validate.

        Raises:
            ValidationError: If agent_id contains slashes.
        """
        if "/" in agent_id:
            raise ValidationError(
                f"Invalid agent_id format: '{agent_id}'. "
                f"Agent IDs cannot contain slashes. "
                f"Use 'profile' parameter instead "
                f"(e.g., profile='{agent_id.split('/')[0]}').",
                details={"agent_id": agent_id},
            )

    def _lookup_agent_definition(self, agent_id: str) -> Any:
        """Look up an agent definition from the agent registry.

        Uses ``InfrastructureBuilder`` to obtain a properly wired registry
        instance, avoiding a direct infrastructure import in the application
        layer.

        Args:
            agent_id: The agent identifier to look up.

        Returns:
            Agent definition (PluginAgentDefinition, CustomAgentDefinition, etc.)
            or None if not found.
        """
        from taskforce.application.infrastructure_builder import InfrastructureBuilder

        registry = InfrastructureBuilder().build_agent_registry()
        return registry.get_agent(agent_id)

    async def _create_plugin_agent_from_definition(
        self,
        definition: PluginAgentDefinition,
        agent_id: str,
        profile: str,
        user_context: dict[str, Any] | None,
        planning_strategy: str | None,
        planning_strategy_params: dict[str, Any] | None,
    ) -> Agent:
        """Create agent from a PluginAgentDefinition.

        Args:
            definition: The plugin agent definition.
            agent_id: The agent identifier (for logging).
            profile: Configuration profile name.
            user_context: Optional user context for RAG filtering.
            planning_strategy: Optional planning strategy override.
            planning_strategy_params: Optional planning strategy parameters.

        Returns:
            Agent instance configured from the plugin definition.
        """
        from taskforce.application.factory import get_base_path

        base_path = get_base_path()
        plugin_path_abs = (base_path / definition.plugin_path).resolve()

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

    async def _create_custom_agent_from_definition(
        self,
        definition: CustomAgentDefinition,
        agent_id: str,
        planning_strategy: str | None,
        planning_strategy_params: dict[str, Any] | None,
    ) -> Agent:
        """Create agent from a CustomAgentDefinition.

        Args:
            definition: The custom agent definition.
            agent_id: The agent identifier (for logging).
            planning_strategy: Optional planning strategy override.
            planning_strategy_params: Optional planning strategy parameters.

        Returns:
            Agent instance configured from the custom definition.
        """
        self.logger.info(
            "loading_custom_agent",
            agent_id=agent_id,
            agent_name=definition.name,
            tool_count=len(definition.tool_allowlist),
        )

        return await self.factory.create_agent(
            system_prompt=definition.system_prompt,
            tools=definition.tool_allowlist,
            mcp_servers=definition.mcp_servers,
            planning_strategy=planning_strategy,
            planning_strategy_params=planning_strategy_params,
        )

    async def _create_agent_from_profile(
        self,
        profile: str,
        user_context: dict[str, Any] | None,
        planning_strategy: str | None,
        planning_strategy_params: dict[str, Any] | None,
    ) -> Agent:
        """Create agent from a profile, checking for plugin agent match first.

        If the profile name matches a registered plugin agent, the plugin
        agent is used instead of loading a YAML profile.

        Args:
            profile: Configuration profile name.
            user_context: Optional user context for RAG filtering.
            planning_strategy: Optional planning strategy override.
            planning_strategy_params: Optional planning strategy parameters.

        Returns:
            Agent instance.
        """
        agent_response = self._lookup_agent_definition(profile)

        if isinstance(agent_response, PluginAgentDefinition):
            return await self._create_plugin_agent_via_profile_name(
                agent_response,
                profile,
                user_context,
                planning_strategy,
                planning_strategy_params,
            )

        return await self.factory.create_agent(
            config=profile,
            user_context=user_context,
            planning_strategy=planning_strategy,
            planning_strategy_params=planning_strategy_params,
        )

    async def _create_plugin_agent_via_profile_name(
        self,
        definition: PluginAgentDefinition,
        profile: str,
        user_context: dict[str, Any] | None,
        planning_strategy: str | None,
        planning_strategy_params: dict[str, Any] | None,
    ) -> Agent:
        """Create a plugin agent when the profile name matched a plugin.

        Args:
            definition: The plugin agent definition.
            profile: The profile name that matched the plugin.
            user_context: Optional user context for RAG filtering.
            planning_strategy: Optional planning strategy override.
            planning_strategy_params: Optional planning strategy parameters.

        Returns:
            Agent instance configured from the plugin.
        """
        from taskforce.application.factory import get_base_path

        base_path = get_base_path()
        plugin_path_abs = (base_path / definition.plugin_path).resolve()

        self.logger.info(
            "profile_matches_plugin_agent",
            profile=profile,
            plugin_path=str(plugin_path_abs),
            hint=(
                "Using profile name as plugin agent. " "Consider using agent_id parameter instead."
            ),
        )

        return await self.factory.create_agent_with_plugin(
            plugin_path=str(plugin_path_abs),
            profile="butler",
            user_context=user_context,
            planning_strategy=planning_strategy,
            planning_strategy_params=planning_strategy_params,
        )

    # ------------------------------------------------------------------
    # Execution helpers
    # ------------------------------------------------------------------

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
        if not progress_callback:
            return await agent.execute(mission=mission, session_id=session_id)

        result = await agent.execute(mission=mission, session_id=session_id)

        progress_callback(
            ProgressUpdate(
                timestamp=datetime.now(),
                event_type=EventType.COMPLETE,
                message=result.final_message,
                details={
                    "status": (
                        result.status_value if hasattr(result, "status_value") else result.status
                    ),
                    "session_id": result.session_id,
                    "todolist_id": result.todolist_id,
                },
            )
        )

        return result

    async def _execute_streaming(
        self,
        agent: Agent,
        mission: str,
        session_id: str,
        user_context: dict[str, Any] | None = None,
    ) -> AsyncIterator[ProgressUpdate]:
        """Execute agent with streaming progress updates.

        Uses true streaming if agent supports execute_stream(), otherwise
        falls back to post-hoc streaming from execution history.

        When a gateway is configured, channel-targeted ``ask_user`` calls
        (those with ``channel`` and ``recipient_id``) are handled
        transparently: the question is sent via the gateway, the executor
        polls for the response, and the agent is automatically resumed.
        The consumer (CLI, API) only sees informational progress events.

        Non-channel-targeted ``ask_user`` calls are automatically promoted
        to channel-targeted calls when a ``source_channel`` is present in
        the *user_context* (injected by the CommunicationGateway).

        Args:
            agent: Agent instance to execute
            mission: Mission description
            session_id: Session identifier
            user_context: Optional user context (may contain source_channel).

        Yields:
            ProgressUpdate objects for execution events
        """
        current_mission = mission
        source_channel = (user_context or {}).get("source_channel")
        source_conversation_id = (user_context or {}).get("source_conversation_id")

        while True:
            channel_ask: dict[str, Any] | None = None

            if self._agent_supports_streaming(agent):
                async for event in agent.execute_stream(current_mission, session_id):
                    # Capture experience (non-invasive, sync)
                    if self._experience_tracker is not None:
                        self._experience_tracker.observe(event)

                    # Auto-promote plain ask_user to channel-targeted when
                    # the message originated from a channel (e.g. Telegram).
                    if (
                        source_channel
                        and self._is_plain_ask_user(event)
                        and self._gateway
                    ):
                        if event.data is None:
                            event.data = {}
                        event.data["channel"] = source_channel
                        event.data["recipient_id"] = source_conversation_id or ""
                        self.logger.info(
                            "ask_user.auto_promoted_to_channel",
                            channel=source_channel,
                            recipient_id=source_conversation_id,
                            question=event.data.get("question", "")[:100],
                        )

                    if self._is_channel_targeted_ask(event) and self._gateway:
                        channel_ask = event.data
                        # Yield an informational event (not a raw ASK_USER)
                        yield self._build_channel_question_sent_update(event)
                    else:
                        # Suppress COMPLETE events when a channel question is
                        # pending — the "Execution completed" status would leak
                        # into conversation history as if it were agent content.
                        if channel_ask is not None and event.event_type == EventType.COMPLETE:
                            continue
                        yield self._stream_event_to_progress_update(event)
            else:
                result = await agent.execute(mission=current_mission, session_id=session_id)
                async for update in self._yield_history_updates(result):
                    yield update

            if not channel_ask or not self._gateway:
                break  # Normal exit — no channel question to handle

            # Route the channel question via the gateway
            response = await self._route_channel_question(
                session_id=session_id,
                channel=channel_ask["channel"],
                recipient_id=channel_ask["recipient_id"],
                question=channel_ask.get("question", ""),
            )

            if response is not None:
                yield self._build_channel_response_received_update(channel_ask, response)
                current_mission = response
                # Loop continues: agent resumes with the response
            else:
                yield ProgressUpdate(
                    timestamp=datetime.now(),
                    event_type=EventType.ERROR,
                    message=(
                        f"Timeout waiting for response from "
                        f"{channel_ask['channel']}:{channel_ask['recipient_id']}"
                    ),
                    details=channel_ask,
                )
                break

    def _agent_supports_streaming(self, agent: Agent) -> bool:
        """Check if the agent has a real execute_stream method.

        Args:
            agent: Agent instance to inspect.

        Returns:
            True if agent supports streaming, False otherwise.
        """
        execute_stream_method = getattr(agent, "execute_stream", None)
        return (
            execute_stream_method is not None
            and callable(execute_stream_method)
            and not str(type(execute_stream_method).__module__).startswith("unittest.mock")
        )

    # ------------------------------------------------------------------
    # Channel-targeted ask_user routing
    # ------------------------------------------------------------------

    @staticmethod
    def _is_plain_ask_user(event: StreamEvent) -> bool:
        """Check whether a StreamEvent is a plain (non-channel) ASK_USER."""
        evt = event.event_type
        is_ask = evt == EventType.ASK_USER or evt == EventType.ASK_USER.value
        if not is_ask:
            return False
        data = event.data or {}
        return not data.get("channel")

    @staticmethod
    def _is_channel_targeted_ask(event: StreamEvent) -> bool:
        """Check whether a StreamEvent is a channel-targeted ASK_USER."""
        evt = event.event_type
        is_ask = evt == EventType.ASK_USER or evt == EventType.ASK_USER.value
        if not is_ask:
            return False
        data = event.data or {}
        return bool(data.get("channel") and data.get("recipient_id"))

    async def _route_channel_question(
        self,
        *,
        session_id: str,
        channel: str,
        recipient_id: str,
        question: str,
    ) -> str | None:
        """Send a channel question via the gateway and poll for the response.

        Args:
            session_id: Paused agent session.
            channel: Target channel (e.g. 'telegram').
            recipient_id: Recipient user ID on that channel.
            question: The question text.

        Returns:
            Response text when the recipient answers, or None on timeout.
        """
        sent = await self._gateway.send_channel_question(
            session_id=session_id,
            channel=channel,
            recipient_id=recipient_id,
            question=question,
        )
        if not sent:
            self.logger.error(
                "channel_question.send_failed",
                session_id=session_id,
                channel=channel,
                recipient_id=recipient_id,
            )
            return None

        self.logger.info(
            "channel_question.polling",
            session_id=session_id,
            channel=channel,
            recipient_id=recipient_id,
        )

        poll_interval = 2.0
        max_wait = 600.0
        elapsed = 0.0

        while elapsed < max_wait:
            await asyncio.sleep(poll_interval)
            elapsed += poll_interval

            response = await self._gateway.poll_channel_response(session_id=session_id)
            if response is not None:
                await self._gateway.clear_channel_question(session_id=session_id)
                self.logger.info(
                    "channel_question.response_received",
                    session_id=session_id,
                    channel=channel,
                    recipient_id=recipient_id,
                )
                return response

        self.logger.warning(
            "channel_question.timeout",
            session_id=session_id,
            channel=channel,
            recipient_id=recipient_id,
            max_wait=max_wait,
        )
        return None

    @staticmethod
    def _build_channel_question_sent_update(event: StreamEvent) -> ProgressUpdate:
        """Build a ProgressUpdate for a channel question that was sent."""
        data = event.data or {}
        channel = data.get("channel", "")
        recipient = data.get("recipient_id", "")
        question = data.get("question", "")
        return ProgressUpdate(
            timestamp=event.timestamp,
            event_type=EventType.ASK_USER,
            message=f"Sending question to {channel}:{recipient}: {question}",
            details={**data, "channel_routed": True},
        )

    @staticmethod
    def _build_channel_response_received_update(
        channel_ask: dict[str, Any], response: str
    ) -> ProgressUpdate:
        """Build a ProgressUpdate when a channel response is received."""
        channel = channel_ask.get("channel", "")
        recipient = channel_ask.get("recipient_id", "")
        return ProgressUpdate(
            timestamp=datetime.now(),
            event_type=EventType.ASK_USER,
            message=f"Response received from {channel}:{recipient}: {response}",
            details={
                "channel": channel,
                "recipient_id": recipient,
                "response": response,
                "channel_response_received": True,
            },
        )

    async def _yield_history_updates(
        self, result: ExecutionResult
    ) -> AsyncIterator[ProgressUpdate]:
        """Yield ProgressUpdate events from a completed execution result.

        Converts execution_history entries into streaming-compatible
        progress updates, followed by token usage and a final COMPLETE event.

        Args:
            result: The completed execution result.

        Yields:
            ProgressUpdate objects for each history event and completion.
        """
        for event in result.execution_history:
            update = self._history_entry_to_update(event)
            if update is not None:
                yield update

        # Emit token usage from the completed result
        usage = result.token_usage
        usage_dict = usage.to_dict() if hasattr(usage, "to_dict") else usage
        if usage_dict and usage_dict.get("total_tokens", 0) > 0:
            yield ProgressUpdate(
                timestamp=datetime.now(),
                event_type=EventType.TOKEN_USAGE,
                message=f"Tokens: {usage_dict.get('total_tokens', 0)}",
                details=usage_dict,
            )

        yield self._build_completion_update(result)

    def _history_entry_to_update(self, event: Any) -> ProgressUpdate | None:
        """Convert a single execution history entry to a ProgressUpdate.

        Args:
            event: A history entry (dict or StreamEvent-like object).

        Returns:
            ProgressUpdate for thought/observation events, None otherwise.
        """
        event_type_str, step, data = self._parse_history_event(event)

        if event_type_str == "thought":
            rationale = data.get("rationale", "") if isinstance(data, dict) else ""
            return ProgressUpdate(
                timestamp=datetime.now(),
                event_type="thought",
                message=f"Step {step}: {rationale[:80]}",
                details=data,
            )

        if event_type_str == "observation":
            return self._build_observation_update(step, data)

        return None

    def _parse_history_event(self, event: Any) -> tuple[str, str | int, dict[str, Any]]:
        """Parse a history event into its type, step, and data components.

        Args:
            event: A history entry (dict or object with event_type/data).

        Returns:
            Tuple of (event_type_str, step, data).
        """
        if isinstance(event, dict):
            event_type_str = event.get("type", "unknown")
            step = event.get("step", "?")
            data: dict[str, Any] = event.get("data", {})
        else:
            et = event.event_type
            event_type_str = et.value if isinstance(et, EventType) else str(et)
            step = "?"
            data = event.data
        return event_type_str, step, data

    def _build_observation_update(self, step: str | int, data: dict[str, Any]) -> ProgressUpdate:
        """Build a ProgressUpdate for an observation event.

        Args:
            step: The step number or identifier.
            data: The observation data.

        Returns:
            ProgressUpdate with observation details.
        """
        success = data.get("success", False) if isinstance(data, dict) else False
        obs_status = ExecutionStatus.COMPLETED.value if success else ExecutionStatus.FAILED.value
        return ProgressUpdate(
            timestamp=datetime.now(),
            event_type="observation",
            message=f"Step {step}: {obs_status}",
            details=data,
        )

    def _build_completion_update(self, result: ExecutionResult) -> ProgressUpdate:
        """Build the final COMPLETE progress update from an execution result.

        Args:
            result: The completed execution result.

        Returns:
            ProgressUpdate with COMPLETE event type.
        """
        status_value = result.status_value if hasattr(result, "status_value") else result.status
        return ProgressUpdate(
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
            EventType.TOOL_CALL.value: lambda d: f"Calling: {d.get('tool', 'unknown')}",
            EventType.TOOL_RESULT.value: lambda d: (
                f"{'OK' if d.get('success') else 'FAIL'} "
                f"{d.get('tool', 'unknown')}: {str(d.get('output', ''))[:50]}"
            ),
            EventType.ASK_USER.value: lambda d: (
                f"Question: {d.get('question', 'User input required')}"
            ),
            EventType.PLAN_UPDATED.value: lambda d: (
                f"Plan updated ({d.get('action', 'unknown')})"
            ),
            EventType.TOKEN_USAGE.value: lambda d: (f"Tokens: {d.get('total_tokens', 0)}"),
            EventType.FINAL_ANSWER.value: lambda d: d.get("content", ""),
            EventType.COMPLETE.value: lambda d: (
                f"Execution completed. Status: {d.get('status', 'unknown')}"
            ),
            EventType.ERROR.value: lambda d: f"Error: {d.get('message', 'unknown')}",
        }

        event_type_value = (
            event.event_type.value if isinstance(event.event_type, EventType) else event.event_type
        )
        message_fn = message_map.get(event_type_value, lambda d: str(d))

        return ProgressUpdate(
            timestamp=event.timestamp,
            event_type=event.event_type,
            message=message_fn(event.data),
            details=event.data,
        )

    # ------------------------------------------------------------------
    # Error and logging helpers
    # ------------------------------------------------------------------

    def _log_execution_failure(
        self,
        event_name: str,
        error: Exception,
        session_id: str,
        agent_id: str | None,
        duration_seconds: float | None = None,
        plugin_path: str | None = None,
    ) -> None:
        """Log a structured execution failure event.

        Args:
            event_name: The structlog event name.
            error: The exception that caused the failure.
            session_id: Session identifier.
            agent_id: Optional agent identifier.
            duration_seconds: Optional execution duration.
            plugin_path: Optional plugin path.
        """
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
        """Extract structured context from an exception for logging.

        Args:
            error: The exception to extract context from.
            session_id: Fallback session identifier.
            agent_id: Fallback agent identifier.

        Returns:
            Dict with session_id, agent_id, tool_name, and error_code.
        """
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
        """Return an existing session ID or generate a new one.

        Args:
            session_id: Optional existing session ID.

        Returns:
            The provided session ID or a newly generated one.
        """
        if session_id is not None:
            return session_id
        return self._generate_session_id()

    async def _maybe_store_conversation_history(
        self,
        agent: Agent,
        session_id: str,
        conversation_history: list[dict[str, Any]] | None,
    ) -> None:
        """Store conversation history in agent state when provided.

        Args:
            agent: Agent whose state manager to use.
            session_id: Session identifier.
            conversation_history: Optional conversation history to persist.
        """
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
        """Wrap unknown exceptions into AgentExecutionError.

        Args:
            error: The original exception.
            context: Description of what was happening when the error occurred.
            session_id: Session identifier.
            agent_id: Optional agent identifier.

        Returns:
            TaskforceError (passthrough) or AgentExecutionError wrapper.
        """
        if isinstance(error, TaskforceError):
            return error
        if isinstance(error, asyncio.CancelledError):
            return CancelledError(
                f"{context}: {error!s}",
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
        return AgentExecutionError(
            f"{context}: {error!s}",
            session_id=error_context["session_id"],
            agent_id=error_context["agent_id"] or agent_id,
            tool_name=error_context["tool_name"],
            error_code=error_context["error_code"],
            status_code=500,
            details=details,
        )
