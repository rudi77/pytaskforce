"""Read-only API routes for inspecting ACP state.

The actual ACP protocol endpoints are served by the embedded
``acp_sdk.server.Server`` on its own port (``acp.server.port``). These routes
expose metadata for operators and dashboards.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel

from taskforce.application.acp_service import list_persisted_peers
from taskforce.core.domain.acp import AcpPeer

router = APIRouter(prefix="/api/v1/acp", tags=["acp"])


class AcpPeerResponse(BaseModel):
    name: str
    agent: str
    base_url: str
    description: str = ""
    auth_type: str = "none"


class AcpStatusResponse(BaseModel):
    configured_peers: int
    peers: list[AcpPeerResponse]


def _peer_to_response(peer: AcpPeer) -> AcpPeerResponse:
    return AcpPeerResponse(
        name=peer.name,
        agent=peer.agent,
        base_url=peer.base_url,
        description=peer.description,
        auth_type=peer.auth.type.value,
    )


@router.get("/peers", response_model=list[AcpPeerResponse])
async def list_peers() -> list[AcpPeerResponse]:
    """List all peers registered in ``.taskforce/acp_peers.json``."""
    return [_peer_to_response(p) for p in list_persisted_peers()]


@router.get("/status", response_model=AcpStatusResponse)
async def status() -> AcpStatusResponse:
    """Return a snapshot of the on-disk ACP registry."""
    peers = list_persisted_peers()
    return AcpStatusResponse(
        configured_peers=len(peers),
        peers=[_peer_to_response(p) for p in peers],
    )


def get_router() -> APIRouter:
    """Factory used by the server module to include the router."""
    return router


__all__: list[Any] = ["router", "get_router"]
