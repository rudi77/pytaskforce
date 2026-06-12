"""Low-level async REST client for the ctxman context-management service.

Wraps the ctxman ``/v1`` API (sessions, segments, render, static region,
refs, frames, gc, blobs) with typed errors and idempotency-key support.
Wire format is snake_case JSON as defined by the ctxman spec.
"""

from __future__ import annotations

import asyncio
import json
import uuid
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Any

import aiohttp

# Inline segment content above this size must go through the blob store
# (ctxman rejects larger inline payloads with 413).
MAX_INLINE_CONTENT_BYTES = 1_000_000

_RETRY_BACKOFF_SECONDS = (0.5, 1.0)


class CtxmanError(Exception):
    """Base error for ctxman client failures."""


class CtxmanUnavailableError(CtxmanError):
    """ctxman could not be reached (connect error, timeout, 5xx)."""


class CtxmanConflictError(CtxmanError):
    """409: If-Match version mismatch or constraint violation."""

    def __init__(self, message: str, context_version: int | None = None) -> None:
        super().__init__(message)
        self.context_version = context_version


class CtxmanIncompleteUnitError(CtxmanError):
    """422: open tool_calls without matching tool_results."""

    def __init__(self, message: str, open_tool_call_ids: list[str] | None = None) -> None:
        super().__init__(message)
        self.open_tool_call_ids = open_tool_call_ids or []


class CtxmanPayloadTooLargeError(CtxmanError):
    """413 on segment append: inline content exceeds the 1 MB limit."""


class CtxmanBudgetExceededError(CtxmanError):
    """413 on render: budget exceeded even after emergency eviction (retryable)."""


class CtxmanGoneError(CtxmanError):
    """410: segment evicted/compacted or blob swept; carries best-effort metadata."""

    def __init__(self, message: str, summary: str | None = None, origin: str | None = None) -> None:
        super().__init__(message)
        self.summary = summary
        self.origin = origin


@dataclass(frozen=True)
class RenderResult:
    """Parsed response of ``POST /v1/sessions/{sid}/render``."""

    messages: list[dict[str, Any]]
    system: str
    tools: list[dict[str, Any]]
    builtin_tools: list[dict[str, Any]]
    context_version: int
    tokens_total: int
    watermark_state: str
    cache_breakpoints: list[dict[str, Any]] = field(default_factory=list)


def new_idempotency_key() -> str:
    """Generate a fresh idempotency key for a mutation attempt."""
    return uuid.uuid4().hex


