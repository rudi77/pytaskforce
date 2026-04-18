"""Embedded ACP server wrapping ``acp_sdk.server.Server``."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from typing import Any

import structlog

from taskforce.core.domain.acp import AcpAgentManifest
from taskforce.infrastructure.acp._sdk import load_server

logger = structlog.get_logger(__name__)

AgentHandler = Callable[[list[Any], Any], Awaitable[Any]]


class AcpServer:
    """Thin wrapper around ``acp_sdk.server.Server``.

    Handlers are registered via :meth:`register_agent` before ``start()``.
    The server runs inside an ``asyncio.Task`` so ``start()`` is
    non-blocking; ``stop()`` flips ``should_exit`` on the underlying
    uvicorn server and awaits the task.
    """

    def __init__(self, *, host: str = "0.0.0.0", port: int = 8800) -> None:
        self._host = host
        self._port = port
        self._server: Any | None = None
        self._task: asyncio.Task[Any] | None = None
        self._registered: dict[str, tuple[AcpAgentManifest, AgentHandler]] = {}
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

    def register_agent(self, manifest: AcpAgentManifest, handler: AgentHandler) -> None:
        if self._running:
            raise RuntimeError("Cannot register agents while ACP server is running; stop it first.")
        self._registered[manifest.name] = (manifest, handler)
        logger.debug("acp.server.agent_registered", agent=manifest.name)

    def registered_manifests(self) -> list[AcpAgentManifest]:
        return [m for m, _ in self._registered.values()]

    async def start(self) -> None:
        if self._running:
            return
        server_cls = load_server()
        server = server_cls()

        # acp-sdk registers agents via the ``@server.agent()`` decorator.
        for name, (manifest, handler) in self._registered.items():
            server.agent(name=name, description=manifest.description)(handler)

        self._server = server
        # ``Server.serve`` is the async entry point (uvicorn-based); it runs
        # until ``server.should_exit`` becomes ``True``.
        serve = server.serve
        self._task = asyncio.create_task(
            serve(host=self._host, port=self._port, log_level="warning")
        )
        self._running = True
        self._started.set()
        logger.info("acp.server.started", host=self._host, port=self._port)

    async def stop(self) -> None:
        if not self._running:
            return
        self._running = False
        server = self._server
        if server is not None:
            try:
                server.should_exit = True
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
        self._server = None
        self._started.clear()
        logger.info("acp.server.stopped")

    async def wait_started(self, timeout: float = 5.0) -> None:
        await asyncio.wait_for(self._started.wait(), timeout=timeout)
