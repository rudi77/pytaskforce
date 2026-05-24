"""Generic inbound webhook endpoint for any registered ``WebhookCapableEventSource``.

Replaces the previous per-channel ``POST /gateway/{channel}/webhook``
entry for sources that are not channels — file-system watchers,
GitHub/GitLab webhooks, custom integrations. The route is intentionally
thin: it looks up the source instance in the active registry and
forwards the raw body and headers, letting the source implement its own
authentication (HMAC, JWT, ...).

* HTTP 401 if the source raised a signature mismatch.
* HTTP 404 if no source with that name is currently active.
* HTTP 415 if the body is not parseable JSON.
* HTTP 202 with ``{"event_id": ..., "source": ...}`` on success.
"""

from __future__ import annotations

import json
import re
from typing import Any

import structlog
from fastapi import APIRouter, HTTPException, Path, Request, status

from taskforce.api.dependencies import (
    get_active_event_source,
    list_active_event_sources,
)
from taskforce.core.interfaces.event_source import WebhookCapableEventSource

router = APIRouter()
logger = structlog.get_logger(__name__)

# Source-name path-param constraint. Bounded length + restricted charset
# stops an attacker from flooding logs / disk with multi-MB names and
# guarantees the value is safe to embed in log lines and error replies.
# 64 chars matches the framework's other identifier limits.
_SOURCE_NAME_PATTERN = r"^[A-Za-z0-9_-]{1,64}$"
_SOURCE_NAME_RE = re.compile(_SOURCE_NAME_PATTERN)


@router.post("/events/{source_name}", status_code=status.HTTP_202_ACCEPTED)
async def receive_event(
    source_name: str = Path(..., pattern=_SOURCE_NAME_PATTERN, max_length=64),
    request: Request = ...,  # type: ignore[assignment]
) -> dict[str, Any]:
    """Forward an inbound webhook to the registered event source."""
    # Defense-in-depth: FastAPI already validates against the pattern,
    # but a custom client that bypasses the route layer (in-process
    # tests, ASGI middleware) gets the same rejection here.
    if not _SOURCE_NAME_RE.fullmatch(source_name):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="source_name must match [A-Za-z0-9_-]{1,64}",
        )
    source = get_active_event_source(source_name)
    if source is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=(
                f"No active event source named {source_name!r}. "
                f"Known: {list_active_event_sources()}"
            ),
        )
    if not isinstance(source, WebhookCapableEventSource):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"Event source {source_name!r} does not accept inbound webhooks "
                "(no handle_inbound method)."
            ),
        )

    raw_body = await request.body()
    try:
        payload: dict[str, Any] = json.loads(raw_body) if raw_body else {}
    except json.JSONDecodeError as exc:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail=f"Body is not valid JSON: {exc}",
        ) from exc

    headers = {k: v for k, v in request.headers.items()}
    try:
        # GitHub-style sources need the exact bytes for HMAC verification;
        # forward them when the source signature accepts ``raw_body``.
        try:
            event = await source.handle_inbound(  # type: ignore[call-arg]
                payload, headers, raw_body=raw_body
            )
        except TypeError:
            event = await source.handle_inbound(payload, headers)
    except ValueError as exc:
        # Sources signal authentication failures by raising ValueError
        # (or a subclass). Translate to HTTP 401 so the sender sees a
        # precise error.
        logger.warning(
            "events_route.signature_rejected",
            source_name=source_name,
            error=str(exc),
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(exc),
        ) from exc

    return {
        "event_id": getattr(event, "event_id", None),
        "source": source_name,
        "status": "accepted",
    }
