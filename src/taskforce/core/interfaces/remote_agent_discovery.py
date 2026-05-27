"""Protocol for the protocol-agnostic remote-agent discovery facade.

Implementation lives in
``taskforce.application.remote_agent_discovery_service.RemoteAgentDiscoveryService``.
"""

from __future__ import annotations

from typing import Protocol

from taskforce.core.domain.remote_agent import RemoteAgentDescriptor


class RemoteAgentDiscoveryProtocol(Protocol):
    """Enumerate and probe remote agents across both ACP and A2A."""

    def list_peers(self, *, probe: bool = False) -> list[RemoteAgentDescriptor]:
        """Return all configured ACP and A2A peers.

        Args:
            probe: When ``True``, perform a network round-trip per peer
                to populate ``reachable`` and ``latency_ms``. Off by
                default so listing stays fast.
        """
        ...

    async def discover(self, base_url: str) -> RemoteAgentDescriptor | None:
        """Probe ``base_url`` for an ACP or A2A endpoint.

        Tries ``/.well-known/agent-card.json`` first (A2A), then the ACP
        ``/agents`` route. Returns ``None`` if neither responds.
        """
        ...
