"""Central request queue and processor for the persistent agent (ADR-016).

All inbound messages — from Telegram, CLI, REST, or internal events — are
normalized into ``AgentRequest`` objects and processed sequentially by the
``RequestProcessor``.

The ``RequestQueue`` provides back-pressure via a bounded ``asyncio.Queue``
and returns ``asyncio.Future[RequestResult]`` so callers can ``await`` the
outcome of their enqueued request.

Usage::

    queue = RequestQueue(max_size=100)

    # Producer: enqueue and await result
    future = await queue.enqueue(request)
    result = await future  # blocks until processed

    # Consumer: run the processing loop
    processor = RequestProcessor(queue, executor, conversation_manager)
    task = asyncio.create_task(processor.run())

    # Graceful shutdown
    await queue.drain(timeout=30.0)
    task.cancel()
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

import structlog

from taskforce.core.domain.enums import MessageRole
from taskforce.core.domain.request import AgentRequest

if TYPE_CHECKING:
    from taskforce.application.conversation_manager import ConversationManager
    from taskforce.application.executor import AgentExecutor

logger = structlog.get_logger(__name__)


@dataclass
class RequestResult:
    """Result of processing a single queued request.

    Attributes:
        request_id: The original request ID.
        conversation_id: The conversation this request belongs to.
        status: Execution status (completed, failed, etc.).
        reply: The agent's reply message.
        error: Error message if processing failed.
    """

    request_id: str
    conversation_id: str | None = None
    status: str = "completed"
    reply: str = ""
    error: str | None = None


class _PrioritizedItem:
    """Wrapper for priority queue ordering.

    Uses ``(priority, sequence, request)`` so that ties in priority
    are broken by insertion order (FIFO within same priority level).
    """

    __slots__ = ("priority", "seq", "request")

    _counter: int = 0

    def __init__(self, request: AgentRequest) -> None:
        self.priority = request.priority
        _PrioritizedItem._counter += 1
        self.seq = _PrioritizedItem._counter
        self.request = request

    def __lt__(self, other: _PrioritizedItem) -> bool:  # type: ignore[override]
        if self.priority != other.priority:
            return self.priority < other.priority
        return self.seq < other.seq


class RequestQueue:
    """Central priority queue for agent requests.

    Requests are ordered by ``AgentRequest.priority`` (lower = higher priority),
    with FIFO ordering within the same priority level.

    The queue ensures that the singleton agent processes one request
    at a time (sequentially), preventing race conditions on shared state.
    Sub-agents can still run in parallel since they operate on their own
    ephemeral contexts.

    Callers receive an ``asyncio.Future[RequestResult]`` from ``enqueue``
    that resolves once the request has been processed.
    """

    def __init__(self, max_size: int = 100) -> None:
        self._queue: asyncio.PriorityQueue[_PrioritizedItem] = asyncio.PriorityQueue(
            maxsize=max_size
        )
        self._futures: dict[str, asyncio.Future[RequestResult]] = {}
        self._running = False

    @property
    def size(self) -> int:
        """Number of requests currently waiting in the queue."""
        return self._queue.qsize()

    @property
    def is_running(self) -> bool:
        """Whether the processing loop is active."""
        return self._running

    def set_running(self, value: bool) -> None:
        """Mark the queue as having an active consumer.

        Called by ``RequestProcessor.run()`` and ``process_loop()`` to
        signal that a consumer is attached.
        """
        self._running = value

    @property
    def pending_count(self) -> int:
        """Number of requests with outstanding Futures."""
        return len(self._futures)

    async def enqueue(self, request: AgentRequest) -> asyncio.Future[RequestResult]:
        """Add a request to the queue and return a Future for its result.

        Blocks if the queue is full (back-pressure). Requests are ordered
        by priority (lower value = higher priority).

        Args:
            request: The ``AgentRequest`` to enqueue.

        Returns:
            A Future that resolves to ``RequestResult`` when the request
            has been processed.
        """
        loop = asyncio.get_running_loop()
        future: asyncio.Future[RequestResult] = loop.create_future()
        self._futures[request.request_id] = future
        await self._queue.put(_PrioritizedItem(request))
        logger.debug(
            "request_queue.enqueued",
            request_id=request.request_id,
            channel=request.channel,
            priority=request.priority,
            queue_size=self._queue.qsize(),
        )
        return future

    async def dequeue(self) -> AgentRequest:
        """Get the highest-priority request from the queue (blocks until available)."""
        item = await self._queue.get()
        return item.request

    def complete(self, request_id: str, result: RequestResult) -> None:
        """Mark a request as completed and resolve its Future.

        Args:
            request_id: The request to complete.
            result: The processing result.
        """
        future = self._futures.pop(request_id, None)
        if future and not future.done():
            future.set_result(result)
        self._queue.task_done()

    def fail(self, request_id: str, error: str) -> None:
        """Mark a request as failed and resolve its Future with an error result.

        Args:
            request_id: The request that failed.
            error: Error description.
        """
        result = RequestResult(request_id=request_id, status="failed", error=error)
        future = self._futures.pop(request_id, None)
        if future and not future.done():
            future.set_result(result)
        self._queue.task_done()

    async def drain(self, timeout: float = 10.0) -> None:
        """Wait for all queued requests to be processed.

        Args:
            timeout: Maximum seconds to wait before giving up.

        Raises:
            asyncio.TimeoutError: If the queue doesn't drain in time.
        """
        await asyncio.wait_for(self._queue.join(), timeout=timeout)

    async def process_loop(
        self,
        handler: Any,
    ) -> None:
        """Main processing loop — runs until cancelled.

        Dequeues requests one at a time and passes them to ``handler``.
        If the handler raises an exception, the error is logged and
        processing continues with the next request.

        This method is the **legacy** interface. Prefer ``RequestProcessor``
        for new code, which provides ConversationManager integration and
        Future-based result delivery.

        Args:
            handler: Async callable that processes a single ``AgentRequest``.
        """
        self._running = True
        logger.info("request_queue.started")
        try:
            while True:
                item = await self._queue.get()
                request = item.request
                try:
                    logger.info(
                        "request_queue.processing",
                        request_id=request.request_id,
                        channel=request.channel,
                    )
                    await handler(request)
                    logger.info(
                        "request_queue.completed",
                        request_id=request.request_id,
                    )
                except Exception:
                    logger.exception(
                        "request_queue.handler_error",
                        request_id=request.request_id,
                        channel=request.channel,
                    )
                finally:
                    self._queue.task_done()
        except asyncio.CancelledError:
            logger.info("request_queue.stopped")
            raise
        finally:
            self._running = False


class RequestProcessor:
    """Consumes requests from the ``RequestQueue`` and executes them.

    Each request is handled sequentially to prevent race conditions on shared
    agent state. Results are delivered back via the queue's Future mechanism.

    When a ``ConversationManager`` is provided, the processor appends user
    and assistant messages to the persistent conversation before/after
    agent execution.
    """

    def __init__(
        self,
        queue: RequestQueue,
        executor: AgentExecutor,
        conversation_manager: ConversationManager | None = None,
    ) -> None:
        self._queue = queue
        self._executor = executor
        self._conversation_manager = conversation_manager
        self._running = False
        self._logger = structlog.get_logger(__name__)

    @property
    def running(self) -> bool:
        """Whether the processing loop is currently active."""
        return self._running

    async def run(self) -> None:
        """Main processing loop — runs until cancelled.

        Dequeues requests one at a time and processes them. Exceptions in
        individual request handling are caught and reported via the
        queue's ``fail()`` mechanism so the loop continues.
        """
        self._running = True
        self._queue.set_running(True)
        self._logger.info("request_processor.started")
        try:
            while True:
                request = await self._queue.dequeue()
                await self._process_request(request)
        except asyncio.CancelledError:
            self._logger.info("request_processor.stopped")
            raise
        finally:
            self._running = False
            self._queue.set_running(False)

    async def _process_request(self, request: AgentRequest) -> None:
        """Process a single request and deliver the result."""
        self._logger.info(
            "request_processor.processing",
            request_id=request.request_id,
            channel=request.channel,
            conversation_id=request.conversation_id,
        )
        try:
            result = await self._execute(request)
            self._queue.complete(request.request_id, result)
        except Exception as exc:
            self._logger.error(
                "request_processor.failed",
                request_id=request.request_id,
                error=str(exc),
            )
            self._queue.fail(request.request_id, str(exc))

    async def _execute(self, request: AgentRequest) -> RequestResult:
        """Execute the request via the agent executor."""
        conversation_history: list[dict[str, Any]] = []
        conv_id = request.conversation_id

        # Build conversation context if ConversationManager is available.
        if self._conversation_manager and conv_id:
            await self._conversation_manager.append_message(
                conv_id,
                {"role": MessageRole.USER.value, "content": request.message},
            )
            conversation_history = await self._conversation_manager.get_messages(conv_id)

        # Reuse stable session_id when provided (gateway passes it through);
        # fall back to request_id for standalone/event-driven requests.
        effective_session_id = request.session_id or request.request_id
        meta = request.metadata

        result = await self._executor.execute_mission(
            mission=request.message,
            profile=meta.get("profile", "butler"),
            session_id=effective_session_id,
            conversation_history=conversation_history,
            user_context=meta.get("user_context"),
            agent_id=meta.get("agent_id"),
            planning_strategy=meta.get("planning_strategy"),
            planning_strategy_params=meta.get("planning_strategy_params"),
            plugin_path=meta.get("plugin_path"),
        )

        # Store assistant reply in conversation.
        if self._conversation_manager and conv_id:
            await self._conversation_manager.append_message(
                conv_id,
                {"role": MessageRole.ASSISTANT.value, "content": result.final_message},
            )

        return RequestResult(
            request_id=request.request_id,
            conversation_id=conv_id,
            status=result.status,
            reply=result.final_message,
        )
