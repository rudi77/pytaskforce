"""Read/write API routes for the A2A peer registry + push webhooks.

Operators manage A2A peers through these REST endpoints; the actual
A2A protocol traffic is served by the embedded server (started via
``taskforce a2a start``) on its own port (``a2a.server.port``).
"""

from __future__ import annotations

import os
from typing import Any

from fastapi import APIRouter, Request, Response, status
from pydantic import BaseModel, Field

from taskforce.api.errors import http_exception as _http_exception
from taskforce.application.a2a_service import (
    delete_persisted_peer,
    get_persisted_peer,
    list_persisted_peers,
    ping_peer,
    upsert_persisted_peer,
)
from taskforce.application.config_schema import A2aPeerSchema
from taskforce.core.domain.a2a import A2aPeer

router = APIRouter(prefix="/api/v1/a2a", tags=["a2a"])


def _work_dir() -> str:
    return os.environ.get("TASKFORCE_A2A_WORK_DIR", ".taskforce")


_push_handler = None


def _get_push_handler() -> Any:
    """Return the module-level push notification handler, creating once."""
    global _push_handler
    if _push_handler is None:
        from taskforce.infrastructure.a2a.push_notification_handler import (
            PushNotificationHandler,
        )

        _push_handler = PushNotificationHandler()
    return _push_handler


class A2aPeerResponse(BaseModel):
    name: str
    base_url: str
    agent_card_url: str | None = None
    description: str = ""
    auth_type: str = "none"
    token_env: str | None = None
    provider: str | None = None
    scopes: list[str] = Field(default_factory=list)
    preferred_transport: str = "json_rpc"


class A2aPeerCreate(BaseModel):
    """Body for ``POST /a2a/peers``."""

    name: str = Field(..., min_length=1, pattern="^[a-zA-Z0-9_:-]+$")
    base_url: str = Field(..., min_length=1)
    agent_card_url: str | None = None
    description: str = Field("", max_length=1024)
    preferred_transport: str = "json_rpc"
    auth: dict[str, Any] = Field(default_factory=lambda: {"type": "none"})

    def to_schema(self) -> A2aPeerSchema:
        return A2aPeerSchema(
            name=self.name,
            base_url=self.base_url,
            agent_card_url=self.agent_card_url,
            description=self.description,
            preferred_transport=self.preferred_transport,
            auth=self.auth,  # type: ignore[arg-type]
        )


class A2aPeerUpdate(BaseModel):
    """Body for ``PUT /a2a/peers/{name}``."""

    base_url: str = Field(..., min_length=1)
    agent_card_url: str | None = None
    description: str = Field("", max_length=1024)
    preferred_transport: str = "json_rpc"
    auth: dict[str, Any] = Field(default_factory=lambda: {"type": "none"})


class A2aStatusResponse(BaseModel):
    configured_peers: int
    peers: list[A2aPeerResponse]


class A2aTestResult(BaseModel):
    ok: bool
    agent: str | None = None
    version: str | None = None
    base_url: str | None = None
    skills: list[str] = Field(default_factory=list)
    latency_ms: int = 0
    error: str | None = None


def _peer_to_response(peer: A2aPeer) -> A2aPeerResponse:
    return A2aPeerResponse(
        name=peer.name,
        base_url=peer.base_url,
        agent_card_url=peer.agent_card_url,
        description=peer.description,
        auth_type=peer.auth.type.value,
        token_env=peer.auth.token_env,
        provider=peer.auth.provider,
        scopes=list(peer.auth.scopes),
        preferred_transport=peer.preferred_transport.value,
    )


@router.get("/peers", response_model=list[A2aPeerResponse])
def list_peers_route() -> list[A2aPeerResponse]:
    """List every peer persisted under ``a2a_peers.json``."""
    return [_peer_to_response(p) for p in list_persisted_peers(work_dir=_work_dir())]


@router.get("/status", response_model=A2aStatusResponse)
def status_endpoint() -> A2aStatusResponse:
    peers = list_persisted_peers(work_dir=_work_dir())
    return A2aStatusResponse(
        configured_peers=len(peers),
        peers=[_peer_to_response(p) for p in peers],
    )


@router.post(
    "/peers",
    response_model=A2aPeerResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Register a new A2A peer",
)
def create_peer(payload: A2aPeerCreate) -> A2aPeerResponse:
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
    response_model=A2aPeerResponse,
    summary="Replace an A2A peer (creates if missing)",
)
def update_peer(name: str, payload: A2aPeerUpdate) -> A2aPeerResponse:
    schema = A2aPeerSchema(
        name=name,
        base_url=payload.base_url,
        agent_card_url=payload.agent_card_url,
        description=payload.description,
        preferred_transport=payload.preferred_transport,
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
    summary="Remove an A2A peer",
)
def delete_peer(name: str) -> Response:
    if not delete_persisted_peer(name, work_dir=_work_dir()):
        raise _http_exception(
            status_code=status.HTTP_404_NOT_FOUND,
            code="peer_not_found",
            message=f"A2A peer '{name}' not found",
        )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/peers/{name}/test",
    response_model=A2aTestResult,
    summary="Probe an A2A peer via its AgentCard",
)
async def test_peer(name: str) -> A2aTestResult:
    if get_persisted_peer(name, work_dir=_work_dir()) is None:
        raise _http_exception(
            status_code=status.HTTP_404_NOT_FOUND,
            code="peer_not_found",
            message=f"A2A peer '{name}' not found",
        )
    result = await ping_peer(name, work_dir=_work_dir())
    return A2aTestResult(**result)


@router.post(
    "/webhooks/{task_id}",
    status_code=status.HTTP_202_ACCEPTED,
    summary="Inbound A2A push notification — dispatched to a waiting client",
)
async def push_webhook(task_id: str, request: Request) -> dict[str, Any]:
    """Receive a push notification from a remote A2A peer.

    Bodies are forwarded to any client coroutine currently waiting for
    ``task_id`` via :class:`PushNotificationHandler`. When no client
    has registered, the call returns ``{"dispatched": false}`` so the
    remote peer learns it can retry / abort.
    """
    try:
        payload = await request.json()
    except Exception as exc:  # noqa: BLE001 - reject non-JSON bodies cleanly
        raise _http_exception(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            code="invalid_body",
            message="A2A webhook body must be JSON",
        ) from exc
    handler = _get_push_handler()
    dispatched = await handler.dispatch(task_id, payload if isinstance(payload, dict) else {})
    return {"dispatched": dispatched, "task_id": task_id}


def get_router() -> APIRouter:
    return router


__all__: list[Any] = ["router", "get_router"]
