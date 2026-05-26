"""Protocol definitions for the A2A (Agent-to-Agent) protocol layer.

These protocols decouple the application/infrastructure wiring from any
concrete SDK (``a2a-sdk``). Implementations live in
``taskforce.infrastructure.a2a``.

Design parity with :mod:`taskforce.core.interfaces.acp` — each protocol
mirrors its ACP counterpart in structure but carries A2A-specific
semantics (task lifecycle, agent cards, artifacts, push notifications).
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any, Protocol

from taskforce.core.domain.a2a import (
    A2aAgentCard,
    A2aPeer,
    A2aPushConfig,
    A2aTaskHandle,
)


class A2aServerProtocol(Protocol):
    """Local A2A server exposing Taskforce agents to remote peers."""

    @property
    def is_running(self) -> bool:
        """Return ``True`` while the server accepts requests."""
        ...

    async def start(self) -> None:
        """Start the server (non-blocking)."""
        ...

    async def stop(self) -> None:
        """Stop the server and release resources."""
        ...

    def register_agent(
        self,
        card: A2aAgentCard,
        handler: Any,
    ) -> None:
        """Register an async handler for the local A2A agent.

        Args:
            card: AgentCard served at ``/.well-known/agent-card.json``.
            handler: ``AgentExecutor``-compatible callable matching the
                ``a2a-sdk`` server contract.
        """
        ...

    def registered_card(self) -> A2aAgentCard | None:
        """Return the AgentCard currently published, or ``None``."""
        ...


class A2aClientProtocol(Protocol):
    """Outbound A2A client for invoking remote agents."""

    async def fetch_agent_card(self, peer: A2aPeer) -> A2aAgentCard:
        """Retrieve and parse the peer's ``/.well-known/agent-card.json``."""
        ...

    async def run_sync(
        self,
        peer: A2aPeer,
        mission: str,
        *,
        session_id: str | None = None,
        metadata: dict[str, Any] | None = None,
        push: A2aPushConfig | None = None,
    ) -> A2aTaskHandle:
        """Run a remote agent task to completion and return the handle."""
        ...

    async def run_stream(
        self,
        peer: A2aPeer,
        mission: str,
        *,
        session_id: str | None = None,
        metadata: dict[str, Any] | None = None,
        push: A2aPushConfig | None = None,
    ) -> AsyncIterator[dict[str, Any]]:
        """Run a remote agent task and stream incremental events (SSE)."""
        ...

    async def get_task(self, peer: A2aPeer, task_id: str) -> A2aTaskHandle:
        """Fetch the current state of an existing task."""
        ...

    async def cancel_task(self, peer: A2aPeer, task_id: str) -> A2aTaskHandle:
        """Cancel an in-flight task."""
        ...

    async def resume_stream(
        self,
        peer: A2aPeer,
        task_id: str,
        *,
        reply: str | None = None,
    ) -> AsyncIterator[dict[str, Any]]:
        """Re-subscribe to an existing task stream; optionally provide a
        reply to satisfy an ``input-required`` state.
        """
        ...


class A2aPeerRegistryProtocol(Protocol):
    """Registry of configured A2A peers."""

    def get(self, name: str) -> A2aPeer | None: ...

    def list(self) -> list[A2aPeer]: ...

    def register(self, peer: A2aPeer) -> None: ...

    def remove(self, name: str) -> None: ...


class A2aRuntimeProtocol(Protocol):
    """Lifecycle facade for the embedded A2A server plus client pool."""

    @property
    def server(self) -> A2aServerProtocol: ...

    @property
    def client(self) -> A2aClientProtocol: ...

    @property
    def peers(self) -> A2aPeerRegistryProtocol: ...

    async def start(self) -> None: ...

    async def stop(self) -> None: ...

    async def call(
        self,
        peer_name: str,
        mission: str,
        *,
        session_id: str | None = None,
        stream: bool = False,
        tenant_id: str | None = None,
        push: A2aPushConfig | None = None,
    ) -> A2aTaskHandle:
        """High-level helper: resolve peer by name and run mission."""
        ...
