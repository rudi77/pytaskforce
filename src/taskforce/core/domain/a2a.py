"""Domain models for A2A (Agent-to-Agent) protocol integration.

Value objects shared across the A2A infrastructure package. Pure dataclasses
with no dependency on the ``a2a-sdk`` package so the core layer stays
installable without the optional dependency.

The A2A protocol (Linux Foundation, spec v1.2) is richer than ACP: tasks
carry resumable streaming, ``input-required`` state, push-notification
webhooks and named artifacts. The dataclasses below mirror that surface
while keeping wire-format details inside the ``infrastructure/a2a/`` layer.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any

from taskforce.core.utils.time import utc_now as _utc_now


class A2aAuthType(str, Enum):
    """Supported A2A peer authentication schemes.

    Mirrors the security schemes declared in the AgentCard
    ``securitySchemes`` block.
    """

    NONE = "none"
    API_KEY = "api_key"
    BEARER = "bearer"
    OAUTH2 = "oauth2"
    OIDC = "oidc"
    MTLS = "mtls"


class A2aTransport(str, Enum):
    """A2A wire transports. Iteration 1 supports JSON-RPC + SSE; REST and
    gRPC are placeholders for follow-up work."""

    JSON_RPC = "json_rpc"
    REST = "rest"
    GRPC = "grpc"


class A2aTaskState(str, Enum):
    """A2A task lifecycle states from the spec.

    Note ``INPUT_REQUIRED`` — pytaskforce routes this through
    ``ChannelAskProtocol`` so the orchestrating agent can ask the user
    and then call ``tasks/resubscribe`` with the reply.
    """

    SUBMITTED = "submitted"
    WORKING = "working"
    INPUT_REQUIRED = "input-required"
    AUTH_REQUIRED = "auth-required"
    COMPLETED = "completed"
    CANCELED = "canceled"
    FAILED = "failed"
    REJECTED = "rejected"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class A2aAuth:
    """Authentication descriptor for an A2A peer.

    The ACP ``token_env`` + literal ``token`` pattern is preserved for
    bearer/API-key flows; OAuth2/OIDC adds ``provider`` (resolved through
    the existing ``AuthManager``) plus declared ``scopes`` so the client
    can request the right token up front.
    """

    type: A2aAuthType = A2aAuthType.NONE
    token_env: str | None = None
    token: str | None = None
    api_key_header: str | None = None
    provider: str | None = None
    scopes: tuple[str, ...] = ()
    client_id_env: str | None = None
    token_url: str | None = None
    cert_path: str | None = None
    key_path: str | None = None


@dataclass(frozen=True)
class A2aPushConfig:
    """Webhook push-notification configuration for an A2A task."""

    url: str
    token: str | None = None
    authentication_schemes: tuple[str, ...] = ()


@dataclass(frozen=True)
class A2aPeer:
    """A remote A2A endpoint reachable by this Taskforce instance.

    The ``agent_card_url`` defaults to ``{base_url}/.well-known/agent-card.json``
    (RFC 8615) but can be overridden when a peer ships its card under a
    non-standard path.
    """

    name: str
    base_url: str
    agent_card_url: str | None = None
    auth: A2aAuth = field(default_factory=A2aAuth)
    description: str = ""
    tenant_id: str = "default"
    allow_cross_tenant: bool = False
    preferred_transport: A2aTransport = A2aTransport.JSON_RPC
    poll_interval_seconds: int = 5

    def resolved_card_url(self) -> str:
        if self.agent_card_url:
            return self.agent_card_url
        return f"{self.base_url.rstrip('/')}/.well-known/agent-card.json"


@dataclass(frozen=True)
class A2aSkill:
    """Skill entry from an AgentCard.

    Skills are the closest A2A analogue to ACP's per-agent manifests:
    each declares a name, description and the input/output modalities
    it supports.
    """

    id: str
    name: str
    description: str = ""
    tags: tuple[str, ...] = ()
    input_modes: tuple[str, ...] = ()
    output_modes: tuple[str, ...] = ()


@dataclass(frozen=True)
class A2aAgentCard:
    """Parsed AgentCard served at /.well-known/agent-card.json.

    The full upstream model carries dozens of optional fields; only those
    actually consumed by pytaskforce surface here. Original payload is
    retained in ``raw`` for forward-compatibility.
    """

    name: str
    description: str
    version: str
    url: str
    skills: tuple[A2aSkill, ...] = ()
    transports: tuple[A2aTransport, ...] = (A2aTransport.JSON_RPC,)
    capabilities: dict[str, bool] = field(default_factory=dict)
    security_schemes: dict[str, dict[str, Any]] = field(default_factory=dict)
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class A2aArtifact:
    """Named output artifact returned by an A2A task.

    Persisted under ``<work_dir>/a2a_artifacts/<task_id>/<name>`` by the
    client. The dataclass carries only metadata so we never pull the
    blob into the LLM context (ADR-025 isolation policy).
    """

    name: str
    mime_type: str
    path: str
    size: int = 0
    description: str = ""


@dataclass(frozen=True)
class A2aTaskHandle:
    """Handle for an in-flight or completed A2A task."""

    task_id: str
    peer: str
    state: A2aTaskState
    started_at: datetime = field(default_factory=_utc_now)
    output_text: str = ""
    artifacts: tuple[A2aArtifact, ...] = ()
    history: tuple[dict[str, Any], ...] = ()
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class A2aInvocation:
    """Normalised payload for invoking a remote A2A agent.

    Mirrors :class:`AcpInvocation` so the orchestration tools (``call_a2a_agent``,
    later possibly a unified router) work off a consistent shape.
    """

    peer: str
    mission: str
    session_id: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    stream: bool = False
    push: A2aPushConfig | None = None
