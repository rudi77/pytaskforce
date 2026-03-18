"""Session management API routes.

.. deprecated::
    Session endpoints are deprecated in favour of the Conversation API
    (ADR-016). Use ``/api/v1/conversations`` instead. These endpoints will
    be removed in a future major release.
"""

import uuid
from datetime import datetime

import structlog
from fastapi import APIRouter, Depends, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from taskforce.api.dependencies import get_factory
from taskforce.api.errors import http_exception as _http_exception

logger = structlog.get_logger(__name__)

_DEPRECATION_NOTICE = (
    "This endpoint is deprecated. Use /api/v1/conversations instead (ADR-016)."
)

router = APIRouter()


def _add_deprecation_headers(response: JSONResponse) -> None:
    """Inject standard deprecation headers into a response."""
    response.headers["Deprecation"] = "true"
    response.headers["Sunset"] = "2026-12-31"
    response.headers["Link"] = '</api/v1/conversations>; rel="successor-version"'


class SessionResponse(BaseModel):
    session_id: str
    mission: str
    status: str
    created_at: str


@router.get("/sessions", response_model=list[SessionResponse], deprecated=True)
async def list_sessions(
    profile: str = Query(
        ...,
        description="Profile name (e.g., coding_agent, devops_agent, rag_agent)",
    ),
    factory=Depends(get_factory),
):
    """List all agent sessions.

    .. deprecated::
        Use ``GET /api/v1/conversations`` instead.
    """
    logger.warning("api.sessions.deprecated", endpoint="GET /sessions", notice=_DEPRECATION_NOTICE)
    try:
        agent = await factory.create_agent(profile=profile)
    except FileNotFoundError as e:
        raise _http_exception(
            status_code=404,
            code="profile_not_found",
            message=f"Profile not found: {profile}",
            details={"profile": profile},
        ) from e

    try:
        sessions = await agent.state_manager.list_sessions()

        # Load details for each session
        results = []
        for session_id in sessions:
            state = await agent.state_manager.load_state(session_id)
            if state:
                results.append(
                    SessionResponse(
                        session_id=session_id,
                        mission=state.get("mission", ""),
                        status=state.get("status", "unknown"),
                        created_at=state.get("created_at", ""),
                    )
                )

        response = JSONResponse(content=[r.model_dump() for r in results])
        _add_deprecation_headers(response)
        return response
    finally:
        await agent.close()


@router.get("/sessions/{session_id}", response_model=SessionResponse, deprecated=True)
async def get_session(
    session_id: str,
    profile: str = Query(
        ...,
        description="Profile name (e.g., coding_agent, devops_agent, rag_agent)",
    ),
    factory=Depends(get_factory),
):
    """Get session details.

    .. deprecated::
        Use ``GET /api/v1/conversations/{conversation_id}/messages`` instead.
    """
    logger.warning(
        "api.sessions.deprecated",
        endpoint="GET /sessions/{session_id}",
        notice=_DEPRECATION_NOTICE,
    )
    try:
        agent = await factory.create_agent(profile=profile)
    except FileNotFoundError as e:
        raise _http_exception(
            status_code=404,
            code="profile_not_found",
            message=f"Profile not found: {profile}",
            details={"profile": profile},
        ) from e

    try:
        state = await agent.state_manager.load_state(session_id)

        if not state:
            raise _http_exception(
                status_code=404,
                code="session_not_found",
                message=f"Session '{session_id}' not found",
                details={"session_id": session_id},
            )

        data = SessionResponse(
            session_id=session_id,
            mission=state.get("mission", ""),
            status=state.get("status", ""),
            created_at=state.get("created_at", ""),
        )
        response = JSONResponse(content=data.model_dump())
        _add_deprecation_headers(response)
        return response
    finally:
        await agent.close()


@router.post("/sessions", response_model=SessionResponse, deprecated=True)
async def create_session(
    profile: str = Query(
        ...,
        description="Profile name (e.g., coding_agent, devops_agent, rag_agent)",
    ),
    mission: str = "",
    factory=Depends(get_factory),
):
    """Create a new session.

    .. deprecated::
        Use ``POST /api/v1/conversations`` instead.
    """
    logger.warning("api.sessions.deprecated", endpoint="POST /sessions", notice=_DEPRECATION_NOTICE)
    try:
        agent = await factory.create_agent(profile=profile)
    except FileNotFoundError as e:
        raise _http_exception(
            status_code=404,
            code="profile_not_found",
            message=f"Profile not found: {profile}",
            details={"profile": profile},
        ) from e

    try:
        session_id = str(uuid.uuid4())
        initial_state = {
            "mission": mission,
            "status": "created",
            "created_at": datetime.now().isoformat(),
        }
        await agent.state_manager.save_state(session_id, initial_state)

        data = SessionResponse(
            session_id=session_id,
            mission=mission,
            status="created",
            created_at=initial_state["created_at"],
        )
        response = JSONResponse(content=data.model_dump())
        _add_deprecation_headers(response)
        return response
    finally:
        await agent.close()

