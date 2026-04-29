"""Read/write API routes for the ACP peer registry.

Read endpoints surface ``.taskforce/acp_peers.json`` for operators and
the management UI. Write endpoints (POST/PUT/DELETE) and the test
endpoint were added in Phase 6 so peers can be managed without editing
JSON by hand.

The actual ACP protocol endpoints are still served by the embedded
``acp_sdk.server.Server`` on its own port (``acp.server.port``).
"""

from __future__ import annotations

import os
from typing import Any

from fastapi import APIRouter, Response, status
from pydantic import BaseModel, Field

from taskforce.api.errors import http_exception as _http_exception
from taskforce.application.acp_service import (
    delete_persisted_peer,
    get_persisted_peer,
    list_persisted_peers,
    ping_peer,
    upsert_persisted_peer,
)
from taskforce.application.config_schema import AcpPeerSchema
from taskforce.core.domain.acp import AcpPeer

router = APIRouter(prefix="/api/v1/acp", tags=["acp"])


def _work_dir() -> str:
    """Allow tests / deployments to redirect the registry via env."""
    return os.environ.get("TASKFORCE_ACP_WORK_DIR", ".taskforce")


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------


class AcpPeerResponse(BaseModel):
    name: str
    agent: str
    base_url: str
    description: str = ""
    auth_type: str = "none"
    token_env: str | None = None


class AcpPeerCreate(BaseModel):
    """Body for ``POST /acp/peers``."""

    name: str = Field(..., min_length=1, pattern="^[a-zA-Z0-9_:-]+$")
    base_url: str = Field(..., min_length=1)
    agent: str = Field(..., min_length=1)
    description: str = Field("", max_length=1024)
    auth: dict[str, Any] = Field(default_factory=lambda: {"type": "none"})

    def to_schema(self) -> AcpPeerSchema:
        return AcpPeerSchema(
            name=self.name,
            base_url=self.base_url,
            agent=self.agent,
            description=self.description,
            auth=self.auth,  # type: ignore[arg-type]
        )


class AcpPeerUpdate(BaseModel):
    """Body for ``PUT /acp/peers/{name}`` (name comes from the URL)."""

    base_url: str = Field(..., min_length=1)
    agent: str = Field(..., min_length=1)
    description: str = Field("", max_length=1024)
    auth: dict[str, Any] = Field(default_factory=lambda: {"type": "none"})


class AcpStatusResponse(BaseModel):
    configured_peers: int
    peers: list[AcpPeerResponse]


class AcpTestResult(BaseModel):
    ok: bool
    status_code: int | None = None
    latency_ms: int = 0
    agent: str | None = None
    base_url: str | None = None
    error: str | None = None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _peer_to_response(peer: AcpPeer) -> AcpPeerResponse:
    return AcpPeerResponse(
        name=peer.name,
        agent=peer.agent,
        base_url=peer.base_url,
        description=peer.description,
        auth_type=peer.auth.type.value,
        token_env=peer.auth.token_env,
    )


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.get("/peers", response_model=list[AcpPeerResponse])
def list_peers() -> list[AcpPeerResponse]:
    """List every peer persisted under ``acp_peers.json``."""
    return [_peer_to_response(p) for p in list_persisted_peers(work_dir=_work_dir())]


@router.get("/status", response_model=AcpStatusResponse)
def status_endpoint() -> AcpStatusResponse:
    peers = list_persisted_peers(work_dir=_work_dir())
    return AcpStatusResponse(
        configured_peers=len(peers),
        peers=[_peer_to_response(p) for p in peers],
    )


@router.post(
    "/peers",
    response_model=AcpPeerResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Register a new ACP peer",
)
def create_peer(payload: AcpPeerCreate) -> AcpPeerResponse:
    try:
        domain = upsert_persisted_peer(
            payload.to_schema(),
            work_dir=_work_dir(),
            overwrite=False,
        )
    except FileExistsError as exc:
        raise _http_exception(
            status_code=status.HTTP_409_CONFLICT,
            code="peer_exists",
            message=str(exc),
        ) from exc
    except (TypeError, ValueError) as exc:
        raise _http_exception(
            status_code=status.HTTP_400_BAD_REQUEST,
            code="peer_invalid",
            message=str(exc),
        ) from exc
    return _peer_to_response(domain)


@router.put(
    "/peers/{name}",
    response_model=AcpPeerResponse,
    summary="Replace an ACP peer (creates if missing)",
)
def update_peer(name: str, payload: AcpPeerUpdate) -> AcpPeerResponse:
    schema = AcpPeerSchema(
        name=name,
        base_url=payload.base_url,
        agent=payload.agent,
        description=payload.description,
        auth=payload.auth,  # type: ignore[arg-type]
    )
    try:
        domain = upsert_persisted_peer(schema, work_dir=_work_dir(), overwrite=True)
    except (TypeError, ValueError) as exc:
        raise _http_exception(
            status_code=status.HTTP_400_BAD_REQUEST,
            code="peer_invalid",
            message=str(exc),
        ) from exc
    return _peer_to_response(domain)


@router.delete(
    "/peers/{name}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Remove an ACP peer",
)
def delete_peer(name: str) -> Response:
    if not delete_persisted_peer(name, work_dir=_work_dir()):
        raise _http_exception(
            status_code=status.HTTP_404_NOT_FOUND,
            code="peer_not_found",
            message=f"ACP peer '{name}' not found",
        )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/peers/{name}/test",
    response_model=AcpTestResult,
    summary="Probe an ACP peer for connectivity",
)
async def test_peer(name: str) -> AcpTestResult:
    if get_persisted_peer(name, work_dir=_work_dir()) is None:
        raise _http_exception(
            status_code=status.HTTP_404_NOT_FOUND,
            code="peer_not_found",
            message=f"ACP peer '{name}' not found",
        )
    result = await ping_peer(name, work_dir=_work_dir())
    return AcpTestResult(**result)


def get_router() -> APIRouter:
    """Factory used by the server module to include the router."""
    return router


__all__: list[Any] = ["router", "get_router"]