class CtxmanClient:
    """Async HTTP client for the ctxman ``/v1`` API.

    The aiohttp session is created lazily inside the running event loop
    (same pattern as the web tools). Retries happen only for connect
    errors and 503 responses, and only with the *same* Idempotency-Key,
    so replays are safe.
    """

    def __init__(
        self,
        *,
        base_url: str,
        timeout_seconds: float = 30.0,
        auth_mode: str = "none",
        api_key: str | None = None,
        tenant_id: str | None = None,
        logger: Any | None = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._timeout = aiohttp.ClientTimeout(total=timeout_seconds)
        self._auth_mode = auth_mode
        self._api_key = api_key
        self._tenant_id = tenant_id
        self._logger = logger
        self._session: aiohttp.ClientSession | None = None

    # ------------------------------------------------------------------
    # Session lifecycle
    # ------------------------------------------------------------------

    async def create_session(
        self,
        *,
        static_segments: list[dict[str, Any]],
        policy_overrides: dict[str, Any] | None = None,
        agent_template_id: str | None = None,
        idempotency_key: str | None = None,
    ) -> tuple[str, int]:
        """Create a session; returns ``(session_id, context_version)``."""
        body: dict[str, Any] = {"static_segments": static_segments}
        if policy_overrides:
            body["policy_overrides"] = policy_overrides
        if agent_template_id:
            body["agent_template_id"] = agent_template_id
        data = await self._request(
            "POST",
            "/v1/sessions",
            json_body=body,
            idempotency_key=idempotency_key,
        )
        return str(data["session_id"]), int(data.get("context_version", 0))

    async def get_session(self, session_id: str) -> dict[str, Any]:
        return await self._request("GET", f"/v1/sessions/{session_id}")

    async def archive_session(self, session_id: str, *, idempotency_key: str) -> None:
        await self._request(
            "POST",
            f"/v1/sessions/{session_id}/archive",
            idempotency_key=idempotency_key,
        )

    # ------------------------------------------------------------------
    # Segments
    # ------------------------------------------------------------------

    async def append_segments(
        self,
        session_id: str,
        segments: list[dict[str, Any]],
        *,
        idempotency_key: str,
        if_match: int | None = None,
    ) -> tuple[list[str], int]:
        """Append a batch of working segments; returns ``(segment_ids, version)``."""
        headers: dict[str, str] = {}
        if if_match is not None:
            headers["If-Match"] = str(if_match)
        data = await self._request(
            "POST",
            f"/v1/sessions/{session_id}/segments",
            json_body={"segments": segments},
            idempotency_key=idempotency_key,
            headers=headers,
        )
        return list(data.get("segment_ids", [])), int(data.get("context_version", 0))

    async def replace_static_segments(
        self,
        session_id: str,
        segments: list[dict[str, Any]],
        *,
        if_match: int,
        idempotency_key: str,
    ) -> dict[str, Any]:
        return await self._request(
            "PUT",
            f"/v1/sessions/{session_id}/static-segments",
            json_body={"segments": segments},
            idempotency_key=idempotency_key,
            headers={"If-Match": str(if_match)},
        )

    async def upload_blob(
        self,
        session_id: str,
        content: bytes,
        *,
        content_type: str = "text/plain; charset=utf-8",
    ) -> dict[str, Any]:
        """Upload a content-addressed blob; returns the ``blob_ref`` dict."""
        data = await self._request(
            "POST",
            f"/v1/sessions/{session_id}/blobs",
            raw_body=content,
            headers={"Content-Type": content_type},
        )
        return dict(data["blob_ref"])

    # ------------------------------------------------------------------
    # Render
    # ------------------------------------------------------------------

    async def render(
        self,
        session_id: str,
        *,
        provider: str,
        scope: str = "path",
        turn_advance: bool = True,
        idempotency_key: str | None = None,
    ) -> RenderResult:
        data = await self._request(
            "POST",
            f"/v1/sessions/{session_id}/render",
            json_body={
                "provider": provider,
                "scope": scope,
                "turn_advance": turn_advance,
            },
            idempotency_key=idempotency_key,
        )
        fragment = data.get("request_fragment") or {}
        return RenderResult(
            messages=list(fragment.get("messages", [])),
            system=str(fragment.get("system") or ""),
            tools=list(fragment.get("tools", [])),
            builtin_tools=list(data.get("builtin_tools", [])),
            context_version=int(data.get("context_version", 0)),
            tokens_total=int(data.get("tokens_total", 0)),
            watermark_state=str(data.get("watermark_state", "ok")),
            cache_breakpoints=list(data.get("cache_breakpoints", [])),
        )

    # ------------------------------------------------------------------
    # Refs (page faults)
    # ------------------------------------------------------------------

    async def get_ref(self, session_id: str, segment_id: str) -> dict[str, Any]:
        """Expand an externalized segment.

        Returns ``{"content": ..., "content_type": ...}`` on success.
        Raises ``CtxmanGoneError`` (with summary/origin) when the segment
        is no longer live (410).
        """
        return await self._request(
            "GET",
            f"/v1/sessions/{session_id}/refs/{segment_id}",
        )

    # ------------------------------------------------------------------
    # Frames
    # ------------------------------------------------------------------

    async def push_frame(
        self,
        session_id: str,
        label: str,
        *,
        idempotency_key: str,
    ) -> str:
        data = await self._request(
            "POST",
            f"/v1/sessions/{session_id}/frames",
            json_body={"label": label},
            idempotency_key=idempotency_key,
        )
        return str(data["frame_id"])

    async def pop_frame(
        self,
        session_id: str,
        frame_id: str,
        *,
        return_content: str,
        return_kind: str | None = None,
        idempotency_key: str,
    ) -> dict[str, Any]:
        body: dict[str, Any] = {"return_content": return_content}
        if return_kind:
            body["return_kind"] = return_kind
        return await self._request(
            "DELETE",
            f"/v1/sessions/{session_id}/frames/{frame_id}",
            json_body=body,
            idempotency_key=idempotency_key,
        )

    # ------------------------------------------------------------------
    # GC / events
    # ------------------------------------------------------------------

    async def gc(self, session_id: str, *, level: str = "minor") -> str:
        data = await self._request(
            "POST",
            f"/v1/sessions/{session_id}/gc",
            json_body={"level": level},
            idempotency_key=new_idempotency_key(),
        )
        return str(data.get("job_id", ""))

    async def get_events(
        self,
        session_id: str,
        *,
        after_seq: int = -1,
    ) -> list[dict[str, Any]]:
        data = await self._request(
            "GET",
            f"/v1/sessions/{session_id}/events?after_seq={after_seq}",
        )
        return list(data.get("events", []))

    async def stream_events(
        self,
        session_id: str,
        *,
        after_seq: int = -1,
    ) -> AsyncIterator[dict[str, Any]]:
        """Stream session events via SSE (``id:``/``data:`` lines).

        Yields one parsed event dict per SSE record. The ctxman stream
        serves the snapshot after ``after_seq`` and then completes; use
        the last event's ``seq`` as the cursor for the next call.
        """
        session = self._ensure_session()
        url = f"{self._base_url}/v1/sessions/{session_id}/events?after_seq={after_seq}"
        headers = self._base_headers()
        headers["Accept"] = "text/event-stream"
        try:
            async with session.get(
                url,
                headers=headers,
                # Streams may outlive the default total timeout; only
                # bound the connect phase.
                timeout=aiohttp.ClientTimeout(total=None, sock_connect=10),
            ) as response:
                if response.status >= 400:
                    await self._handle_response("GET", url, response)
                data_lines: list[str] = []
                async for raw_line in response.content:
                    line = raw_line.decode("utf-8").rstrip("\r\n")
                    if line.startswith("data:"):
                        data_lines.append(line[5:].strip())
                    elif not line and data_lines:
                        payload = json.loads("\n".join(data_lines))
                        data_lines = []
                        if isinstance(payload, dict):
                            yield payload
                if data_lines:
                    payload = json.loads("\n".join(data_lines))
                    if isinstance(payload, dict):
                        yield payload
        except (TimeoutError, aiohttp.ClientConnectionError) as exc:
            raise CtxmanUnavailableError(f"GET {url}: {exc}") from exc

    # ------------------------------------------------------------------
    # Plumbing
    # ------------------------------------------------------------------

    async def aclose(self) -> None:
        if self._session is not None and not self._session.closed:
            await self._session.close()
        self._session = None

    def _ensure_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(timeout=self._timeout)
        return self._session

    def _base_headers(self) -> dict[str, str]:
        headers: dict[str, str] = {}
        if self._auth_mode == "api_key" and self._api_key:
            headers["X-Api-Key"] = self._api_key
        if self._tenant_id:
            headers["X-Tenant-Id"] = self._tenant_id
        return headers

    async def _request(
        self,
        method: str,
        path: str,
        *,
        json_body: dict[str, Any] | None = None,
        raw_body: bytes | None = None,
        idempotency_key: str | None = None,
        headers: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        """Issue one request with bounded retry on connect errors / 503."""
        all_headers = self._base_headers()
        if headers:
            all_headers.update(headers)
        if idempotency_key:
            all_headers["Idempotency-Key"] = idempotency_key

        url = f"{self._base_url}{path}"
        last_error: Exception | None = None
        for attempt, backoff in enumerate((*_RETRY_BACKOFF_SECONDS, None)):
            try:
                return await self._send(
                    method,
                    url,
                    json_body=json_body,
                    raw_body=raw_body,
                    headers=all_headers,
                )
            except CtxmanUnavailableError as exc:
                last_error = exc
                # Only retry when a replay is safe: idempotent verbs or a
                # mutation carrying an Idempotency-Key.
                retryable = method == "GET" or idempotency_key is not None
                if backoff is None or not retryable:
                    raise
                if self._logger:
                    self._logger.warning(
                        "ctxman_request_retry",
                        method=method,
                        path=path,
                        attempt=attempt + 1,
                        error=str(exc),
                    )
                await asyncio.sleep(backoff)
        raise last_error or CtxmanUnavailableError(f"{method} {path} failed")

    async def _send(
        self,
        method: str,
        url: str,
        *,
        json_body: dict[str, Any] | None,
        raw_body: bytes | None,
        headers: dict[str, str],
    ) -> dict[str, Any]:
        session = self._ensure_session()
        try:
            async with session.request(
                method,
                url,
                json=json_body if raw_body is None else None,
                data=raw_body,
                headers=headers,
            ) as response:
                return await self._handle_response(method, url, response)
        except (TimeoutError, aiohttp.ClientConnectionError) as exc:
            raise CtxmanUnavailableError(f"{method} {url}: {exc}") from exc

    async def _handle_response(
        self,
        method: str,
        url: str,
        response: aiohttp.ClientResponse,
    ) -> dict[str, Any]:
        status = response.status
        text = await response.text()
        payload: dict[str, Any] = {}
        if text:
            try:
                parsed = json.loads(text)
                if isinstance(parsed, dict):
                    payload = parsed
            except json.JSONDecodeError:
                payload = {}

        if 200 <= status < 300:
            return payload
        if status == 409:
            raise CtxmanConflictError(
                payload.get("error") or f"conflict on {method} {url}",
                context_version=payload.get("context_version"),
            )
        if status == 410:
            raise CtxmanGoneError(
                payload.get("error") or "content gone",
                summary=payload.get("summary"),
                origin=payload.get("origin"),
            )
        if status == 413:
            if payload.get("retryable"):
                raise CtxmanBudgetExceededError(payload.get("error") or "budget exceeded")
            raise CtxmanPayloadTooLargeError(payload.get("error") or "payload too large")
        if status == 422:
            raise CtxmanIncompleteUnitError(
                payload.get("error") or "incomplete units",
                open_tool_call_ids=payload.get("open_tool_call_ids"),
            )
        if status == 503 or status >= 500:
            raise CtxmanUnavailableError(payload.get("error") or f"{status} on {method} {url}")
        raise CtxmanError(payload.get("error") or f"unexpected status {status} on {method} {url}")
