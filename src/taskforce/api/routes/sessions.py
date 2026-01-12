import uuid
from datetime import datetime
from typing import Any, List

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from taskforce.api.schemas.errors import ErrorResponse
from taskforce.application.factory import AgentFactory

router = APIRouter()
factory = AgentFactory()


def _http_exception(
    status_code: int, code: str, message: str, details: dict[str, Any] | None = None
) -> HTTPException:
    """Build standardized HTTPException with ErrorResponse payload."""
    return HTTPException(
        status_code=status_code,
        detail=ErrorResponse(
            code=code, message=message, details=details, detail=message
        ).model_dump(exclude_none=True),
        headers={"X-Taskforce-Error": "1"},
    )


class SessionResponse(BaseModel):
    session_id: str
    mission: str
    status: str
    created_at: str


@router.get("/sessions", response_model=List[SessionResponse])
async def list_sessions(
    profile: str = Query(
        ...,
        description="Profile name (e.g., coding_agent, devops_agent, rag_agent)",
    )
):
    """List all agent sessions."""
    try:
        agent = await factory.create_agent(profile=profile)
    except FileNotFoundError:
        raise _http_exception(
            404,
            "profile_not_found",
            f"Profile not found: {profile}",
            {"profile": profile},
        )

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

        return results
    finally:
        await agent.close()


@router.get("/sessions/{session_id}", response_model=SessionResponse)
async def get_session(
    session_id: str,
    profile: str = Query(
        ...,
        description="Profile name (e.g., coding_agent, devops_agent, rag_agent)",
    ),
):
    """Get session details."""
    try:
        agent = await factory.create_agent(profile=profile)
    except FileNotFoundError:
        raise _http_exception(
            404,
            "profile_not_found",
            f"Profile not found: {profile}",
            {"profile": profile},
        )

    try:
        state = await agent.state_manager.load_state(session_id)

        if not state:
            raise HTTPException(status_code=404, detail="Session not found")

        return SessionResponse(
            session_id=session_id,
            mission=state.get("mission", ""),
            status=state.get("status", ""),
            created_at=state.get("created_at", ""),
        )
    finally:
        await agent.close()


@router.post("/sessions", response_model=SessionResponse)
async def create_session(
    profile: str = Query(
        ...,
        description="Profile name (e.g., coding_agent, devops_agent, rag_agent)",
    ),
    mission: str = "",
):
    """Create a new session."""
    try:
        agent = await factory.create_agent(profile=profile)
    except FileNotFoundError:
        raise _http_exception(
            404,
            "profile_not_found",
            f"Profile not found: {profile}",
            {"profile": profile},
        )

    try:
        session_id = str(uuid.uuid4())
        initial_state = {
            "mission": mission,
            "status": "created",
            "created_at": datetime.now().isoformat(),
        }
        await agent.state_manager.save_state(session_id, initial_state)

        return SessionResponse(
            session_id=session_id,
            mission=mission,
            status="created",
            created_at=initial_state["created_at"],
        )
    finally:
        await agent.close()

