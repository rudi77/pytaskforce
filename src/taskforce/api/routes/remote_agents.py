"""Cross-protocol remote-agent discovery routes.

Read-only view that unifies ACP + A2A peers behind one REST surface.
Invocation paths stay protocol-specific (``/api/v1/acp/...`` vs
``/api/v1/a2a/...``); this surface only discovers and lists.
"""

from __future__ import annotations

import os
from typing import Any

from fastapi import APIRouter, status
from pydantic import BaseModel, Field

from taskforce.api.errors import http_exception as _http_exception
from taskforce.application.remote_agent_discovery_service import (
    RemoteAgentDiscoveryService,
)
from taskforce.core.domain.remote_agent import RemoteAgentDescriptor

router = APIRouter(prefix="/api/v1/remote-agents", tags=["remote-agents"])


def _work_dir() -> str:
    return os.environ.get("TASKFORCE_REMOTE_AGENTS_WORK_DIR", ".taskforce")


class RemoteAgentEntry(BaseModel):
    name: str
    protocol: str
    base_url: str
    agent: str | None = None
    description: str = ""
    capabilities: list[str] = Field(default_factory=list)
    auth_schemes: list[str] = Field(default_factory=list)
    reachable: bool | None = None
    latency_ms: int | None = None


class RemoteAgentDiscoverRequest(BaseModel):
    base_url: str = Field(..., min_length=1)


def _to_entry(d: RemoteAgentDescriptor) -> RemoteAgentEntry:
    return RemoteAgentEntry(
        name=d.name,
        protocol=d.protocol.value,
        base_url=d.base_url,
        agent=d.agent,
        description=d.description,
        capabilities=list(d.capabilities),
        auth_schemes=list(d.auth_schemes),
        reachable=d.reachable,
        latency_ms=d.latency_ms,
    )


@router.get("", response_model=list[RemoteAgentEntry])
async def list_remote_agents(probe: bool = False) -> list[RemoteAgentEntry]:
    """List ACP + A2A peers in a unified view.

    Pass ``?probe=true`` to network-check each peer (slower; populates
    ``reachable`` + ``latency_ms``).
    """
    service = RemoteAgentDiscoveryService(work_dir=_work_dir())
    descriptors = await service.list_peers_async(probe=probe)
    return [_to_entry(d) for d in descriptors]


@router.post(
    "/discover",
    response_model=RemoteAgentEntry,
    summary="Probe a URL for an ACP or A2A endpoint",
)
async def discover_endpoint(payload: RemoteAgentDiscoverRequest) -> RemoteAgentEntry:
    """Probe a URL — tries A2A's ``/.well-known/agent-card.json`` first,
    then ACP's ``/agents`` listing.
    """
    service = RemoteAgentDiscoveryService(work_dir=_work_dir())
    result = await service.discover(payload.base_url)
    if result is None:
        raise _http_exception(
            status_code=status.HTTP_404_NOT_FOUND,
            code="no_endpoint",
            message=f"No ACP or A2A endpoint reachable at {payload.base_url!r}",
        )
    return _to_entry(result)


def get_router() -> APIRouter:
    return router


__all__: list[Any] = ["router", "get_router"]
