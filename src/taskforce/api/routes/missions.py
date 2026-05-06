"""Mission management routes.

Surfaces the running ``PersistentAgentService``'s queue so operators can
list queued/in-flight requests and cancel individual missions — both
queued (via :meth:`RequestQueue.cancel`) and in-flight (via cooperative
interrupt forwarded to :meth:`AgentExecutor.interrupt`).

The service is published into the API layer by an embedding host
(butler daemon, REST lifespan) via
:func:`taskforce.api.dependencies.set_persistent_agent_service`. When no
service is registered the routes return ``503 Service Unavailable`` so
clients can give a clear error message instead of a generic 500.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from taskforce.api.dependencies import get_persistent_agent_service

router = APIRouter()


class MissionRecord(BaseModel):
    """Snapshot of a single queued or in-flight request."""

    request_id: str
    session_id: str
    channel: str
    priority: int
    conversation_id: str | None = None
    status: str
    message_preview: str


class MissionListResponse(BaseModel):
    missions: list[MissionRecord]


class CancelResponse(BaseModel):
    request_id: str
    session_id: str | None = None
    status: str


def _require_service() -> Any:
    service = get_persistent_agent_service()
    if service is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=(
                "No PersistentAgentService is registered with this API "
                "process. Start the butler daemon or call "
                "`set_persistent_agent_service` from the embedding host."
            ),
        )
    return service


@router.get("/missions", response_model=MissionListResponse)
def list_missions(service=Depends(_require_service)) -> MissionListResponse:
    """Return every currently queued or in-flight mission."""
    return MissionListResponse(
        missions=[MissionRecord(**record) for record in service.list_missions()]
    )


@router.post(
    "/missions/{request_id}/cancel",
    response_model=CancelResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
def cancel_mission(
    request_id: str,
    service=Depends(_require_service),
) -> CancelResponse:
    """Cancel a queued or in-flight mission by ``request_id``.

    Returns ``status="cancelled"`` for queued items, ``"interrupt_requested"``
    for in-flight items, ``"not_found"`` (HTTP 404) when no such request
    exists.
    """
    result = service.cancel_request(request_id)
    if result["status"] == "not_found":
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No queued or in-flight request with id {request_id!r}",
        )
    return CancelResponse(**result)
