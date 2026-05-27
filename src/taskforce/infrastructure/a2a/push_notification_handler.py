"""Push-notification handler for inbound A2A webhooks.

When a remote A2A peer is configured with push-notifications, it
POSTs the final ``Task`` payload to a callback URL once execution
completes asynchronously. This module owns the in-process registry
that correlates incoming webhooks with waiting client coroutines and
provides a polling fallback for deployments without a public
callback URL.

The matching FastAPI route lives in ``api/routes/a2a.py`` and just
delegates to :func:`PushNotificationHandler.dispatch`.
"""

from __future__ import annotations

import asyncio
from typing import Any

import structlog

from taskforce.core.domain.a2a import A2aPeer, A2aTaskHandle, A2aTaskState

logger = structlog.get_logger(__name__)


class PushNotificationHandler:
    """In-process correlation map for A2A push-notification webhooks.

    Callers register a task they expect to receive a webhook for and
    await the returned :class:`asyncio.Future`. The framework's
    webhook route calls :meth:`dispatch` with the raw payload from the
    remote peer; the matching future is resolved.
    """

    def __init__(self) -> None:
        self._pending: dict[str, asyncio.Future[dict[str, Any]]] = {}
        self._lock = asyncio.Lock()

    async def register(self, task_id: str) -> asyncio.Future[dict[str, Any]]:
        """Reserve a slot for ``task_id`` and return its future."""
        async with self._lock:
            existing = self._pending.get(task_id)
            if existing is not None and not existing.done():
                return existing
            fut: asyncio.Future[dict[str, Any]] = asyncio.get_running_loop().create_future()
            self._pending[task_id] = fut
            return fut

    async def dispatch(self, task_id: str, payload: dict[str, Any]) -> bool:
        """Resolve the future associated with ``task_id``. Returns True
        when a waiter was notified, False when no caller had registered."""
        async with self._lock:
            fut = self._pending.pop(task_id, None)
        if fut is None or fut.done():
            logger.debug("a2a.push.no_waiter", task_id=task_id)
            return False
        fut.set_result(payload)
        return True

    async def cancel(self, task_id: str) -> None:
        async with self._lock:
            fut = self._pending.pop(task_id, None)
        if fut is not None and not fut.done():
            fut.cancel()


async def poll_until_terminal(
    client: Any,
    peer: A2aPeer,
    task_id: str,
    *,
    interval: float = 5.0,
    max_attempts: int = 360,
) -> A2aTaskHandle:
    """Fallback for deployments without a public callback URL.

    Polls ``tasks/get`` on ``interval`` until the task reaches a
    terminal state or ``max_attempts`` is exceeded. Mirrors the
    asynchronous-task pattern in the A2A spec.
    """
    terminal = {
        A2aTaskState.COMPLETED,
        A2aTaskState.CANCELED,
        A2aTaskState.FAILED,
        A2aTaskState.REJECTED,
    }
    for _attempt in range(max_attempts):
        handle = await client.get_task(peer, task_id)
        if handle.state in terminal:
            return handle
        if handle.state in (A2aTaskState.INPUT_REQUIRED, A2aTaskState.AUTH_REQUIRED):
            return handle
        await asyncio.sleep(interval)
    raise TimeoutError(
        f"A2A task {task_id!r} on peer {peer.name!r} did not reach a "
        f"terminal state within {max_attempts * interval:.0f}s"
    )
