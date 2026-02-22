"""Unified Communication Gateway API routes.

Provides a single entry point for all channel-based agent communication,
replacing the previous per-provider integration routes. Supports:

- ``POST /gateway/{channel}/messages`` -- handle inbound messages from any channel
- ``POST /gateway/{channel}/webhook`` -- handle raw provider webhooks (Telegram, Teams)
- ``POST /gateway/notify`` -- send proactive push notifications
- ``POST /gateway/broadcast`` -- broadcast to all recipients on a channel
- ``GET  /gateway/channels`` -- list configured channels
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from taskforce.api.dependencies import get_gateway, get_inbound_adapters
from taskforce.api.schemas.errors import ErrorResponse
from taskforce.core.domain.gateway import (
    GatewayOptions,
    InboundMessage,
    NotificationRequest,
)

router = APIRouter(prefix="/gateway")


# ------------------------------------------------------------------
# Request / Response schemas
# ------------------------------------------------------------------


class GatewayMessageRequest(BaseModel):
    """Inbound message payload for the gateway."""

    conversation_id: str = Field(
        ...,
        description="Channel-specific conversation identifier.",
        examples=["123456789", "19:abc123@thread.v2"],
    )
    message: str = Field(
        ...,
        max_length=32_000,
        description="User message content.",
        examples=["Wie ist der aktuelle Status?"],
    )
    sender_id: str | None = Field(
        default=None,
        description="Sender identifier for recipient auto-registration.",
    )
    session_id: str | None = Field(
        default=None,
        description="Optional session ID override.",
    )
    profile: str = Field(
        default="dev",
        description="Agent profile to use.",
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
        description="Optional plugin path.",
    )
    metadata: dict[str, Any] | None = Field(
        default=None,
        description="Optional channel-specific metadata.",
    )


class GatewayMessageResponse(BaseModel):
    """Response from gateway message handling."""

    session_id: str = Field(..., description="Resolved session identifier.")
    status: str = Field(..., description="Execution status.")
    reply: str = Field(..., description="Agent reply message.")
    history_length: int = Field(..., description="Total history entries for this conversation.")


class NotificationRequestSchema(BaseModel):
    """Request to send a proactive push notification."""

    channel: str = Field(
        ...,
        description="Target channel (e.g. 'telegram', 'teams').",
    )
    recipient_id: str = Field(
        ...,
        description="Application-level user ID.",
    )
    message: str = Field(
        ...,
        description="Notification message text.",
    )
    metadata: dict[str, Any] | None = Field(
        default=None,
        description="Optional channel-specific formatting.",
    )


class NotificationResponseSchema(BaseModel):
    """Response from notification dispatch."""

    success: bool
    channel: str
    recipient_id: str
    error: str | None = None


class BroadcastRequestSchema(BaseModel):
    """Request to broadcast a message to all recipients on a channel."""

    channel: str = Field(..., description="Target channel.")
    message: str = Field(..., description="Message text.")
    metadata: dict[str, Any] | None = Field(default=None, description="Optional formatting.")


class BroadcastResponseSchema(BaseModel):
    """Response from broadcast."""

    total: int
    sent: int
    failed: int
    results: list[NotificationResponseSchema]


class ChannelsResponseSchema(BaseModel):
    """List of configured channels."""

    channels: list[str]


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------


def _build_user_context(request: GatewayMessageRequest) -> dict[str, Any] | None:
    if not any([request.user_id, request.org_id, request.scope]):
        return None
    return {
        "user_id": request.user_id,
        "org_id": request.org_id,
        "scope": request.scope,
    }


def _error_response(
    status_code: int, code: str, message: str, details: dict[str, Any] | None = None
) -> HTTPException:
    return HTTPException(
        status_code=status_code,
        detail=ErrorResponse(
            code=code,
            message=message,
            details=details,
            detail=message,
        ).model_dump(exclude_none=True),
        headers={"X-Taskforce-Error": "1"},
    )


# ------------------------------------------------------------------
# Endpoints
# ------------------------------------------------------------------


@router.post(
    "/{channel}/messages",
    response_model=GatewayMessageResponse,
    responses={400: {"model": ErrorResponse}},
)
async def handle_message(
    channel: str,
    request: GatewayMessageRequest,
    gateway=Depends(get_gateway),
) -> GatewayMessageResponse:
    """Handle an inbound message from any channel.

    The channel path parameter identifies the source (e.g. 'telegram', 'teams',
    'rest'). The gateway manages session mapping, conversation history,
    agent execution, and outbound reply dispatch.
    """
    if not request.message.strip():
        raise _error_response(
            400,
            "invalid_request",
            "Message content must not be empty",
            details={"field": "message"},
        )

    inbound = InboundMessage(
        channel=channel,
        conversation_id=request.conversation_id,
        message=request.message,
        sender_id=request.sender_id,
        metadata=request.metadata or {},
    )

    options = GatewayOptions(
        profile=request.profile,
        session_id=request.session_id,
        user_context=_build_user_context(request),
        agent_id=request.agent_id,
        planning_strategy=request.planning_strategy,
        planning_strategy_params=request.planning_strategy_params,
        plugin_path=request.plugin_path,
    )

    response = await gateway.handle_message(inbound, options)

    return GatewayMessageResponse(
        session_id=response.session_id,
        status=response.status,
        reply=response.reply,
        history_length=len(response.history),
    )


@router.post(
    "/{channel}/webhook",
    response_model=GatewayMessageResponse,
    responses={400: {"model": ErrorResponse}},
)
async def handle_webhook(
    channel: str,
    request: Request,
    gateway=Depends(get_gateway),
    inbound_adapters=Depends(get_inbound_adapters),
) -> GatewayMessageResponse:
    """Handle a raw webhook payload from an external channel.

    Uses the channel's InboundAdapter to normalize the raw payload,
    verify its signature, and then process it through the gateway.
    """
    adapter = inbound_adapters.get(channel)
    if not adapter:
        raise _error_response(
            400,
            "invalid_request",
            f"No inbound adapter for channel '{channel}'",
            details={"channel": channel},
        )

    raw_body = await request.body()
    headers = {k.lower(): v for k, v in request.headers.items()}

    if not adapter.verify_signature(raw_body=raw_body, headers=headers):
        raise _error_response(
            401,
            "unauthorized",
            "Webhook signature verification failed",
            details={"channel": channel},
        )

    try:
        raw_payload = await request.json()
        extracted = adapter.extract_message(raw_payload)
    except (ValueError, KeyError) as exc:
        raise _error_response(
            400,
            "invalid_request",
            f"Failed to parse webhook payload: {exc}",
            details={"channel": channel},
        ) from exc

    inbound = InboundMessage(
        channel=channel,
        conversation_id=extracted["conversation_id"],
        message=extracted["message"],
        sender_id=extracted.get("sender_id"),
        metadata=extracted.get("metadata", {}),
    )

    response = await gateway.handle_message(inbound)

    return GatewayMessageResponse(
        session_id=response.session_id,
        status=response.status,
        reply=response.reply,
        history_length=len(response.history),
    )


@router.post(
    "/notify",
    response_model=NotificationResponseSchema,
    responses={400: {"model": ErrorResponse}},
)
async def send_notification(
    request: NotificationRequestSchema,
    gateway=Depends(get_gateway),
) -> NotificationResponseSchema:
    """Send a proactive push notification to a registered recipient."""
    if not request.message.strip():
        raise _error_response(
            400,
            "invalid_request",
            "Notification message must not be empty",
            details={"field": "message"},
        )

    result = await gateway.send_notification(
        NotificationRequest(
            channel=request.channel,
            recipient_id=request.recipient_id,
            message=request.message,
            metadata=request.metadata or {},
        )
    )

    return NotificationResponseSchema(
        success=result.success,
        channel=result.channel,
        recipient_id=result.recipient_id,
        error=result.error,
    )


@router.post(
    "/broadcast",
    response_model=BroadcastResponseSchema,
    responses={400: {"model": ErrorResponse}},
)
async def broadcast(
    request: BroadcastRequestSchema,
    gateway=Depends(get_gateway),
) -> BroadcastResponseSchema:
    """Broadcast a message to all registered recipients on a channel."""
    if not request.message.strip():
        raise _error_response(
            400,
            "invalid_request",
            "Broadcast message must not be empty",
            details={"field": "message"},
        )

    results = await gateway.broadcast(
        channel=request.channel,
        message=request.message,
        metadata=request.metadata,
    )

    return BroadcastResponseSchema(
        total=len(results),
        sent=sum(1 for r in results if r.success),
        failed=sum(1 for r in results if not r.success),
        results=[
            NotificationResponseSchema(
                success=r.success,
                channel=r.channel,
                recipient_id=r.recipient_id,
                error=r.error,
            )
            for r in results
        ],
    )


@router.get(
    "/channels",
    response_model=ChannelsResponseSchema,
)
async def list_channels(
    gateway=Depends(get_gateway),
) -> ChannelsResponseSchema:
    """List all communication channels with outbound senders configured."""
    return ChannelsResponseSchema(
        channels=sorted(gateway.supported_channels()),
    )
