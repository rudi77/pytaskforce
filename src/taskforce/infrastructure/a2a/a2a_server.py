"""Embedded A2A server wrapping the ``a2a-sdk`` route builders.

The SDK ships JSON-RPC + agent-card route factories that return
``starlette.routing.Route`` objects. We wire them into a Starlette
app and serve via uvicorn — mirroring :class:`AcpServer`.

A Taskforce mission handler is bridged through a small
:class:`_TaskforceAgentExecutor` adapter. The handler signature stays
plain-Python (``async def handler(mission, session_id) -> str``) so
caller code never depends on ``a2a-sdk`` types.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from typing import Any

import structlog

from taskforce.infrastructure.a2a._sdk import (
    load_server_agent_execution,
    load_server_request_handlers,
    load_server_routes,
    load_types,
)

logger = structlog.get_logger(__name__)


A2aMissionHandler = Callable[[str, str | None], Awaitable[str]]


class A2aServer:
    """Thin wrapper around the a2a-sdk server building blocks.

    Lifecycle mirrors :class:`AcpServer`: handlers (here: the bridge to
    a Taskforce mission handler) are registered via
    :meth:`register_agent` before ``start()``. The server runs inside
    an ``asyncio.Task`` so ``start()`` is non-blocking; ``stop()`` sets
    ``should_exit`` on the underlying uvicorn server and awaits the task.
    """

    def __init__(self, *, host: str = "0.0.0.0", port: int = 9000) -> None:
        self._host = host
        self._port = port
        self._uvicorn_server: Any | None = None
        self._task: asyncio.Task[Any] | None = None
        self._agent_card: Any | None = None
        self._handler: A2aMissionHandler | None = None
        self._started = asyncio.Event()
        self._running = False

    @property
    def is_running(self) -> bool:
        return self._running

    @property
    def host(self) -> str:
        return self._host

    @property
    def port(self) -> int:
        return self._port

    def register_agent(self, card: Any, handler: A2aMissionHandler) -> None:
        """Bind the local AgentCard + mission handler to the server.

        ``card`` is an ``a2a.types.AgentCard`` proto (build it via
        :func:`agent_card_builder.build_agent_card`).
        """
        if self._running:
            raise RuntimeError("Cannot register A2A agent while server is running; stop it first.")
        self._agent_card = card
        self._handler = handler
        logger.debug("a2a.server.agent_registered", agent=getattr(card, "name", "?"))

    def registered_card(self) -> Any | None:
        return self._agent_card

    async def start(self) -> None:
        if self._running:
            return
        if self._agent_card is None or self._handler is None:
            raise RuntimeError(
                "A2A server cannot start without a registered agent — "
                "call register_agent(card, handler) first."
            )
        app = self._build_starlette_app()
        import uvicorn  # type: ignore[import-not-found]

        config = uvicorn.Config(app, host=self._host, port=self._port, log_level="warning")
        self._uvicorn_server = uvicorn.Server(config)
        self._task = asyncio.create_task(self._uvicorn_server.serve())
        self._running = True
        self._started.set()
        logger.info("a2a.server.started", host=self._host, port=self._port)

    async def stop(self) -> None:
        if not self._running:
            return
        self._running = False
        if self._uvicorn_server is not None:
            try:
                self._uvicorn_server.should_exit = True
            except Exception:  # pragma: no cover - defensive
                pass
        if self._task is not None:
            try:
                await asyncio.wait_for(self._task, timeout=5.0)
            except TimeoutError:
                self._task.cancel()
                try:
                    await self._task
                except (asyncio.CancelledError, Exception):
                    pass
            except (asyncio.CancelledError, Exception):
                pass
            self._task = None
        self._uvicorn_server = None
        self._started.clear()
        logger.info("a2a.server.stopped")

    async def wait_started(self, timeout: float = 5.0) -> None:
        await asyncio.wait_for(self._started.wait(), timeout=timeout)
        if self._uvicorn_server is not None:
            deadline = asyncio.get_event_loop().time() + timeout
            while not getattr(self._uvicorn_server, "started", False):
                if asyncio.get_event_loop().time() > deadline:
                    raise TimeoutError(f"A2A server failed to start within {timeout}s")
                await asyncio.sleep(0.05)

    def _build_starlette_app(self) -> Any:
        from starlette.applications import Starlette  # type: ignore[import-not-found]

        routes_mod = load_server_routes()
        request_handlers = load_server_request_handlers()
        executor = _TaskforceAgentExecutor(self._handler)

        from a2a.server.tasks import InMemoryTaskStore  # type: ignore[import-not-found]

        request_handler = request_handlers.DefaultRequestHandler(
            agent_executor=executor,
            task_store=InMemoryTaskStore(),
            agent_card=self._agent_card,
        )
        routes = list(routes_mod.create_agent_card_routes(self._agent_card))
        routes.extend(routes_mod.create_jsonrpc_routes(request_handler, rpc_url="/"))
        return Starlette(routes=routes)


class _TaskforceAgentExecutor:
    """Bridge a plain Taskforce mission handler to the a2a-sdk
    ``AgentExecutor`` interface.

    Inherits implicitly via duck typing; the SDK calls ``execute`` and
    ``cancel`` on any object with matching signatures.
    """

    def __init__(self, handler: A2aMissionHandler) -> None:
        self._handler = handler
        self._cancelled: set[str] = set()

    async def execute(self, context: Any, event_queue: Any) -> None:
        types = load_types()
        load_server_agent_execution()
        mission = _extract_mission_text(context)
        session_id = getattr(context, "context_id", None)
        task_id = getattr(context, "task_id", None) or ""
        context_id = session_id or task_id

        task = types.Task(id=task_id, context_id=context_id)
        task.status.state = types.TaskState.TASK_STATE_WORKING
        await _enqueue(event_queue, task)

        try:
            response_text = await self._handler(mission, session_id)
            if task_id in self._cancelled:
                await _enqueue_status(
                    event_queue,
                    types,
                    task_id,
                    context_id,
                    types.TaskState.TASK_STATE_CANCELED,
                    "",
                )
                return
            await _enqueue_status(
                event_queue,
                types,
                task_id,
                context_id,
                types.TaskState.TASK_STATE_COMPLETED,
                response_text,
            )
        except Exception as exc:  # noqa: BLE001 - reflected to client
            logger.warning("a2a.server.handler_failed", error=str(exc))
            await _enqueue_status(
                event_queue,
                types,
                task_id,
                context_id,
                types.TaskState.TASK_STATE_FAILED,
                f"Handler error: {exc}",
            )

    async def cancel(self, context: Any, event_queue: Any) -> None:
        task_id = getattr(context, "task_id", None)
        if task_id:
            self._cancelled.add(task_id)


def _extract_mission_text(context: Any) -> str:
    message = getattr(context, "message", None)
    if message is None:
        return ""
    chunks: list[str] = []
    for part in getattr(message, "parts", []) or []:
        try:
            if part.HasField("text"):
                chunks.append(part.text)
        except (ValueError, AttributeError):
            continue
    return "\n".join(chunks)


async def _enqueue(event_queue: Any, event: Any) -> None:
    """Enqueue an event, awaiting if the queue uses an async interface.

    a2a-sdk evolved from sync to async event queues across patch versions;
    this helper accepts both.
    """
    result = event_queue.enqueue_event(event)
    if asyncio.iscoroutine(result):
        await result


async def _enqueue_status(
    event_queue: Any,
    types: Any,
    task_id: str,
    context_id: str,
    state: Any,
    text: str,
) -> None:
    from a2a.helpers import new_text_status_update_event  # type: ignore[import-not-found]

    await _enqueue(
        event_queue,
        new_text_status_update_event(
            task_id=task_id,
            context_id=context_id,
            state=state,
            text=text,
        ),
    )
