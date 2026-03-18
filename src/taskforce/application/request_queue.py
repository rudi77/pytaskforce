"""
Request Queue

Central request queue for the persistent agent (ADR-016). All inbound
messages — from Telegram, CLI, REST, or internal events — are normalized
into ``AgentRequest`` objects and processed sequentially by the agent.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from typing import Any

import structlog

from taskforce.core.domain.request import AgentRequest

logger = structlog.get_logger(__name__)

# Type alias for the handler function.
RequestHandler = Callable[[AgentRequest], Awaitable[Any]]


class RequestQueue:
    """Central FIFO queue for agent requests.

    The queue ensures that the singleton agent processes one request
    at a time (sequentially), preventing race conditions on shared state.
    Sub-agents can still run in parallel since they operate on their own
    ephemeral contexts.

    Usage::

        queue = RequestQueue(max_size=100)

        # Producer: enqueue from any channel
        await queue.enqueue(AgentRequest(channel="telegram", message="Hello"))

        # Consumer: run the processing loop
        await queue.process_loop(handler=my_handler_fn)
    """

    def __init__(self, max_size: int = 100) -> None:
        self._queue: asyncio.Queue[AgentRequest] = asyncio.Queue(maxsize=max_size)
        self._running = False

    @property
    def size(self) -> int:
        """Number of requests currently waiting in the queue."""
        return self._queue.qsize()

    @property
    def is_running(self) -> bool:
        """Whether the processing loop is active."""
        return self._running

    async def enqueue(self, request: AgentRequest) -> None:
        """Add a request to the queue.

        Blocks if the queue is full (back-pressure).

        Args:
            request: The ``AgentRequest`` to enqueue.
        """
        await self._queue.put(request)
        logger.debug(
            "request_queue.enqueued",
            request_id=request.request_id,
            channel=request.channel,
            queue_size=self._queue.qsize(),
        )

    async def process_loop(self, handler: RequestHandler) -> None:
        """Main processing loop — runs until cancelled.

        Dequeues requests one at a time and passes them to ``handler``.
        If the handler raises an exception, the error is logged and
        processing continues with the next request.

        Args:
            handler: Async callable that processes a single ``AgentRequest``.
        """
        self._running = True
        logger.info("request_queue.started")
        try:
            while True:
                request = await self._queue.get()
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

    async def drain(self, timeout: float = 10.0) -> None:
        """Wait for all queued requests to be processed.

        Args:
            timeout: Maximum seconds to wait before giving up.

        Raises:
            asyncio.TimeoutError: If the queue doesn't drain in time.
        """
        await asyncio.wait_for(self._queue.join(), timeout=timeout)
