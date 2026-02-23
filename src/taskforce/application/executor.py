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
            AgentExecutionError: If agent creation or execution fails
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
            result = self._extract_result_from_update(update) or result

        if result is None:
            raise AgentExecutionError(
                "No completion event received from streaming execution",
                session_id=session_id,
            )

        return result

    def _extract_result_from_update(
        self, update: ProgressUpdate
    ) -> ExecutionResult | None:
        """Extract an ExecutionResult from a COMPLETE progress update.

        Args:
            update: A ProgressUpdate to inspect.

        Returns:
            ExecutionResult if the update is a COMPLETE event, None otherwise.
        """
        event_type = update.event_type
        is_complete = (
            event_type == EventType.COMPLETE
            or event_type == EventType.COMPLETE.value
        )
        if not is_complete:
            return None

        return ExecutionResult(
            status=update.details.get("status", ExecutionStatus.COMPLETED.value),
            final_message=update.message,
            session_id=update.details.get("session_id", ""),
            todolist_id=update.details.get("todolist_id"),
            execution_history=[],
        )

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
            AgentExecutionError: If agent creation or execution fails
            CancelledError: If the execution is cancelled
        """
        resolved_session_id = self._resolve_session_id(session_id)
        owns_agent = agent is None

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

        # --- Auto-epic classification ---
        if agent is None and auto_epic is not False:
            escalated = await self._try_epic_escalation(
                mission, profile, auto_epic
            )
            if escalated is not None:
                yield escalated
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
            yield self._handle_cancellation(
                e, resolved_session_id, agent_id, plugin_path
            )

        except Exception as e:
            error_update, wrapped_error = self._handle_streaming_failure(
                e, resolved_session_id, agent_id, plugin_path
            )
            yield error_update
            raise wrapped_error from e

        finally:
            if agent and owns_agent:
                await agent.close()

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

    async def _try_epic_escalation(
        self,
        mission: str,
        profile: str,
        auto_epic: bool | None,
    ) -> ProgressUpdate | None:
        """Attempt auto-epic classification and return escalation update if warranted.

        Args:
            mission: The mission text.
            profile: Active profile name.
            auto_epic: Explicit override (True=force, False=skip, None=from config).

        Returns:
            ProgressUpdate with EPIC_ESCALATION event, or None for standard execution.
        """
        return await self._classify_and_route_epic(
            mission=mission,
            profile=profile,
            auto_epic=auto_epic,
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
                plugin_path, profile, user_context,
                planning_strategy, planning_strategy_params,
            )

        if agent_id:
            return await self._create_agent_from_agent_id(
                agent_id, profile, user_context,
                planning_strategy, planning_strategy_params,
            )

        return await self._create_agent_from_profile(
            profile, user_context,
            planning_strategy, planning_strategy_params,
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
                agent_response, agent_id, profile, user_context,
                planning_strategy, planning_strategy_params,
            )

        if isinstance(agent_response, CustomAgentDefinition):
            return await self._create_custom_agent_from_definition(
                agent_response, agent_id,
                planning_strategy, planning_strategy_params,
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
                agent_response, profile, user_context,
                planning_strategy, planning_strategy_params,
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
                "Using profile name as plugin agent. "
                "Consider using agent_id parameter instead."
            ),
        )

        return await self.factory.create_agent_with_plugin(
            plugin_path=str(plugin_path_abs),
            profile="dev",
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
                        result.status_value
                        if hasattr(result, "status_value")
                        else result.status
                    ),
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
        if self._agent_supports_streaming(agent):
            async for event in agent.execute_stream(mission, session_id):
                yield self._stream_event_to_progress_update(event)
        else:
            result = await agent.execute(mission=mission, session_id=session_id)
            async for update in self._yield_history_updates(result):
                yield update

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
            and not str(type(execute_stream_method).__module__).startswith(
                "unittest.mock"
            )
        )

    async def _yield_history_updates(
        self, result: ExecutionResult
    ) -> AsyncIterator[ProgressUpdate]:
        """Yield ProgressUpdate events from a completed execution result.

        Converts execution_history entries into streaming-compatible
        progress updates, followed by a final COMPLETE event.

        Args:
            result: The completed execution result.

        Yields:
            ProgressUpdate objects for each history event and completion.
        """
        for event in result.execution_history:
            update = self._history_entry_to_update(event)
            if update is not None:
                yield update

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

    def _parse_history_event(
        self, event: Any
    ) -> tuple[str, str | int, dict[str, Any]]:
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

    def _build_observation_update(
        self, step: str | int, data: dict[str, Any]
    ) -> ProgressUpdate:
        """Build a ProgressUpdate for an observation event.

        Args:
            step: The step number or identifier.
            data: The observation data.

        Returns:
            ProgressUpdate with observation details.
        """
        success = data.get("success", False) if isinstance(data, dict) else False
        obs_status = (
            ExecutionStatus.COMPLETED.value
            if success
            else ExecutionStatus.FAILED.value
        )
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
        status_value = (
            result.status_value
            if hasattr(result, "status_value")
            else result.status
        )
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
            EventType.TOKEN_USAGE.value: lambda d: (
                f"Tokens: {d.get('total_tokens', 0)}"
            ),
            EventType.FINAL_ANSWER.value: lambda d: d.get("content", ""),
            EventType.COMPLETE.value: lambda d: (
                f"Execution completed. Status: {d.get('status', 'unknown')}"
            ),
            EventType.ERROR.value: lambda d: f"Error: {d.get('message', 'unknown')}",
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
        except (FileNotFoundError, AttributeError):
            self.logger.debug(
                "auto_epic.profile_not_found",
                profile=profile,
            )
            return None
        except Exception as e:
            self.logger.error(
                "auto_epic.profile_load_failed",
                profile=profile,
                error=str(e),
                error_type=type(e).__name__,
            )
            return None

        return self._parse_auto_epic_from_config(config, profile)

    def _parse_auto_epic_from_config(
        self, config: dict[str, Any], profile: str
    ) -> AutoEpicConfig | None:
        """Parse AutoEpicConfig from a loaded profile configuration dict.

        Args:
            config: The loaded profile configuration.
            profile: Profile name (for logging context).

        Returns:
            AutoEpicConfig if valid auto_epic settings exist, None otherwise.
        """
        orchestration = config.get("orchestration", {}) or {}
        auto_epic_raw = orchestration.get("auto_epic")
        if not auto_epic_raw or not isinstance(auto_epic_raw, dict):
            return None

        try:
            return AutoEpicConfig(**auto_epic_raw)
        except Exception as e:
            self.logger.error(
                "auto_epic.config_parse_error",
                profile=profile,
                error=str(e),
                error_type=type(e).__name__,
                raw_config=auto_epic_raw,
            )
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
        epic_config = self._resolve_effective_epic_config(profile, auto_epic)
        if epic_config is None:
            return None

        llm_provider = self._create_classification_llm_provider(profile)
        if llm_provider is None:
            return None

        classification = await self._run_classification(
            mission, llm_provider, epic_config
        )
        if classification is None:
            return None

        return self._build_escalation_update(classification, epic_config)

    def _resolve_effective_epic_config(
        self, profile: str, auto_epic: bool | None
    ) -> AutoEpicConfig | None:
        """Determine the effective auto-epic config based on override and profile.

        Args:
            profile: Active profile name.
            auto_epic: Explicit override (True=force, None=from config).

        Returns:
            AutoEpicConfig if epic classification should proceed, None otherwise.
        """
        epic_config = self._resolve_auto_epic_config(profile)

        if auto_epic is True:
            if epic_config is None:
                epic_config = AutoEpicConfig(enabled=True)
        elif epic_config is None or not epic_config.enabled:
            return None

        return epic_config

    def _create_classification_llm_provider(self, profile: str) -> Any | None:
        """Create a lightweight LLM provider for complexity classification.

        Args:
            profile: Profile name to load LLM configuration from.

        Returns:
            LLM provider instance, or None if creation fails.
        """
        try:
            profile_config = self.factory.profile_loader.load_safe(profile)
            return self.factory._create_llm_provider(profile_config)
        except Exception as e:
            self.logger.error(
                "auto_epic.llm_creation_failed",
                profile=profile,
                error=str(e),
                error_type=type(e).__name__,
            )
            return None

    async def _run_classification(
        self, mission: str, llm_provider: Any, epic_config: AutoEpicConfig
    ) -> Any | None:
        """Run the complexity classifier and return the classification result.

        Args:
            mission: The mission text.
            llm_provider: LLM provider for the classifier.
            epic_config: The auto-epic configuration.

        Returns:
            Classification result if classified as EPIC with sufficient
            confidence, None otherwise.
        """
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

        return classification

    def _build_escalation_update(
        self, classification: Any, epic_config: AutoEpicConfig
    ) -> ProgressUpdate:
        """Build the EPIC_ESCALATION progress update from classification results.

        Args:
            classification: The classification result.
            epic_config: The auto-epic configuration.

        Returns:
            ProgressUpdate with EPIC_ESCALATION event type.
        """
        worker_count = (
            classification.suggested_worker_count or epic_config.default_worker_count
        )
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
