"""Protocol-agnostic descriptor for the unified remote-agent discovery layer.

Used by ``RemoteAgentDiscoveryService`` (application) to expose ACP and
A2A peers behind a single read-only view. The invocation paths
(``call_acp_agent`` vs ``call_a2a_agent``) stay protocol-specific because
A2A's task lifecycle (artifacts, push, ``input-required``) has no ACP
analogue.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class RemoteAgentProtocol(str, Enum):
    """Wire protocol behind a remote agent peer."""

    ACP = "acp"
    A2A = "a2a"


@dataclass(frozen=True)
class RemoteAgentDescriptor:
    """Unified view of a peer across ACP and A2A.

    Field semantics:
        agent: ACP agent name OR A2A AgentCard.name; ``None`` if the peer
            advertises no canonical name yet (e.g. discovery only by URL).
        capabilities: free-form labels — ACP carries agent descriptions,
            A2A carries skill ids.
        auth_schemes: declared auth schemes (``bearer``, ``oauth2``,
            ``oidc``, ``api_key``, ``mtls``, ``none``).
        reachable: best-effort health-check result; ``None`` when no
            probe has run.
        raw: protocol-specific original payload, kept for callers who
            need to drop down to the native model.
    """

    name: str
    protocol: RemoteAgentProtocol
    base_url: str
    agent: str | None
    description: str = ""
    capabilities: tuple[str, ...] = ()
    auth_schemes: tuple[str, ...] = ()
    reachable: bool | None = None
    latency_ms: int | None = None
    raw: dict[str, Any] = field(default_factory=dict)
