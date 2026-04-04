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
from taskforce.core.domain.enums import EventType, ExecutionStatus
from taskforce.core.domain.exceptions import AgentExecutionError
from taskforce.core.domain.models import ExecutionResult, TokenUsage

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
    ):
        """Initialize AgentExecutor with optional factory and gateway.

        Args:
            factory: Optional AgentFactory instance. If not provided,
                    creates a default factory.
            gateway: Optional CommunicationGateway instance. When provided,
                    channel-targeted ``ask_user`` calls are automatically
                    routed via the gateway (send → poll → resume).
        """
        from taskforce.application.agent_creation_pipeline import (
            AgentCreationPipeline,
        )
        from taskforce.application.execution_error_handler import (
            ExecutionErrorHandler,
        )

        self.factory = factory or AgentFactory()
        self._gateway = gateway
        self.logger = logger.bind(component="agent_executor")

        # Composed components (extracted concerns)
        self._error_handler = ExecutionErrorHandler()
        self._agent_pipeline = AgentCreationPipeline(self.factory)


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
            is_token_usage = evt == EventType.TOKEN_USAGE or evt == EventType.TOKEN_USAGE.value
            if is_token_usage:
                usage = update.details
                accumulated_usage.prompt_tokens += usage.get("prompt_tokens", 0)
                accumulated_usage.completion_tokens += usage.get("completion_tokens", 0)
                accumulated_usage.total_tokens += usage.get("total_tokens", 0)

            # Keep track of FINAL_ANSWER to avoid leaking generic COMPLETE text
            is_final_answer = evt == EventType.FINAL_ANSWER or evt == EventType.FINAL_ANSWER.value
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
        """Extract an ExecutionResult from a COMPLETE progress update."""
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
            agent_id: Optional custom agent ID
            planning_strategy: Optional planning strategy override
            planning_strategy_params: Optional params for planning strategy
            agent: Optional pre-created Agent instance
            plugin_path: Optional path to external plugin directory

        Yields:
            ProgressUpdate objects for each execution event

        Raises:
            AgentExecutionError: If agent creation or execution fails
            CancelledError: If the execution is cancelled
        """
        from taskforce.application.progress_update_builder import (
            build_started_update,
        )

        resolved_session_id = self._resolve_session_id(session_id)
        owns_agent = agent is None

        yield build_started_update(mission, resolved_session_id, profile, agent_id, plugin_path)

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
            agent = await self._agent_pipeline.create_agent(
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
                agent,
                mission,
                resolved_session_id,
                user_context=user_context,
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
            yield self._error_handler.handle_cancellation(
                e, resolved_session_id, agent_id, plugin_path
            )

        except Exception as e:
            execution_failed = True
            error_update, wrapped_error = self._error_handler.handle_streaming_failure(
                e, resolved_session_id, agent_id, plugin_path
            )
            yield error_update
            raise wrapped_error from e

        finally:
            if agent and owns_agent:
                asyncio.create_task(
                    self._deferred_close(agent, delay=2.0),
                    name="agent-close",
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
        """Execute agent with progress tracking via callback."""
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
        are handled transparently via the ChannelAskRouter.
        """
        from taskforce.application.channel_ask_router import ChannelAskRouter
        from taskforce.application.progress_update_builder import (
            stream_event_to_progress_update,
            yield_history_updates,
        )

        current_mission = mission
        source_channel = (user_context or {}).get("source_channel")
        source_conversation_id = (user_context or {}).get("source_conversation_id")

        # Build router if gateway is available
        ask_router = ChannelAskRouter(self._gateway) if self._gateway else None

        while True:
            channel_ask: dict[str, Any] | None = None

            if self._agent_supports_streaming(agent):
                async for event in agent.execute_stream(current_mission, session_id):
                    # Auto-promote plain ask_user to channel-targeted
                    if source_channel and ask_router and ChannelAskRouter.is_plain_ask_user(event):
                        ask_router.auto_promote_ask(event, source_channel, source_conversation_id)

                    if ask_router and ChannelAskRouter.is_channel_targeted_ask(event):
                        channel_ask = event.data
                        yield ask_router.build_question_sent_update(event)
                    else:
                        # Suppress COMPLETE events when a channel question is pending
                        if channel_ask is not None and event.event_type == EventType.COMPLETE:
                            continue
                        yield stream_event_to_progress_update(event)
            else:
                result = await agent.execute(mission=current_mission, session_id=session_id)
                async for update in yield_history_updates(result):
                    yield update

            if not channel_ask or not ask_router:
                break  # Normal exit — no channel question to handle

            # Route the channel question via the gateway
            response = await ask_router.route_channel_question(
                session_id=session_id,
                channel=channel_ask["channel"],
                recipient_id=channel_ask["recipient_id"],
                question=channel_ask.get("question", ""),
            )

            if response is not None:
                yield ask_router.build_response_received_update(channel_ask, response)
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
        """Check if the agent has a real execute_stream method."""
        execute_stream_method = getattr(agent, "execute_stream", None)
        return (
            execute_stream_method is not None
            and callable(execute_stream_method)
            and not str(type(execute_stream_method).__module__).startswith("unittest.mock")
        )

    # ------------------------------------------------------------------
    # Session helpers
    # ------------------------------------------------------------------

    def _generate_session_id(self) -> str:
        """Generate unique session ID."""
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

    @staticmethod
    async def _deferred_close(agent: Agent, delay: float = 2.0) -> None:
        """Close agent after a delay so background consolidation can finish."""
        await asyncio.sleep(delay)
        try:
            await agent.close()
        except Exception:
            pass

    # ------------------------------------------------------------------
    # Backward-compatible delegate methods
    # ------------------------------------------------------------------

    # Agent creation delegates (backward-compatible)

    async def _create_agent(
        self,
        profile: str,
        user_context: dict[str, Any] | None = None,
        agent_id: str | None = None,
        planning_strategy: str | None = None,
        planning_strategy_params: dict[str, Any] | None = None,
        plugin_path: str | None = None,
    ) -> Agent:
        """Create Agent using factory. Delegates to AgentCreationPipeline."""
        return await self._agent_pipeline.create_agent(
            profile,
            user_context=user_context,
            agent_id=agent_id,
            planning_strategy=planning_strategy,
            planning_strategy_params=planning_strategy_params,
            plugin_path=plugin_path,
        )

    # Error handling delegates (backward-compatible)

    def _handle_cancellation(self, error, session_id, agent_id, plugin_path):
        """Delegate to ExecutionErrorHandler."""
        return self._error_handler.handle_cancellation(error, session_id, agent_id, plugin_path)

    def _handle_streaming_failure(self, error, session_id, agent_id, plugin_path):
        """Delegate to ExecutionErrorHandler."""
        return self._error_handler.handle_streaming_failure(
            error, session_id, agent_id, plugin_path
        )

    def _log_execution_failure(self, event_name, error, session_id, agent_id, **kwargs):
        """Delegate to ExecutionErrorHandler."""
        return self._error_handler.log_execution_failure(
            event_name, error, session_id, agent_id, **kwargs
        )

    def _wrap_exception(self, error, *, context, session_id, agent_id):
        """Delegate to ExecutionErrorHandler."""
        return self._error_handler.wrap_exception(
            error, context=context, session_id=session_id, agent_id=agent_id
        )

    def _extract_error_context(self, error, session_id, agent_id):
        """Delegate to execution_error_handler module function."""
        from taskforce.application.execution_error_handler import (
            _extract_error_context,
        )

        return _extract_error_context(error, session_id, agent_id)

    # Progress update delegates (backward-compatible)

    def _build_started_update(self, mission, session_id, profile, agent_id, plugin_path):
        """Delegate to progress_update_builder module."""
        from taskforce.application.progress_update_builder import (
            build_started_update,
        )

        return build_started_update(mission, session_id, profile, agent_id, plugin_path)

    def _stream_event_to_progress_update(self, event):
        """Delegate to progress_update_builder module."""
        from taskforce.application.progress_update_builder import (
            stream_event_to_progress_update,
        )

        return stream_event_to_progress_update(event)

    async def _yield_history_updates(self, result):
        """Delegate to progress_update_builder module."""
        from taskforce.application.progress_update_builder import (
            yield_history_updates,
        )

        async for update in yield_history_updates(result):
            yield update

    def _build_completion_update(self, result):
        """Delegate to progress_update_builder module."""
        from taskforce.application.progress_update_builder import (
            build_completion_update,
        )

        return build_completion_update(result)

    # Channel ask delegates (backward-compatible)

    @staticmethod
    def _is_plain_ask_user(event):
        """Delegate to ChannelAskRouter."""
        from taskforce.application.channel_ask_router import ChannelAskRouter

        return ChannelAskRouter.is_plain_ask_user(event)

    @staticmethod
    def _is_channel_targeted_ask(event):
        """Delegate to ChannelAskRouter."""
        from taskforce.application.channel_ask_router import ChannelAskRouter

        return ChannelAskRouter.is_channel_targeted_ask(event)

    async def _route_channel_question(self, **kwargs):
        """Delegate to ChannelAskRouter."""
        from taskforce.application.channel_ask_router import ChannelAskRouter

        router = ChannelAskRouter(self._gateway)
        return await router.route_channel_question(**kwargs)

    @staticmethod
    def _build_channel_question_sent_update(event):
        """Delegate to ChannelAskRouter."""
        from taskforce.application.channel_ask_router import ChannelAskRouter

        return ChannelAskRouter.build_question_sent_update(event)

    @staticmethod
    def _build_channel_response_received_update(channel_ask, response):
        """Delegate to ChannelAskRouter."""
        from taskforce.application.channel_ask_router import ChannelAskRouter

        return ChannelAskRouter.build_response_received_update(channel_ask, response)

    # Agent creation delegates (backward-compatible, kept for tests)

    async def _create_agent_from_plugin_path(self, *args, **kwargs):
        return await self._agent_pipeline._from_plugin_path(*args, **kwargs)

    async def _create_agent_from_agent_id(self, *args, **kwargs):
        return await self._agent_pipeline._from_agent_id(*args, **kwargs)

    def _validate_agent_id_format(self, agent_id):
        return self._agent_pipeline._validate_agent_id_format(agent_id)

    def _lookup_agent_definition(self, agent_id):
        return self._agent_pipeline._lookup_agent_definition(agent_id)

    async def _create_plugin_agent_from_definition(self, *args, **kwargs):
        return await self._agent_pipeline._from_plugin_definition(*args, **kwargs)

    async def _create_custom_agent_from_definition(self, *args, **kwargs):
        return await self._agent_pipeline._from_custom_definition(*args, **kwargs)

    async def _create_agent_from_profile(self, *args, **kwargs):
        return await self._agent_pipeline._from_profile(*args, **kwargs)

    async def _create_plugin_agent_via_profile_name(self, *args, **kwargs):
        return await self._agent_pipeline._from_plugin_via_profile_name(*args, **kwargs)

