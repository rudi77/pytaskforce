"""API routes for external communication integrations."""

from __future__ import annotations

import os
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from taskforce.api.schemas.errors import ErrorResponse
from taskforce.application.communication_service import (
    CommunicationOptions,
    CommunicationService,
)
from taskforce.application.executor import AgentExecutor
from taskforce_extensions.infrastructure.communication import FileConversationStore

router = APIRouter(prefix="/integrations")

_ALLOWED_PROVIDERS = {"telegram", "teams"}

conversation_store = FileConversationStore(
    work_dir=os.getenv("TASKFORCE_WORK_DIR", ".taskforce")
)
executor = AgentExecutor()
service = CommunicationService(
    executor=executor,
    conversation_store=conversation_store,
)


class InboundMessageRequest(BaseModel):
    """Inbound message payload from an external provider."""

    conversation_id: str = Field(
        ...,
        description="Provider-specific conversation identifier.",
        examples=["telegram:123456", "teams:19:abc123"],
    )
    message: str = Field(
        ...,
        description="User message content.",
        examples=["Wie ist der Status?"],
    )
    profile: str = Field(
        default="dev",
        description="Agent profile for execution.",
        examples=["dev", "coding_agent"],
    )
    session_id: str | None = Field(
        default=None,
        description="Optional session ID override for this conversation.",
    )
    user_id: str | None = Field(
        default=None,
        description="User ID for RAG security filtering.",
    )
    org_id: str | None = Field(
        default=None,
        description="Organization ID for RAG security filtering.",
    )
    scope: str | None = Field(
        default=None,
        description="Access scope for RAG security filtering.",
    )
    agent_id: str | None = Field(
        default=None,
        description="Optional agent ID override.",
    )
    planning_strategy: str | None = Field(
        default=None,
        description="Optional planning strategy override.",
    )
    planning_strategy_params: dict[str, Any] | None = Field(
        default=None,
        description="Optional planning strategy parameters.",
    )
    plugin_path: str | None = Field(
        default=None,
        description="Optional plugin path for external agent tools.",
    )


class InboundMessageResponse(BaseModel):
    """Response payload for inbound communication handling."""

    session_id: str = Field(..., description="Resolved session identifier.")
    status: str = Field(..., description="Execution status.")
    reply: str = Field(..., description="Agent reply message.")
    history_length: int = Field(
        ...,
        description="Total number of history entries stored for this conversation.",
    )


def _build_user_context(request: InboundMessageRequest) -> dict[str, Any] | None:
    if not any([request.user_id, request.org_id, request.scope]):
        return None
    return {
        "user_id": request.user_id,
        "org_id": request.org_id,
        "scope": request.scope,
    }


@router.post(
    "/{provider}/messages",
    response_model=InboundMessageResponse,
    responses={
        400: {"model": ErrorResponse},
    },
)
async def handle_inbound_message(
    provider: str,
    request: InboundMessageRequest,
) -> InboundMessageResponse:
    """Handle inbound communication from Telegram/MS Teams."""
    if provider not in _ALLOWED_PROVIDERS:
        raise HTTPException(
            status_code=400,
            detail=ErrorResponse(
                code="invalid_request",
                message=f"Unsupported provider '{provider}'",
                details={"provider": provider},
                detail=f"Unsupported provider '{provider}'",
            ).model_dump(exclude_none=True),
            headers={"X-Taskforce-Error": "1"},
        )
    if not request.message.strip():
        raise HTTPException(
            status_code=400,
            detail=ErrorResponse(
                code="invalid_request",
                message="Message content must not be empty",
                details={"field": "message"},
                detail="Message content must not be empty",
            ).model_dump(exclude_none=True),
            headers={"X-Taskforce-Error": "1"},
        )
    response = await service.handle_message(
        provider=provider,
        conversation_id=request.conversation_id,
        message=request.message,
        options=CommunicationOptions(
            profile=request.profile,
            session_id=request.session_id,
            user_context=_build_user_context(request),
            agent_id=request.agent_id,
            planning_strategy=request.planning_strategy,
            planning_strategy_params=request.planning_strategy_params,
            plugin_path=request.plugin_path,
        ),
    )
    return InboundMessageResponse(
        session_id=response.session_id,
        status=response.status,
        reply=response.reply,
        history_length=len(response.history),
    )
