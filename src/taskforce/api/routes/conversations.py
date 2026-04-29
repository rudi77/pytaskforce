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

import asyncio
import json
from dataclasses import asdict
from datetime import datetime
from typing import Any, AsyncIterator

import structlog
from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from taskforce.api.dependencies import get_conversation_manager, get_executor
from taskforce.api.errors import http_exception as _error_response
from taskforce.api.schemas.errors import ErrorResponse
from taskforce.application.file_storage import (
    FileNotFound as _FileNotFound,
    get_file_storage,
)
from taskforce.core.domain.enums import EventType

_chat_logger = structlog.get_logger("taskforce.api.routes.conversations")

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


class AttachmentRef(BaseModel):
    """Reference to a previously uploaded file (see /api/v1/files)."""

    file_id: str = Field(..., min_length=1)


class AppendMessageRequest(BaseModel):
    """Message to send to the agent within a conversation."""

    message: str = Field(..., max_length=32_000, description="User message content.")
    profile: str = Field(default="butler", description="Agent profile.")
    attachments: list[AttachmentRef] = Field(
        default_factory=list,
        description="File ids of previously uploaded attachments (POST /api/v1/files).",
    )


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
    attachments: list[dict[str, Any]] = Field(default_factory=list)


def _resolve_attachments(refs: list[AttachmentRef]) -> list[dict[str, Any]]:
    """Resolve attachment refs to lightweight metadata dicts."""
    if not refs:
        return []
    storage = get_file_storage()
    out: list[dict[str, Any]] = []
    for ref in refs:
        try:
            meta = storage.get_metadata(ref.file_id)
        except _FileNotFound as exc:
            raise _error_response(
                status_code=400,
                code="attachment_not_found",
                message=str(exc),
                details={"file_id": ref.file_id},
            ) from exc
        out.append(
            {
                "file_id": meta.file_id,
                "name": meta.name,
                "mime": meta.mime,
                "size": meta.size,
            }
        )
    return out


def _build_attachments_prefix(attachments: list[dict[str, Any]]) -> str:
    """Render an attachment summary the agent can read."""
    if not attachments:
        return ""
    storage = get_file_storage()
    lines = ["[Attachments]"]
    for att in attachments:
        path = storage._blob_path(att["file_id"])  # type: ignore[attr-defined]
        lines.append(f"- {att['name']} ({att['mime']}, {att['size']} bytes) — {path}")
    return "\n".join(lines) + "\n\n"


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
    return [
        MessageResponse(
            role=m.get("role", ""),
            content=m.get("content", ""),
            attachments=list(m.get("attachments") or []),
        )
        for m in messages
    ]


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

    attachments = _resolve_attachments(request.attachments)
    user_message: dict[str, Any] = {"role": "user", "content": request.message}
    if attachments:
        user_message["attachments"] = attachments

    # Append user message.
    await manager.append_message(conversation_id, user_message)

    # Load full history for the agent.
    history = await manager.get_messages(conversation_id)

    mission = _build_attachments_prefix(attachments) + request.message

    # Execute agent with conversation history.
    result = await executor.execute_mission(
        mission=mission,
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
    "/{conversation_id}/messages/stream",
    summary="Stream a chat reply via SSE",
    responses={
        200: {
            "description": "Server-Sent Events stream of agent progress.",
            "content": {"text/event-stream": {}},
        },
        400: {"model": ErrorResponse},
    },
)
async def stream_message(
    conversation_id: str,
    request: AppendMessageRequest,
    manager=Depends(get_conversation_manager),
    executor=Depends(get_executor),
) -> StreamingResponse:
    """Append a user message, run the agent, and stream tokens back as SSE.

    The user message is persisted before the stream starts. The
    assistant reply is persisted in the ``finally`` block so that even
    a cancelled or failed stream leaves the conversation in a sane
    state (with a ``[partial]`` marker if the run did not complete).
    """
    if not request.message.strip():
        raise _error_response(
            status_code=400,
            code="invalid_request",
            message="Message content must not be empty",
            details={"field": "message"},
        )

    attachments = _resolve_attachments(request.attachments)
    user_message: dict[str, Any] = {"role": "user", "content": request.message}
    if attachments:
        user_message["attachments"] = attachments
    await manager.append_message(conversation_id, user_message)

    history = await manager.get_messages(conversation_id)
    mission = _build_attachments_prefix(attachments) + request.message

    async def event_stream() -> AsyncIterator[bytes]:
        accumulated_chunks: list[str] = []
        final_text: str | None = None
        completed = False
        try:
            yield _sse(
                "message_persisted",
                {"conversation_id": conversation_id},
            )
            async for update in executor.execute_mission_streaming(
                mission=mission,
                profile=request.profile,
                conversation_history=history,
            ):
                if update.event_type == EventType.LLM_TOKEN.value:
                    chunk = (update.details or {}).get("token") or update.message or ""
                    if isinstance(chunk, str) and chunk:
                        accumulated_chunks.append(chunk)
                if update.event_type == EventType.FINAL_ANSWER.value:
                    candidate = (update.details or {}).get("content") or update.message
                    if isinstance(candidate, str) and candidate:
                        final_text = candidate
                if update.event_type == EventType.COMPLETE.value:
                    completed = True
                payload = json.dumps(asdict(update), default=str)
                yield f"data: {payload}\n\n".encode("utf-8")
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001 — surfaced to client
            _chat_logger.exception("conversations.stream_failed")
            yield _sse(
                "error",
                {"error": str(exc), "error_type": type(exc).__name__},
            )
        finally:
            assistant_text = (final_text if final_text is not None else "".join(accumulated_chunks)).strip()
            if not completed and assistant_text:
                assistant_text += "\n\n[partial — interrupted]"
            elif not assistant_text:
                assistant_text = "[no response]"
            try:
                await manager.append_message(
                    conversation_id,
                    {"role": "assistant", "content": assistant_text},
                )
            except Exception:  # noqa: BLE001 — logging only
                _chat_logger.exception("conversations.persist_assistant_failed")
            persisted_payload = json.dumps(
                {
                    "conversation_id": conversation_id,
                    "completed": completed,
                    "content": assistant_text,
                }
            )
            yield f"event: assistant_persisted\ndata: {persisted_payload}\n\n".encode("utf-8")

    return StreamingResponse(event_stream(), media_type="text/event-stream")


def _sse(event_type: str, payload: dict[str, Any]) -> bytes:
    body = json.dumps(payload, default=str)
    return f"event: {event_type}\ndata: {body}\n\n".encode("utf-8")


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
