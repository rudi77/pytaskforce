"""Domain models for ACP (Agent Communication Protocol) integration.

Value objects shared across the ACP infrastructure package. These types are
pure dataclasses with no dependency on the ``acp-sdk`` package so the core
layer stays installable without the optional dependency.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any

from taskforce.core.utils.time import utc_now as _utc_now


class AcpAuthType(str, Enum):
    """Supported ACP peer authentication schemes."""

    NONE = "none"
    BEARER = "bearer"
    MTLS = "mtls"


@dataclass(frozen=True)
class AcpAuth:
    """Authentication descriptor for an ACP peer."""

    type: AcpAuthType = AcpAuthType.NONE
    token_env: str | None = None
    token: str | None = None
    cert_path: str | None = None
    key_path: str | None = None


@dataclass(frozen=True)
class AcpPeer:
    """A remote ACP endpoint reachable by this Taskforce instance."""

    name: str
    base_url: str
    agent: str
    auth: AcpAuth = field(default_factory=AcpAuth)
    description: str = ""
    tenant_id: str = "default"
    allow_cross_tenant: bool = False


@dataclass(frozen=True)
class AcpAgentManifest:
    """Describes a locally hosted ACP agent exposed to peers."""

    name: str
    description: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class AcpRunHandle:
    """Handle for an in-flight or completed ACP run."""

    run_id: str
    agent: str
    peer: str
    status: str
    started_at: datetime = field(default_factory=_utc_now)
    result: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class AcpInvocation:
    """Normalised payload for calling a remote ACP agent.

    Used by ``AcpAgentTool`` and ``AcpMessageBus`` to hand off a mission to
    the client layer without leaking ``acp_sdk`` types into the application
    layer.
    """

    peer: str
    agent: str
    mission: str
    session_id: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    stream: bool = False
