"""
Active Runs API
===============

Surfaces in-flight executions (sessions currently running on this
server) plus an SSE stream that pushes a fresh snapshot every couple of
seconds so the management UI's live table stays fresh without polling.
"""

from __future__ import annotations

import asyncio
import json
from typing import AsyncIterator

from fastapi import APIRouter, Request, status
from fastapi.responses import StreamingResponse

from taskforce.api.errors import http_exception as _http_exception
from taskforce.api.schemas.analytics_schemas import ActiveRunResponse, ActiveRunsResponse
from taskforce.application.run_registry import get_run_registry
from taskforce.application.run_trace_store import get_run_trace_store

router = APIRouter()

POLL_INTERVAL_SECONDS = 2.0


def _to_response(snapshot: list[dict]) -> ActiveRunsResponse:
    return ActiveRunsResponse(
        runs=[ActiveRunResponse(**entry) for entry in snapshot]
    )


@router.get(
    "/runs/active",
    response_model=ActiveRunsResponse,
    summary="List currently running executions",
)
def list_active_runs() -> ActiveRunsResponse:
    return _to_response(get_run_registry().snapshot_dicts())


@router.get(
    "/runs/recent",
    summary="List recent runs (active + recently finished, captured by the trace store)",
)
def list_recent_runs() -> dict:
    return {"runs": get_run_trace_store().list_sessions()}


@router.get(
    "/runs/{session_id}/trace",
    summary="Return the recorded ReAct trace for a run",
)
def get_run_trace(session_id: str) -> dict:
    trace = get_run_trace_store().get(session_id)
    if trace is None:
        raise _http_exception(
            status_code=status.HTTP_404_NOT_FOUND,
            code="run_not_found",
            message=f"No recorded trace for session '{session_id}'.",
        )
    return trace


@router.get(
    "/runs/active/stream",
    summary="Stream active-runs snapshots via SSE",
    responses={200: {"content": {"text/event-stream": {}}}},
)
def stream_active_runs(request: Request) -> StreamingResponse:
    async def _gen() -> AsyncIterator[bytes]:
        registry = get_run_registry()
        last_payload: str | None = None
        while True:
            # Stop the loop the moment the client disconnects so the server
            # doesn't hold a busy task slot until the next poll tick.
            if await request.is_disconnected():
                break
            snapshot = registry.snapshot_dicts()
            payload = json.dumps({"runs": snapshot})
            if payload != last_payload:
                yield f"data: {payload}\n\n".encode("utf-8")
                last_payload = payload
            else:
                # keepalive comment so proxies don't time out on quiet streams.
                yield b": keep-alive\n\n"
            await asyncio.sleep(POLL_INTERVAL_SECONDS)

    return StreamingResponse(_gen(), media_type="text/event-stream")
