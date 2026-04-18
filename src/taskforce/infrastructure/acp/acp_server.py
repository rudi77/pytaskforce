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

    Handlers are registered *before* ``start()`` via :meth:`register_agent`.
    The server runs inside an asyncio task so it does not block the caller.
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

        # acp-sdk uses ``@server.agent()`` decorator to register agents.
        for name, (manifest, handler) in self._registered.items():
            server.agent(name=name, description=manifest.description)(handler)

        self._server = server
        # ``Server.run_async`` is provided by acp-sdk; fall back to a thread
        # pool executor wrapping the sync ``run()`` if unavailable.
        run_async = getattr(server, "run_async", None)
        if run_async is None:
            loop = asyncio.get_running_loop()
            self._task = loop.create_task(
                loop.run_in_executor(None, lambda: server.run(host=self._host, port=self._port))
            )
        else:
            self._task = asyncio.create_task(run_async(host=self._host, port=self._port))
        self._running = True
        self._started.set()
        logger.info("acp.server.started", host=self._host, port=self._port)

    async def stop(self) -> None:
        if not self._running:
            return
        self._running = False
        server = self._server
        if server is not None:
            shutdown = getattr(server, "shutdown", None)
            if shutdown is not None:
                result = shutdown()
                if asyncio.iscoroutine(result):
                    await result
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except (asyncio.CancelledError, Exception):
                pass
            self._task = None
        self._server = None
        self._started.clear()
        logger.info("acp.server.stopped")

    async def wait_started(self, timeout: float = 5.0) -> None:
        await asyncio.wait_for(self._started.wait(), timeout=timeout)
