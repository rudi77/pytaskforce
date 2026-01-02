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

import uuid
from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Any

import structlog

from taskforce.application.factory import AgentFactory
from taskforce.core.domain.agent import Agent
from taskforce.core.domain.lean_agent import LeanAgent
from taskforce.core.domain.models import ExecutionResult, StreamEvent

logger = structlog.get_logger()


@dataclass
class ProgressUpdate:
    """Progress update during execution.

    Represents a single event during agent execution that can be
    streamed to consumers for real-time progress tracking.

    Attributes:
        timestamp: When this update occurred
        event_type: Type of event (started, thought, action, observation, complete, error)
        message: Human-readable message describing the event
        details: Additional structured data about the event
    """

    timestamp: datetime
    event_type: str
    message: str
    details: dict


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
        use_lean_agent: bool = False,
        agent_id: str | None = None,
    ) -> ExecutionResult:
        """Execute agent mission with comprehensive orchestration.

        Main entry point for mission execution. Orchestrates the complete
        workflow from agent creation through execution to result delivery.

        Workflow:
        1. Create agent using factory based on profile
        2. Generate or use provided session ID
        3. Execute agent ReAct loop with progress tracking
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
            use_lean_agent: If True, use LeanAgent instead of legacy Agent.
                           LeanAgent uses native tool calling and PlannerTool.
            agent_id: Optional custom agent ID. If provided, loads agent
                     definition from configs/custom/{agent_id}.yaml and
                     creates LeanAgent (ignores use_lean_agent flag).

        Returns:
            ExecutionResult with completion status and history

        Raises:
            Exception: If agent creation or execution fails
        """
        start_time = datetime.now()

        # Generate session ID if not provided
        if session_id is None:
            session_id = self._generate_session_id()

        self.logger.info(
            "mission.execution.started",
            mission=mission[:100],
            profile=profile,
            session_id=session_id,
            has_user_context=user_context is not None,
            use_lean_agent=use_lean_agent,
            agent_id=agent_id,
        )

        agent = None
        try:
            # Create agent with appropriate adapters
            agent = await self._create_agent(
                profile,
                user_context=user_context,
                use_lean_agent=use_lean_agent,
                agent_id=agent_id,
            )

            # Store conversation history in state if provided
            if conversation_history:
                state = await agent.state_manager.load_state(session_id) or {}
                state["conversation_history"] = conversation_history
                await agent.state_manager.save_state(session_id, state)

            # Execute ReAct loop with progress tracking
            result = await self._execute_with_progress(
                agent=agent,
                mission=mission,
                session_id=session_id,
                progress_callback=progress_callback,
            )

            duration = (datetime.now() - start_time).total_seconds()

            self.logger.info(
                "mission.execution.completed",
                session_id=session_id,
                status=result.status,
                duration_seconds=duration,
                agent_id=agent_id,
            )

            return result

        except Exception as e:
            duration = (datetime.now() - start_time).total_seconds()

            self.logger.error(
                "mission.execution.failed",
                session_id=session_id,
                error=str(e),
                error_type=type(e).__name__,
                duration_seconds=duration,
                agent_id=agent_id,
            )
            raise

        finally:
            # Clean up MCP connections to avoid cancel scope errors
            if agent:
                await agent.close()

    async def execute_mission_streaming(
        self,
        mission: str,
        profile: str = "dev",
        session_id: str | None = None,
        conversation_history: list[dict[str, Any]] | None = None,
        user_context: dict[str, Any] | None = None,
        use_lean_agent: bool = False,
        agent_id: str | None = None,
    ) -> AsyncIterator[ProgressUpdate]:
        """Execute mission with streaming progress updates.

        Yields ProgressUpdate objects as execution progresses, enabling
        real-time feedback to consumers (CLI progress bars, API SSE, etc).

        Args:
            mission: Mission description
            profile: Configuration profile (dev/staging/prod)
            session_id: Optional existing session to resume
            conversation_history: Optional conversation history for chat context
            user_context: Optional user context for RAG security filtering
            use_lean_agent: If True, use LeanAgent instead of legacy Agent
            agent_id: Optional custom agent ID. If provided, loads agent
                     definition and creates LeanAgent (ignores use_lean_agent).

        Yields:
            ProgressUpdate objects for each execution event

        Raises:
            Exception: If agent creation or execution fails
        """
        # Generate session ID if not provided
        if session_id is None:
            session_id = self._generate_session_id()

        self.logger.info(
            "mission.streaming.started",
            mission=mission[:100],
            profile=profile,
            session_id=session_id,
            has_user_context=user_context is not None,
            use_lean_agent=use_lean_agent,
            agent_id=agent_id,
        )

        # Yield initial started event
        yield ProgressUpdate(
            timestamp=datetime.now(),
            event_type="started",
            message=f"Starting mission: {mission[:80]}",
            details={
                "session_id": session_id,
                "profile": profile,
                "lean": use_lean_agent,
                "agent_id": agent_id,
            },
        )

        agent = None
        try:
            # Create agent
            agent = await self._create_agent(
                profile,
                user_context=user_context,
                use_lean_agent=use_lean_agent,
                agent_id=agent_id,
            )

            # Store conversation history in state if provided
            if conversation_history:
                state = await agent.state_manager.load_state(session_id) or {}
                state["conversation_history"] = conversation_history
                await agent.state_manager.save_state(session_id, state)

            # Execute with streaming
            async for update in self._execute_streaming(agent, mission, session_id):
                yield update

            self.logger.info(
                "mission.streaming.completed", session_id=session_id, agent_id=agent_id
            )

        except Exception as e:
            self.logger.error(
                "mission.streaming.failed",
                session_id=session_id,
                error=str(e),
                error_type=type(e).__name__,
                agent_id=agent_id,
            )

            # Yield error event
            yield ProgressUpdate(
                timestamp=datetime.now(),
                event_type="error",
                message=f"Execution failed: {str(e)}",
                details={"error": str(e), "error_type": type(e).__name__},
            )

            raise

        finally:
            # Clean up MCP connections to avoid cancel scope errors
            if agent:
                await agent.close()

    async def _create_agent(
        self,
        profile: str,
        user_context: dict[str, Any] | None = None,
        use_lean_agent: bool = False,
        agent_id: str | None = None,
    ) -> Agent | LeanAgent:
        """Create agent using factory.

        Creates either legacy Agent or LeanAgent based on parameters:
        - agent_id provided: Loads custom agent definition and creates LeanAgent
        - use_lean_agent=True: Creates LeanAgent (native tool calling, PlannerTool)
        - user_context provided: Creates RAG agent (legacy)
        - Otherwise: Creates standard Agent (legacy)

        Args:
            profile: Configuration profile name
            user_context: Optional user context for RAG security filtering
            use_lean_agent: If True, create LeanAgent instead of legacy Agent
            agent_id: Optional custom agent ID to load from registry

        Returns:
            Agent or LeanAgent instance with injected dependencies

        Raises:
            FileNotFoundError: If agent_id provided but not found (404)
            ValueError: If agent definition is invalid/corrupt (400)
        """
        self.logger.debug(
            "creating_agent",
            profile=profile,
            has_user_context=user_context is not None,
            use_lean_agent=use_lean_agent,
            agent_id=agent_id,
        )

        # agent_id takes highest priority - load custom agent definition
        if agent_id:
            from taskforce.infrastructure.persistence.file_agent_registry import (
                FileAgentRegistry,
            )

            registry = FileAgentRegistry()
            agent_response = registry.get_agent(agent_id)

            if not agent_response:
                raise FileNotFoundError(f"Agent '{agent_id}' not found")

            # Only custom agents can be used for execution (not profile agents)
            if agent_response.source != "custom":
                raise ValueError(
                    f"Agent '{agent_id}' is a profile agent, not a custom agent. "
                    "Use 'profile' parameter for profile agents."
                )

            # Convert response to definition dict
            agent_definition = {
                "system_prompt": agent_response.system_prompt,
                "tool_allowlist": agent_response.tool_allowlist,
                "mcp_servers": agent_response.mcp_servers,
                "mcp_tool_allowlist": agent_response.mcp_tool_allowlist,
            }

            self.logger.info(
                "loading_custom_agent",
                agent_id=agent_id,
                agent_name=agent_response.name,
                tool_count=len(agent_response.tool_allowlist),
            )

            return await self.factory.create_lean_agent_from_definition(
                agent_definition=agent_definition,
                profile=profile,
            )

        # LeanAgent takes priority if requested (with optional user_context for RAG)
        if use_lean_agent:
            return await self.factory.create_lean_agent(
                profile=profile, user_context=user_context
            )

        # Use RAG agent factory when user_context is provided
        if user_context:
            return await self.factory.create_rag_agent(
                profile=profile, user_context=user_context
            )

        return await self.factory.create_agent(profile=profile)

    async def _execute_with_progress(
        self,
        agent: Agent | LeanAgent,
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
                event_type="complete",
                message=result.final_message,
                details={
                    "status": result.status,
                    "session_id": result.session_id,
                    "todolist_id": result.todolist_id,
                },
            )
        )

        return result

    async def _execute_streaming(
        self, agent: Agent | LeanAgent, mission: str, session_id: str
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
        # Check if agent supports streaming (LeanAgent has execute_stream)
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
                event_type = event.get("type", "unknown")
                step = event.get("step", "?")

                if event_type == "thought":
                    data = event.get("data", {})
                    rationale = data.get("rationale", "")
                    yield ProgressUpdate(
                        timestamp=datetime.now(),
                        event_type="thought",
                        message=f"Step {step}: {rationale[:80]}",
                        details=data,
                    )

                elif event_type == "observation":
                    data = event.get("data", {})
                    success = data.get("success", False)
                    status = "success" if success else "failed"
                    yield ProgressUpdate(
                        timestamp=datetime.now(),
                        event_type="observation",
                        message=f"Step {step}: {status}",
                        details=data,
                    )

            # Yield final completion update
            yield ProgressUpdate(
                timestamp=datetime.now(),
                event_type="complete",
                message=result.final_message,
                details={
                    "status": result.status,
                    "session_id": result.session_id,
                    "todolist_id": result.todolist_id,
                },
            )

    def _stream_event_to_progress_update(self, event: StreamEvent) -> ProgressUpdate:
        """Convert StreamEvent to ProgressUpdate for API consumers.

        Maps LeanAgent StreamEvent types to human-readable messages
        for CLI and API streaming consumers.

        Args:
            event: StreamEvent from agent execution

        Returns:
            ProgressUpdate for consumer display
        """
        message_map = {
            "step_start": lambda d: f"Step {d.get('step', '?')} starting...",
            "llm_token": lambda d: d.get("content", ""),
            "tool_call": lambda d: f"🔧 Calling: {d.get('tool', 'unknown')}",
            "tool_result": lambda d: (
                f"{'✅' if d.get('success') else '❌'} "
                f"{d.get('tool', 'unknown')}: {str(d.get('output', ''))[:50]}"
            ),
            "plan_updated": lambda d: f"📋 Plan updated ({d.get('action', 'unknown')})",
            "final_answer": lambda d: d.get("content", ""),
            "error": lambda d: f"⚠️ Error: {d.get('message', 'unknown')}",
        }

        message_fn = message_map.get(event.event_type, lambda d: str(d))

        return ProgressUpdate(
            timestamp=event.timestamp,
            event_type=event.event_type,
            message=message_fn(event.data),
            details=event.data,
        )

    def _generate_session_id(self) -> str:
        """Generate unique session ID.

        Returns:
            UUID-based session identifier
        """
        return str(uuid.uuid4())

