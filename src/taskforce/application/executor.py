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
        agent_path: Hierarchical path of agent specialists when this event
            originated from a sub-agent (e.g. ``["coding_worker"]`` or
            ``["coding_worker", "test_engineer"]``).  ``None`` for events
            emitted by the root agent.
        parent_session_id: Session ID of the parent agent when this event
            originated from a sub-agent.  ``None`` for root events.
        source_agent: Specialist / agent identifier that emitted the event
            (matches the last element of ``agent_path``).  ``None`` for
            root events.
    """

    timestamp: datetime
    event_type: EventType | str  # Allow string for backward compatibility
    message: str
    details: dict[str, Any]
    agent_path: list[str] | None = None
    parent_session_id: str | None = None
    source_agent: str | None = None

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

        # Registry of agents currently running under a session_id.  Populated
        # at the start of ``execute_mission_streaming`` and cleared in the
        # matching ``finally`` block.  Enables :meth:`interrupt` to look up
        # the agent and request a cooperative pause.
        self._active_agents: dict[str, Agent] = {}

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
        work_dir: str | None = None,
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
            work_dir=work_dir,
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

    def interrupt(self, session_id: str) -> bool:
        """Request a cooperative pause for a running session.

        Looks up the agent currently executing under ``session_id`` and
        signals it to pause at the next ReAct loop boundary. The in-flight
        step (LLM call + tool calls) finishes normally; state is then
        persisted and an ``INTERRUPTED`` event is streamed out.

        Also forwards the interrupt to every running sub-agent spawned
        by orchestration tools under this session — the registry is
        managed by :mod:`taskforce.application.sub_agent_spawner`.

        Returns:
            True if an active agent or any sub-agent was found and
            signalled, False if nothing is currently running under the
            given session_id.
        """
        from taskforce.application.sub_agent_spawner import (
            request_interrupt_for_parent,
        )

        agent = self._active_agents.get(session_id)
        children_signalled = request_interrupt_for_parent(session_id)
        if agent is None and children_signalled == 0:
            self.logger.warning(
                "interrupt.no_active_agent",
                session_id=session_id,
            )
            return False
        if agent is not None:
            request_interrupt = getattr(agent, "request_interrupt", None)
            if callable(request_interrupt):
                request_interrupt()
        self.logger.info(
            "interrupt.requested",
            session_id=session_id,
            children_signalled=children_signalled,
        )
        return True

    def has_active_session(self, session_id: str) -> bool:
        """Return True if an agent is currently running under ``session_id``."""
        return session_id in self._active_agents

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
        work_dir: str | None = None,
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

        # Register with the in-memory run registry so the management UI
        # can list active runs. Lazy import keeps the executor module
        # cheap to import in tests that don't need analytics.
        try:
            from taskforce.application.run_registry import get_run_registry

            run_registry = get_run_registry()
            run_registry.register(
                resolved_session_id,
                profile=profile,
                agent_id=agent_id,
                mission=mission,
            )
        except Exception:  # noqa: BLE001
            run_registry = None

        try:
            from taskforce.application.infrastructure_overrides import (
                get_current_tenant_id,
                get_current_user_id,
                get_user_resolver,
            )
            from taskforce.application.run_trace_store import get_run_trace_store

            trace_store = get_run_trace_store()
            # Stamp tenant + user so /runs/recent can filter per-user
            # (ADR-022 iter-2). The user resolver is None on single-tenant
            # builds and the stamp stays None; the route then skips the
            # user filter and behaviour is bit-for-bit identical to today.
            stamp_user = get_current_user_id() if get_user_resolver() else None
            trace_store.start(
                resolved_session_id,
                mission=mission,
                profile=profile,
                agent_id=agent_id,
                tenant_id=get_current_tenant_id(),
                user_id=stamp_user,
            )
        except Exception:  # noqa: BLE001
            trace_store = None

        # Stamp run context so the LiteLLM token-ledger callback can
        # attach session/agent metadata to every record.
        from taskforce.application.token_ledger import run_context as _run_context

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

        # Notify mission-lifecycle observers (enterprise audit hook).
        # Failures are logged but never break the mission.
        import time as _time

        _started_at = _time.monotonic()
        await self._emit_mission_started(
            mission=mission,
            session_id=resolved_session_id,
            profile=profile,
            agent_id=agent_id,
        )

        if agent is None:
            agent = await self._agent_pipeline.create_agent(
                profile,
                user_context=user_context,
                agent_id=agent_id,
                planning_strategy=planning_strategy,
                planning_strategy_params=planning_strategy_params,
                plugin_path=plugin_path,
                work_dir=work_dir,
            )

        await self._maybe_store_conversation_history(
            agent=agent,
            session_id=resolved_session_id,
            conversation_history=conversation_history,
        )

        # Register the agent so that interrupt(session_id) can find it.
        # A previous entry under the same session_id is replaced (e.g. resume
        # after a prior interrupt).  Clear any stale interrupt flag so the
        # new run starts with a clean slate.  ``getattr`` guards against
        # agent doubles in the test suite that omit the interrupt surface;
        # the ``inspect`` check prevents the AsyncMock default from emitting
        # "coroutine was never awaited" warnings.
        self._active_agents[resolved_session_id] = agent
        _clear = getattr(agent, "clear_interrupt", None)
        if callable(_clear):
            _result = _clear()
            if asyncio.iscoroutine(_result):
                _result.close()

        execution_failed = False
        _failure_error: str | None = None
        try:
            with _run_context(
                session_id=resolved_session_id,
                agent_id=agent_id,
                profile=profile,
            ):
                async for update in self._execute_streaming(
                    agent,
                    mission,
                    resolved_session_id,
                    user_context=user_context,
                ):
                    if trace_store is not None:
                        try:
                            details = getattr(update, "details", None) or {}
                            evt = update.event_type
                            evt_str = evt.value if hasattr(evt, "value") else str(evt)
                            is_usage = evt_str == EventType.TOKEN_USAGE.value
                            trace_store.record(
                                resolved_session_id,
                                event_type=evt_str,
                                message=getattr(update, "message", "") or "",
                                details=details or None,
                                step=getattr(update, "step_number", None),
                                prompt_tokens=(
                                    int(details.get("prompt_tokens", 0)) if is_usage else 0
                                ),
                                completion_tokens=(
                                    int(details.get("completion_tokens", 0)) if is_usage else 0
                                ),
                                cost_usd=float(details.get("cost_usd", 0.0)) if is_usage else 0.0,
                            )
                        except Exception:  # noqa: BLE001
                            pass
                    yield update

            self.logger.info(
                "mission.streaming.completed",
                session_id=resolved_session_id,
                agent_id=agent_id,
                plugin_path=plugin_path,
            )

            await self._run_post_mission_learning(
                mission=mission,
                agent=agent,
                profile=profile,
                session_id=resolved_session_id,
            )

        except asyncio.CancelledError as e:
            execution_failed = True
            _failure_error = "cancelled"
            yield self._error_handler.handle_cancellation(
                e, resolved_session_id, agent_id, plugin_path
            )

        except Exception as e:
            execution_failed = True
            _failure_error = str(e)
            error_update, wrapped_error = self._error_handler.handle_streaming_failure(
                e, resolved_session_id, agent_id, plugin_path
            )
            yield error_update
            raise wrapped_error from e

        finally:
            await self._emit_mission_completed(
                mission=mission,
                session_id=resolved_session_id,
                profile=profile,
                agent_id=agent_id,
                success=not execution_failed,
                error=_failure_error,
                duration_seconds=_time.monotonic() - _started_at,
            )
            if run_registry is not None:
                run_registry.unregister(resolved_session_id)
            if trace_store is not None:
                try:
                    trace_store.finish(
                        resolved_session_id,
                        final_status="failed" if execution_failed else "completed",
                    )
                except Exception:  # noqa: BLE001
                    pass
            # Remove the agent from the active registry only if the entry
            # still points to the same instance (guards against a rare race
            # where a second run for the same session_id replaced it).
            if self._active_agents.get(resolved_session_id) is agent:
                self._active_agents.pop(resolved_session_id, None)
            if agent and owns_agent:
                asyncio.create_task(
                    self._deferred_close(agent, delay=2.0),
                    name="agent-close",
                )

    # ------------------------------------------------------------------
    # Mission lifecycle hook plumbing
    # ------------------------------------------------------------------

    async def _emit_mission_started(
        self,
        *,
        mission: str,
        session_id: str,
        profile: str,
        agent_id: str | None,
    ) -> None:
        """Best-effort notify of mission start. Hook failures never raise."""
        from taskforce.application.infrastructure_overrides import (
            get_mission_lifecycle_hook,
        )

        hook = get_mission_lifecycle_hook()
        if hook is None:
            return
        try:
            await hook.on_mission_started(
                mission=mission,
                session_id=session_id,
                profile=profile,
                agent_id=agent_id,
            )
        except Exception as exc:  # noqa: BLE001
            self.logger.warning(
                "mission.lifecycle_hook.start_failed",
                error=str(exc),
                session_id=session_id,
            )

    async def _emit_mission_completed(
        self,
        *,
        mission: str,
        session_id: str,
        profile: str,
        agent_id: str | None,
        success: bool,
        error: str | None,
        duration_seconds: float | None,
    ) -> None:
        """Best-effort notify of mission completion (success or failure)."""
        from taskforce.application.infrastructure_overrides import (
            get_mission_lifecycle_hook,
        )

        hook = get_mission_lifecycle_hook()
        if hook is None:
            return
        try:
            await hook.on_mission_completed(
                mission=mission,
                session_id=session_id,
                profile=profile,
                agent_id=agent_id,
                success=success,
                error=error,
                duration_seconds=duration_seconds,
            )
        except Exception as exc:  # noqa: BLE001
            self.logger.warning(
                "mission.lifecycle_hook.end_failed",
                error=str(exc),
                session_id=session_id,
            )

    # ------------------------------------------------------------------
    # Execution helpers
    # ------------------------------------------------------------------

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
                    # Ensure ask_user events have channel + recipient_id
                    # (fills in missing fields from source conversation context).
                    if source_channel and ask_router:
                        ask_router.ensure_channel_complete(
                            event, source_channel, source_conversation_id
                        )

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
                timeout_msg = (
                    f"Timeout waiting for response from "
                    f"{channel_ask['channel']}:{channel_ask['recipient_id']}"
                )
                yield ProgressUpdate(
                    timestamp=datetime.now(),
                    event_type=EventType.ERROR,
                    message=timeout_msg,
                    details=channel_ask,
                )
                # Also emit a COMPLETE event so execute_mission can build a
                # ExecutionResult and not raise "No completion event received".
                # Without this the unhandled AgentExecutionError bubbles up
                # through gateway.handle_message and crashes the CLI loop.
                yield ProgressUpdate(
                    timestamp=datetime.now(),
                    event_type=EventType.COMPLETE,
                    message=timeout_msg,
                    details={
                        "complete": True,
                        "status": ExecutionStatus.FAILED.value,
                        "final_message": timeout_msg,
                        "session_id": session_id,
                        "channel_question": channel_ask,
                    },
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
        """Store conversation history in agent state when provided.

        No-op for stateless foreign-runtime adapters that do not expose a
        ``state_manager`` attribute.
        """
        if not conversation_history:
            return

        state_manager = getattr(agent, "state_manager", None)
        if state_manager is None:
            return

        state = await state_manager.load_state(session_id) or {}
        state["conversation_history"] = conversation_history
        await state_manager.save_state(session_id, state)

    @staticmethod
    async def _deferred_close(agent: Agent, delay: float = 2.0) -> None:
        """Close agent after a delay so background consolidation can finish."""
        await asyncio.sleep(delay)
        try:
            await agent.close()
        except Exception:
            pass

    async def _run_post_mission_learning(
        self,
        mission: str,
        agent: Agent | None,
        profile: str | None,
        session_id: str,
    ) -> None:
        """Optionally extract reusable knowledge into the wiki.

        Activated only when the resolved profile config sets
        ``learning.enabled: true``. All exceptions are swallowed so
        learning never breaks the mission flow.
        """
        if agent is None or not profile:
            return
        try:
            from taskforce.application.profile_loader import ProfileLoader

            config = ProfileLoader().load(profile)
            learning_cfg = (config or {}).get("learning") or {}
            if not learning_cfg.get("enabled"):
                return

            wiki_store = getattr(agent, "_wiki_store", None) or getattr(agent, "wiki_store", None)
            llm_service = getattr(agent, "llm_provider", None)
            if wiki_store is None or llm_service is None:
                return

            messages = list(getattr(agent.context, "messages", []) or [])
            if not messages:
                return

            from taskforce.application.learning_service import (
                LlmExtractingLearningService,
            )

            service = LlmExtractingLearningService(
                wiki_store=wiki_store,
                llm_service=llm_service,
                model_alias=str(learning_cfg.get("model_alias", "fast")),
            )
            result = await service.learn_from_mission(
                mission=mission,
                messages=messages,
                session_id=session_id,
            )
            self.logger.info(
                "post_mission_learning",
                session_id=session_id,
                pages_written=result.pages_written,
                extracted=result.extracted_count,
                skipped=result.skipped_reason,
            )
        except Exception as e:
            self.logger.warning(
                "post_mission_learning_failed",
                session_id=session_id,
                error=repr(e),
            )
