"""Conversation Management API routes (ADR-016).

Provides REST endpoints for managing persistent agent conversations:

- ``POST   /conversations``                    -- create a new conversation
- ``GET    /conversations``                    -- list active conversations
- ``GET    /conversations/archived``           -- list archived conversations
- ``GET    /conversations/{id}/messages``      -- get messages for a conversation
- ``POST   /conversations/{id}/messages``      -- append a message (and run agent)
- ``POST   /conversations/{id}/archive``       -- archive a conversation
- ``DELETE /conversations/{id}``               -- permanently delete a conversation
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

from taskforce.api.dependencies import (
    get_conversation_manager,
    get_executor,
    get_project_store,
)
from taskforce.api.errors import http_exception as _error_response
from taskforce.api.schemas.errors import ErrorResponse
from taskforce.application.file_storage import (
    FileNotFound as _FileNotFound,
    get_file_storage,
)
from taskforce.core.domain.enums import EventType
from taskforce.core.domain.planning.react_loop import (
    build_user_message_for_error as _build_user_message_for_error,
)

_chat_logger = structlog.get_logger("taskforce.api.routes.conversations")

router = APIRouter(prefix="/conversations", tags=["conversations"])


def _default_profile(*, in_project: bool = False) -> str:
    """Resolve the chat default profile.

    For project-scoped conversations we use the ``default`` profile
    (file/shell/python/edit/git tools, native ReAct) — the user wants
    a focused worker that knows how to operate inside a directory,
    not the butler's event-driven coordinator persona which underperforms
    on per-project work and aggressively delegates to sub-agents.

    Non-project chats keep the legacy resolution: ``butler`` when
    installed, otherwise ``default``. Mirrors the unified CLI behaviour.
    """
    if in_project:
        return "default"
    try:
        import importlib.util as _ilu

        if _ilu.find_spec("taskforce_butler") is not None:
            return "butler"
    except Exception:  # pragma: no cover — defensive
        pass
    return "default"


def _ping_interval_seconds() -> float:
    """How long the SSE consumer waits before emitting a keepalive ping."""
    import os as _os

    raw = _os.environ.get("TASKFORCE_SSE_PING_INTERVAL", "10.0")
    try:
        value = float(raw)
    except ValueError:
        return 10.0
    return max(0.1, value)


# ------------------------------------------------------------------
# Schemas
# ------------------------------------------------------------------


class CreateConversationRequest(BaseModel):
    """Request to start a new conversation."""

    channel: str = Field(default="rest", description="Channel identifier.")
    sender_id: str | None = Field(default=None, description="Sender identifier.")
    project_id: str | None = Field(
        default=None,
        description=(
            "Optional project to link the conversation to. When set, the "
            "agent's working_dir resolves to the project's path."
        ),
    )


class ConversationInfoResponse(BaseModel):
    """Active conversation metadata."""

    conversation_id: str
    channel: str
    started_at: datetime
    last_activity: datetime
    message_count: int
    topic: str | None = None
    project_id: str | None = None


class ConversationSummaryResponse(BaseModel):
    """Archived conversation summary."""

    conversation_id: str
    topic: str
    summary: str
    started_at: datetime
    archived_at: datetime
    message_count: int
    project_id: str | None = None


class AttachmentRef(BaseModel):
    """Reference to a previously uploaded file (see /api/v1/files)."""

    file_id: str = Field(..., min_length=1)


class AppendMessageRequest(BaseModel):
    """Message to send to the agent within a conversation."""

    message: str = Field(..., max_length=32_000, description="User message content.")
    profile: str | None = Field(
        default=None,
        description=(
            "Agent profile. When omitted, the server falls back to the same "
            "profile the unified CLI would pick (``butler`` if installed, "
            "otherwise ``default``)."
        ),
    )
    agent_id: str | None = Field(
        default=None,
        description=(
            "Registered custom-agent id (from the agent catalog / deployments). "
            "When set, the agent is loaded via the agent registry and ``profile`` "
            "is treated as the base profile fallback."
        ),
    )
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


async def _resolve_conversation_work_dir(
    manager: Any,
    project_store: Any,
    conversation_id: str,
) -> str | None:
    """Return the project's path for a conversation, or ``None``.

    Looks up the conversation in the manager's active list, reads the
    ``project_id`` if set, and resolves it to a directory path via the
    project store. Returns ``None`` when the conversation isn't linked
    to a project (the executor then falls back to the profile's
    configured ``persistence.work_dir``).
    """
    try:
        active = await manager.list_active()
    except Exception:  # noqa: BLE001 — defensive: never block a chat reply
        return None
    info = next(
        (c for c in active if c.conversation_id == conversation_id),
        None,
    )
    if info is None or info.project_id is None:
        return None
    project = await project_store.get(info.project_id)
    if project is None:
        # Conversation references a deleted project; let the executor
        # use the default work_dir rather than erroring out mid-chat.
        return None
    return project.path


def _build_attachments_prefix(attachments: list[dict[str, Any]]) -> str:
    """Render an attachment summary the agent can read."""
    if not attachments:
        return ""
    storage = get_file_storage()
    lines = ["[Attachments]"]
    for att in attachments:
        path = storage.blob_path(att["file_id"])
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
    project_store=Depends(get_project_store),
) -> ConversationInfoResponse:
    """Create a new conversation, archiving any existing active one for the channel."""
    if request.project_id is not None:
        project = await project_store.get(request.project_id)
        if project is None:
            raise _error_response(
                status_code=400,
                code="project_not_found",
                message=f"No project with id {request.project_id!r}.",
                details={"project_id": request.project_id},
            )

    conv_id = await manager.create_new(
        request.channel,
        request.sender_id,
        project_id=request.project_id,
    )
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
        project_id=info.project_id,
    )


@router.get(
    "",
    response_model=list[ConversationInfoResponse],
)
async def list_active_conversations(
    project_id: str | None = Query(
        default=None,
        description="Filter to conversations linked to this project id.",
    ),
    manager=Depends(get_conversation_manager),
) -> list[ConversationInfoResponse]:
    """List active (non-archived) conversations, optionally filtered by project."""
    active = await manager.list_active()
    if project_id is not None:
        active = [c for c in active if c.project_id == project_id]
    return [
        ConversationInfoResponse(
            conversation_id=c.conversation_id,
            channel=c.channel,
            started_at=c.started_at,
            last_activity=c.last_activity,
            message_count=c.message_count,
            topic=c.topic,
            project_id=c.project_id,
        )
        for c in active
    ]


@router.get(
    "/archived",
    response_model=list[ConversationSummaryResponse],
)
async def list_archived_conversations(
    limit: int = Query(default=20, ge=1, le=100),
    project_id: str | None = Query(
        default=None,
        description="Filter to conversations linked to this project id.",
    ),
    manager=Depends(get_conversation_manager),
) -> list[ConversationSummaryResponse]:
    """List archived conversations, optionally filtered by project."""
    archived = await manager.list_archived(limit)
    if project_id is not None:
        archived = [c for c in archived if getattr(c, "project_id", None) == project_id]
    return [
        ConversationSummaryResponse(
            conversation_id=c.conversation_id,
            topic=c.topic,
            summary=c.summary,
            started_at=c.started_at,
            archived_at=c.archived_at,
            message_count=c.message_count,
            project_id=getattr(c, "project_id", None),
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
    project_store=Depends(get_project_store),
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
    work_dir = await _resolve_conversation_work_dir(
        manager, project_store, conversation_id
    )
    # Project-scoped conversations default to the ``default`` profile —
    # see ``_default_profile`` for why butler isn't a good fit here.
    resolved_profile = request.profile or _default_profile(in_project=work_dir is not None)

    # Execute agent with conversation history.
    result = await executor.execute_mission(
        mission=mission,
        profile=resolved_profile,
        agent_id=request.agent_id,
        conversation_history=history,
        work_dir=work_dir,
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
    project_store=Depends(get_project_store),
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
    work_dir = await _resolve_conversation_work_dir(
        manager, project_store, conversation_id
    )
    resolved_profile = request.profile or _default_profile(in_project=work_dir is not None)

    async def event_stream() -> AsyncIterator[bytes]:
        accumulated_chunks: list[str] = []
        final_text: str | None = None
        # Last ERROR event surfaced by the agent (content_filter,
        # max_steps, …). Used as the persisted reply when the run
        # produces no FINAL_ANSWER + no LLM tokens — otherwise the user
        # would see a literal "[no response]" placeholder instead of an
        # actionable message (e.g. the German content-filter hint).
        error_text: str | None = None
        completed = False
        # Sentinel used to signal end-of-stream from the producer task.
        sentinel = object()
        # Bounded queue keeps the producer in lock-step with the consumer
        # so a slow client cannot starve the executor of its only feedback
        # path, but doesn't unbounded-buffer either.
        queue: asyncio.Queue = asyncio.Queue(maxsize=64)

        async def _produce() -> None:
            try:
                async for update in executor.execute_mission_streaming(
                    mission=mission,
                    profile=resolved_profile,
                    agent_id=request.agent_id,
                    conversation_history=history,
                    work_dir=work_dir,
                ):
                    await queue.put(update)
            except Exception as exc:  # noqa: BLE001 — forwarded to consumer
                await queue.put(exc)
            finally:
                await queue.put(sentinel)

        producer = asyncio.create_task(_produce())
        try:
            yield _sse(
                "message_persisted",
                {"conversation_id": conversation_id},
            )
            while True:
                try:
                    item = await asyncio.wait_for(
                        queue.get(), timeout=_ping_interval_seconds()
                    )
                except asyncio.TimeoutError:
                    # Reverse-proxy keepalive — yield an SSE comment so the
                    # connection stays warm across nginx / Cloudflare /
                    # Caddy idle thresholds (typically 30–60s).
                    yield b": ping\n\n"
                    continue

                if item is sentinel:
                    break
                if isinstance(item, Exception):
                    raise item

                update = item
                if update.event_type == EventType.LLM_TOKEN.value:
                    chunk = (update.details or {}).get("token") or update.message or ""
                    if isinstance(chunk, str) and chunk:
                        accumulated_chunks.append(chunk)
                if update.event_type == EventType.FINAL_ANSWER.value:
                    candidate = (update.details or {}).get("content") or update.message
                    if isinstance(candidate, str) and candidate:
                        final_text = candidate
                if update.event_type == EventType.ERROR.value:
                    # Build a user-facing message from the structured error so
                    # the persisted reply is something they can act on (e.g.
                    # content-filter advice) rather than "[no response]".
                    details = update.details or {}
                    error_kind = (
                        details.get("error_kind") if isinstance(details, dict) else None
                    )
                    raw_error = update.message or (
                        details.get("error") if isinstance(details, dict) else ""
                    )
                    error_text = _build_user_message_for_error(
                        error_kind or "", raw_error or ""
                    )
                if update.event_type == EventType.COMPLETE.value:
                    completed = True
                payload = json.dumps(asdict(update), default=str)
                yield f"data: {payload}\n\n".encode("utf-8")
        except asyncio.CancelledError:
            producer.cancel()
            raise
        except Exception as exc:  # noqa: BLE001 — surfaced to client
            _chat_logger.exception("conversations.stream_failed")
            yield _sse(
                "error",
                {"error": str(exc), "error_type": type(exc).__name__},
            )
        finally:
            if not producer.done():
                producer.cancel()
                try:
                    await producer
                except (asyncio.CancelledError, Exception):  # noqa: BLE001
                    pass
            assistant_text = (final_text if final_text is not None else "".join(accumulated_chunks)).strip()
            if not completed and assistant_text:
                assistant_text += "\n\n[partial — interrupted]"
            elif not assistant_text:
                # Prefer the structured ERROR message (content_filter,
                # max_steps, …) over the bare placeholder. Both are
                # last-resort UX strings — the error variant is just
                # informative.
                assistant_text = error_text or "[no response]"
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


@router.delete(
    "/{conversation_id}",
    status_code=204,
    responses={404: {"model": ErrorResponse}},
)
async def delete_conversation(
    conversation_id: str,
    manager=Depends(get_conversation_manager),
) -> None:
    """Permanently delete a conversation (active or archived).

    Removes the index entry and purges the on-disk message log. Unlike
    ``archive`` this is irreversible — used by the project UI when the
    user explicitly removes a past chat. Returns 404 when the
    conversation does not exist so the UI can detect double-clicks.
    """
    removed = await manager.delete(conversation_id)
    if not removed:
        raise _error_response(
            status_code=404,
            code="conversation_not_found",
            message=f"No conversation with id {conversation_id!r}.",
            details={"conversation_id": conversation_id},
        )


class ForkConversationRequest(BaseModel):
    """Body for ``POST /conversations/{id}/fork``."""

    up_to_index: int | None = Field(
        default=None,
        ge=0,
        description=(
            "Number of messages to copy from the source. ``None`` means "
            "copy the full transcript."
        ),
    )
    channel: str = Field(default="rest")


class ForkConversationResponse(BaseModel):
    conversation_id: str
    source_id: str
    messages_copied: int


@router.post(
    "/{conversation_id}/fork",
    response_model=ForkConversationResponse,
    status_code=201,
    summary="Fork a conversation into a fresh copy",
)
async def fork_conversation(
    conversation_id: str,
    request: ForkConversationRequest | None = None,
    manager=Depends(get_conversation_manager),
) -> ForkConversationResponse:
    """Create a new conversation seeded with the source's messages.

    Use case: replay a past conversation through a different profile or
    LLM model without mutating the original transcript.
    """
    body = request or ForkConversationRequest()
    new_id, copied = await manager.fork(
        conversation_id,
        up_to_index=body.up_to_index,
        channel=body.channel,
    )
    return ForkConversationResponse(
        conversation_id=new_id,
        source_id=conversation_id,
        messages_copied=copied,
    )


# ---------------------------------------------------------------------------
# Compact (Cowork-style /compact)
# ---------------------------------------------------------------------------


class CompactRequest(BaseModel):
    """Body for ``POST /conversations/{id}/compact``."""

    keep_last_n: int = Field(
        default=4,
        ge=0,
        le=50,
        description=(
            "Number of trailing messages to keep verbatim. Earlier messages "
            "are summarized into a single ``role=system`` summary message "
            "prepended to the kept tail. Defaults to 4."
        ),
    )
    model: str | None = Field(
        default=None,
        description=(
            "Optional model alias for the summarization call (e.g. ``fast``). "
            "Falls back to the LLM router's default routing for the "
            "``summarizing`` phase hint."
        ),
    )


class CompactResponse(BaseModel):
    """Result of a compact operation."""

    status: str = Field(
        ..., description="``compacted`` or ``skipped`` (see ``reason``)."
    )
    summarized: int = Field(
        default=0,
        description="Number of messages folded into the summary.",
    )
    kept: int = Field(default=0, description="Number of messages kept verbatim.")
    summary_preview: str | None = Field(
        default=None,
        description="First 200 chars of the generated summary (debug aid).",
    )
    reason: str | None = Field(
        default=None,
        description="Populated when ``status=skipped`` (e.g. ``below_threshold``).",
    )
    messages: int | None = Field(
        default=None,
        description="Total message count when skipped.",
    )


def _build_default_llm_provider() -> Any:
    """Build a transient LLM provider for the summarization call.

    Mirrors what ``InfrastructureBuilder.build_llm_provider`` does inside the
    main agent factory but without instantiating a full agent — we only need
    the ``complete`` surface here.
    """
    from taskforce.application.infrastructure_builder import InfrastructureBuilder

    return InfrastructureBuilder().build_llm_provider({"llm": {}})


async def _llm_summarizer(
    messages: list[dict[str, Any]],
    llm_provider: Any,
    model: str | None,
    system_prompt: str,
) -> str:
    """Format the transcript and ask the LLM for a compact summary."""
    transcript = _format_transcript_for_summary(messages)
    result = await llm_provider.complete(
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": transcript},
        ],
        # ``summarizing`` is the canonical phase hint that the LLM router
        # uses to pick a fast/cheap model when routing rules are configured.
        model=model or "summarizing",
    )
    if not result.get("success"):
        err = result.get("error") or "unknown error"
        raise RuntimeError(f"LLM summarization failed: {err}")
    content = result.get("content") or ""
    if not isinstance(content, str):
        content = str(content)
    return content


def _format_transcript_for_summary(messages: list[dict[str, Any]]) -> str:
    """Render a role-tagged transcript that fits in a single user turn.

    Each line is capped at 4000 chars to keep extreme tool outputs from
    blowing the summarizer's context. Truncation is marked explicitly so
    the LLM doesn't treat it as the end of a turn.
    """
    lines: list[str] = []
    for m in messages:
        role = m.get("role", "?")
        content = m.get("content", "")
        if isinstance(content, list):
            content = " ".join(str(p) for p in content)
        if not isinstance(content, str):
            content = str(content)
        if len(content) > 4000:
            content = content[:4000] + " …[truncated]"
        lines.append(f"[{role}] {content}")
    return "\n\n".join(lines)


@router.post(
    "/{conversation_id}/compact",
    response_model=CompactResponse,
    summary="Compact a conversation by summarizing earlier messages",
    responses={
        404: {"model": ErrorResponse, "description": "Conversation not found."},
    },
)
async def compact_conversation(
    conversation_id: str,
    request: CompactRequest | None = None,
    manager=Depends(get_conversation_manager),
) -> CompactResponse:
    """Compact the conversation: summarize earlier turns into a single
    ``role=system`` message while keeping the last N messages verbatim.

    Cowork-style ``/compact``: lets the user keep working in the same
    conversation_id without context-window pressure. The original messages
    are NOT recoverable after this operation — clients should warn before
    invoking it (or fork first).
    """
    body = request or CompactRequest()

    # Confirm the conversation exists; otherwise summarizing an empty
    # transcript is wasted work and the user gets a clearer error.
    existing = await manager.get_messages(conversation_id)
    if existing is None or (not existing and not await _conversation_exists(manager, conversation_id)):
        raise _error_response(
            status_code=404,
            code="conversation_not_found",
            message=f"No conversation with id {conversation_id!r}.",
            details={"conversation_id": conversation_id},
        )

    llm_provider = _build_default_llm_provider()

    async def summarizer(msgs: list[dict[str, Any]]) -> str:
        return await _llm_summarizer(
            msgs,
            llm_provider=llm_provider,
            model=body.model,
            system_prompt=manager._COMPACT_SYSTEM_PROMPT,  # noqa: SLF001
        )

    result = await manager.compact(
        conversation_id,
        summarizer,
        keep_last_n=body.keep_last_n,
    )
    return CompactResponse(**result)


async def _conversation_exists(manager: Any, conversation_id: str) -> bool:
    """Cheap existence check: scan the active list for the id."""
    try:
        active = await manager.list_active()
    except Exception:  # noqa: BLE001 — defensive
        return False
    return any(c.conversation_id == conversation_id for c in active)
