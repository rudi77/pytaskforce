"""Conversation Management API routes (ADR-016).

Provides REST endpoints for managing persistent agent conversations:

- ``POST /conversations``            -- create a new conversation
- ``GET  /conversations``            -- list active conversations
- ``GET  /conversations/archived``   -- list archived conversations
- ``GET  /conversations/{id}/messages`` -- get messages for a conversation
- ``POST /conversations/{id}/messages`` -- append a message (and run agent)
- ``POST /conversations/{id}/archive`` -- archive a conversation
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field

from taskforce.api.dependencies import get_conversation_manager, get_executor
from taskforce.api.errors import http_exception as _error_response
from taskforce.api.schemas.errors import ErrorResponse

router = APIRouter(prefix="/conversations", tags=["conversations"])


# ------------------------------------------------------------------
# Schemas
# ------------------------------------------------------------------


class CreateConversationRequest(BaseModel):
    """Request to start a new conversation."""

    channel: str = Field(default="rest", description="Channel identifier.")
    sender_id: str | None = Field(default=None, description="Sender identifier.")


class ConversationInfoResponse(BaseModel):
    """Active conversation metadata."""

    conversation_id: str
    channel: str
    started_at: datetime
    last_activity: datetime
    message_count: int
    topic: str | None = None


class ConversationSummaryResponse(BaseModel):
    """Archived conversation summary."""

    conversation_id: str
    topic: str
    summary: str
    started_at: datetime
    archived_at: datetime
    message_count: int


class AppendMessageRequest(BaseModel):
    """Message to send to the agent within a conversation."""

    message: str = Field(..., max_length=32_000, description="User message content.")
    profile: str = Field(default="butler", description="Agent profile.")


class AppendMessageResponse(BaseModel):
    """Response from the agent after processing a message."""

    conversation_id: str
    reply: str
    status: str
    message_count: int


class ArchiveRequest(BaseModel):
    """Optional summary when archiving a conversation."""

    summary: str | None = Field(default=None, description="Optional summary.")


class MessageResponse(BaseModel):
    """A single message in the conversation."""

    role: str
    content: str


# ------------------------------------------------------------------
# Endpoints
# ------------------------------------------------------------------


@router.post(
    "",
    response_model=ConversationInfoResponse,
    status_code=201,
)
async def create_conversation(
    request: CreateConversationRequest,
    manager=Depends(get_conversation_manager),
) -> ConversationInfoResponse:
    """Create a new conversation, archiving any existing active one for the channel."""
    conv_id = await manager.create_new(request.channel, request.sender_id)
    active = await manager.list_active()
    info = next((c for c in active if c.conversation_id == conv_id), None)
    if not info:
        raise _error_response(
            status_code=500,
            code="internal_error",
            message="Conversation created but not found in active list",
            details={"conversation_id": conv_id},
        )
    return ConversationInfoResponse(
        conversation_id=info.conversation_id,
        channel=info.channel,
        started_at=info.started_at,
        last_activity=info.last_activity,
        message_count=info.message_count,
        topic=info.topic,
    )


@router.get(
    "",
    response_model=list[ConversationInfoResponse],
)
async def list_active_conversations(
    manager=Depends(get_conversation_manager),
) -> list[ConversationInfoResponse]:
    """List all active (non-archived) conversations."""
    active = await manager.list_active()
    return [
        ConversationInfoResponse(
            conversation_id=c.conversation_id,
            channel=c.channel,
            started_at=c.started_at,
            last_activity=c.last_activity,
            message_count=c.message_count,
            topic=c.topic,
        )
        for c in active
    ]


@router.get(
    "/archived",
    response_model=list[ConversationSummaryResponse],
)
async def list_archived_conversations(
    limit: int = Query(default=20, ge=1, le=100),
    manager=Depends(get_conversation_manager),
) -> list[ConversationSummaryResponse]:
    """List archived conversations."""
    archived = await manager.list_archived(limit)
    return [
        ConversationSummaryResponse(
            conversation_id=c.conversation_id,
            topic=c.topic,
            summary=c.summary,
            started_at=c.started_at,
            archived_at=c.archived_at,
            message_count=c.message_count,
        )
        for c in archived
    ]


@router.get(
    "/{conversation_id}/messages",
    response_model=list[MessageResponse],
)
async def get_messages(
    conversation_id: str,
    limit: int | None = Query(default=None, ge=1),
    manager=Depends(get_conversation_manager),
) -> list[MessageResponse]:
    """Get messages for a conversation."""
    messages = await manager.get_messages(conversation_id, limit)
    return [MessageResponse(role=m.get("role", ""), content=m.get("content", "")) for m in messages]


@router.post(
    "/{conversation_id}/messages",
    response_model=AppendMessageResponse,
    responses={400: {"model": ErrorResponse}},
)
async def append_message(
    conversation_id: str,
    request: AppendMessageRequest,
    manager=Depends(get_conversation_manager),
    executor=Depends(get_executor),
) -> AppendMessageResponse:
    """Send a message to the agent within a conversation.

    Appends the user message, runs the agent, and appends the reply.
    """
    if not request.message.strip():
        raise _error_response(
            status_code=400,
            code="invalid_request",
            message="Message content must not be empty",
            details={"field": "message"},
        )

    # Append user message.
    await manager.append_message(
        conversation_id,
        {"role": "user", "content": request.message},
    )

    # Load full history for the agent.
    history = await manager.get_messages(conversation_id)

    # Execute agent with conversation history.
    result = await executor.execute_mission(
        mission=request.message,
        profile=request.profile,
        conversation_history=history,
    )

    # Append assistant reply.
    await manager.append_message(
        conversation_id,
        {"role": "assistant", "content": result.final_message},
    )

    messages = await manager.get_messages(conversation_id)
    return AppendMessageResponse(
        conversation_id=conversation_id,
        reply=result.final_message,
        status=result.status_value,
        message_count=len(messages),
    )


@router.post(
    "/{conversation_id}/archive",
    status_code=204,
)
async def archive_conversation(
    conversation_id: str,
    request: ArchiveRequest | None = None,
    manager=Depends(get_conversation_manager),
) -> None:
    """Archive a conversation with an optional summary."""
    summary = request.summary if request else None
    await manager.archive(conversation_id, summary)
