"""Protocol definitions for the ACP (Agent Communication Protocol) layer.

These protocols decouple the application/infrastructure wiring from any
concrete SDK (``acp-sdk``). Implementations live in
``taskforce.infrastructure.acp``.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any, Protocol

from taskforce.core.domain.acp import AcpAgentManifest, AcpPeer, AcpRunHandle


class AcpServerProtocol(Protocol):
    """Local ACP server exposing Taskforce agents to remote peers."""

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
        manifest: AcpAgentManifest,
        handler: Any,
    ) -> None:
        """Register an async handler for an ACP agent name.

        Args:
            manifest: Describes the agent (name, description, metadata).
            handler: Async callable matching ``acp_sdk`` server agent
                signature (``async def h(input, context)``).
        """
        ...


class AcpClientProtocol(Protocol):
    """Outbound ACP client for invoking remote agents."""

    async def run_sync(
        self,
        peer: AcpPeer,
        mission: str,
        *,
        session_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Run a remote agent synchronously and return the final payload."""
        ...

    async def run_stream(
        self,
        peer: AcpPeer,
        mission: str,
        *,
        session_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> AsyncIterator[dict[str, Any]]:
        """Run a remote agent and stream intermediate events."""
        ...

    async def list_agents(self, peer: AcpPeer) -> list[AcpAgentManifest]:
        """List agents advertised by the peer's ACP server."""
        ...


class AcpPeerRegistryProtocol(Protocol):
    """Registry of configured ACP peers."""

    def get(self, name: str) -> AcpPeer | None: ...

    def list(self) -> list[AcpPeer]: ...

    def register(self, peer: AcpPeer) -> None: ...

    def remove(self, name: str) -> None: ...


class AcpRuntimeProtocol(Protocol):
    """Lifecycle facade for the embedded ACP server plus client pool."""

    @property
    def server(self) -> AcpServerProtocol: ...

    @property
    def client(self) -> AcpClientProtocol: ...

    @property
    def peers(self) -> AcpPeerRegistryProtocol: ...

    async def start(self) -> None: ...

    async def stop(self) -> None: ...

    async def call(
        self,
        peer_name: str,
        mission: str,
        *,
        session_id: str | None = None,
        stream: bool = False,
    ) -> AcpRunHandle:
        """High-level helper: resolve peer by name and run mission."""
        ...
