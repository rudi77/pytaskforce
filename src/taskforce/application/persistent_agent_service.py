"""Persistent Agent Service (ADR-016 Phase 5).

Singleton lifecycle manager that ties together the core components of the
persistent agent architecture:

- **AgentState** — global singleton state (save/load on start/stop)
- **RequestQueue + RequestProcessor** — sequential request processing
- **ConversationManager** — persistent conversation history
- **AgentExecutor** — actual agent execution

The service manages startup, shutdown, and graceful drain. It is the
single entry point for running a persistent (daemon-style) agent.

Usage::

    service = PersistentAgentService(
        executor=executor,
        agent_state=file_agent_state,
        conversation_manager=conv_manager,
        queue_max_size=100,
    )

    # Start (non-blocking — launches background processor)
    await service.start()

    # Enqueue requests from any channel
    result = await service.submit(request)

    # Graceful shutdown
    await service.stop()
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

import structlog

from taskforce.application.conversation_manager import ConversationManager
from taskforce.application.executor import AgentExecutor
from taskforce.application.request_queue import RequestProcessor, RequestQueue, RequestResult
from taskforce.core.domain.request import AgentRequest
from taskforce.core.interfaces.agent_state import AgentStateProtocol

logger = structlog.get_logger(__name__)


@dataclass
class AgentStatus:
    """Snapshot of the persistent agent's current status.

    Attributes:
        running: Whether the agent is actively processing.
        queue_size: Number of pending requests.
        active_conversations: Number of active conversations.
        started_at: When the agent was started.
        last_activity: Timestamp of last processed request.
        state_version: Version counter from AgentState.
    """

    running: bool = False
    queue_size: int = 0
    active_conversations: int = 0
    started_at: datetime | None = None
    last_activity: datetime | None = None
    state_version: int = 0


class PersistentAgentService:
    """Singleton agent lifecycle manager.

    Orchestrates the persistent agent's startup, request processing,
    state persistence, and graceful shutdown.

    The agent runs as a single process with a sequential request queue,
    ensuring no race conditions on shared state. Sub-agents spawned
    during execution operate on their own ephemeral contexts.
    """

    def __init__(
        self,
        *,
        executor: AgentExecutor,
        agent_state: AgentStateProtocol,
        conversation_manager: ConversationManager,
        queue_max_size: int = 100,
        drain_timeout: float = 30.0,
    ) -> None:
        self._executor = executor
        self._agent_state = agent_state
        self._conversation_manager = conversation_manager
        self._drain_timeout = drain_timeout

        self._queue = RequestQueue(max_size=queue_max_size)
        self._processor = RequestProcessor(
            self._queue,
            self._executor,
            conversation_manager=self._conversation_manager,
        )

        self._processor_task: asyncio.Task[None] | None = None
        self._started_at: datetime | None = None
        self._last_activity: datetime | None = None
        self._state_version: int = 0
        self._logger = structlog.get_logger(__name__)

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def start(self) -> None:
        """Start the persistent agent.

        1. Loads agent state from persistent storage.
        2. Launches the ``RequestProcessor`` as a background task.

        Raises:
            RuntimeError: If the agent is already running.
        """
        if self._processor_task and not self._processor_task.done():
            raise RuntimeError("PersistentAgentService is already running")

        # Load persisted state.
        state = await self._agent_state.load()
        if state:
            self._state_version = state.get("_version", 0)
            self._logger.info(
                "persistent_agent.state_loaded",
                version=self._state_version,
                active_conversations=state.get("active_conversation_count", 0),
            )

        self._started_at = datetime.now(UTC)
        self._processor_task = asyncio.create_task(
            self._run_processor(), name="persistent-agent-processor"
        )

        self._logger.info("persistent_agent.started")

    async def stop(self) -> None:
        """Gracefully stop the persistent agent.

        1. Drains the request queue (waits for in-flight requests).
        2. Cancels the processor task.
        3. Saves agent state to persistent storage.
        """
        if not self._processor_task:
            return

        self._logger.info("persistent_agent.stopping")

        # Drain pending requests.
        try:
            await self._queue.drain(timeout=self._drain_timeout)
        except asyncio.TimeoutError:
            self._logger.warning(
                "persistent_agent.drain_timeout",
                remaining=self._queue.size,
            )

        # Cancel processor.
        self._processor_task.cancel()
        try:
            await self._processor_task
        except asyncio.CancelledError:
            pass
        self._processor_task = None

        # Persist state.
        await self._save_state()

        self._logger.info("persistent_agent.stopped")

    # ------------------------------------------------------------------
    # Request submission
    # ------------------------------------------------------------------

    async def submit(self, request: AgentRequest) -> RequestResult:
        """Submit a request for processing and await the result.

        This is the primary entry point for all channels. The request is
        enqueued and processed sequentially by the ``RequestProcessor``.

        Args:
            request: The agent request to process.

        Returns:
            The processing result.

        Raises:
            RuntimeError: If the agent is not running.
        """
        if not self._processor_task or self._processor_task.done():
            raise RuntimeError("PersistentAgentService is not running")

        future = await self._queue.enqueue(request)
        result = await future

        self._last_activity = datetime.now(UTC)
        return result

    # ------------------------------------------------------------------
    # Introspection
    # ------------------------------------------------------------------

    @property
    def running(self) -> bool:
        """Whether the agent is actively processing."""
        return self._processor_task is not None and not self._processor_task.done()

    @property
    def queue(self) -> RequestQueue:
        """The underlying request queue (for direct access if needed)."""
        return self._queue

    async def status(self) -> AgentStatus:
        """Get a snapshot of the agent's current status."""
        active_convs = await self._conversation_manager.list_active()
        return AgentStatus(
            running=self.running,
            queue_size=self._queue.size,
            active_conversations=len(active_convs),
            started_at=self._started_at,
            last_activity=self._last_activity,
            state_version=self._state_version,
        )

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    async def _run_processor(self) -> None:
        """Run the request processor and handle unexpected exits."""
        try:
            await self._processor.run()
        except asyncio.CancelledError:
            raise
        except Exception:
            self._logger.exception("persistent_agent.processor_crashed")
            raise

    async def _save_state(self) -> None:
        """Persist the current agent state."""
        active_convs = await self._conversation_manager.list_active()
        state: dict[str, Any] = {
            "_version": self._state_version,
            "started_at": self._started_at.isoformat() if self._started_at else None,
            "last_activity": (
                self._last_activity.isoformat() if self._last_activity else None
            ),
            "active_conversation_ids": [c.conversation_id for c in active_convs],
            "active_conversation_count": len(active_convs),
        }
        await self._agent_state.save(state)
        self._logger.info(
            "persistent_agent.state_saved",
            active_conversations=len(active_convs),
        )
