"""Unit tests for the ctxman REST client (error mapping, retry, headers)."""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock

import pytest

from taskforce.infrastructure.context.ctxman_client import (
    CtxmanBudgetExceededError,
    CtxmanClient,
    CtxmanConflictError,
    CtxmanError,
    CtxmanGoneError,
    CtxmanIncompleteUnitError,
    CtxmanPayloadTooLargeError,
    CtxmanUnavailableError,
)


class FakeResponse:
    """Minimal stand-in for aiohttp.ClientResponse."""

    def __init__(self, status: int, body: str = "") -> None:
        self.status = status
        self._body = body

    async def text(self) -> str:
        return self._body


class FakeStreamResponse:
    """Stand-in for a streaming (SSE) aiohttp response."""

    def __init__(self, status: int, lines: list[bytes]) -> None:
        self.status = status
        self.content = self._iter(lines)
        self._body = ""

    @staticmethod
    async def _iter(lines: list[bytes]):
        for line in lines:
            yield line

    async def text(self) -> str:
        return self._body

    async def __aenter__(self) -> FakeStreamResponse:
        return self

    async def __aexit__(self, *exc_info: Any) -> None:
        return None


class FakeHttpSession:
    """aiohttp.ClientSession stand-in returning a canned stream response."""

    def __init__(self, response: FakeStreamResponse) -> None:
        self._response = response
        self.requested: list[tuple[str, dict[str, str]]] = []
        self.closed = False

    def get(self, url: str, *, headers: dict[str, str], **kwargs: Any):
        self.requested.append((url, headers))
        return self._response


@pytest.fixture
def client() -> CtxmanClient:
    return CtxmanClient(base_url="http://ctxman.test/", timeout_seconds=1)


# ---------------------------------------------------------------------------
# Response → error mapping
# ---------------------------------------------------------------------------


async def test_2xx_returns_parsed_json(client: CtxmanClient) -> None:
    response = FakeResponse(201, '{"session_id": "s1", "context_version": 3}')
    data = await client._handle_response("POST", "u", response)  # type: ignore[arg-type]
    assert data == {"session_id": "s1", "context_version": 3}


async def test_409_raises_conflict_with_version(client: CtxmanClient) -> None:
    response = FakeResponse(409, '{"context_version": 7}')
    with pytest.raises(CtxmanConflictError) as exc_info:
        await client._handle_response("PUT", "u", response)  # type: ignore[arg-type]
    assert exc_info.value.context_version == 7


async def test_410_raises_gone_with_summary_and_origin(client: CtxmanClient) -> None:
    response = FakeResponse(410, '{"summary": "old log", "origin": "skill://x"}')
    with pytest.raises(CtxmanGoneError) as exc_info:
        await client._handle_response("GET", "u", response)  # type: ignore[arg-type]
    assert exc_info.value.summary == "old log"
    assert exc_info.value.origin == "skill://x"


async def test_413_retryable_raises_budget_exceeded(client: CtxmanClient) -> None:
    response = FakeResponse(413, '{"error": "budget", "retryable": true}')
    with pytest.raises(CtxmanBudgetExceededError):
        await client._handle_response("POST", "u", response)  # type: ignore[arg-type]


async def test_413_non_retryable_raises_payload_too_large(client: CtxmanClient) -> None:
    response = FakeResponse(413, '{"error": "too big"}')
    with pytest.raises(CtxmanPayloadTooLargeError):
        await client._handle_response("POST", "u", response)  # type: ignore[arg-type]


async def test_422_raises_incomplete_unit_with_ids(client: CtxmanClient) -> None:
    response = FakeResponse(422, '{"open_tool_call_ids": ["call_1", "call_2"]}')
    with pytest.raises(CtxmanIncompleteUnitError) as exc_info:
        await client._handle_response("POST", "u", response)  # type: ignore[arg-type]
    assert exc_info.value.open_tool_call_ids == ["call_1", "call_2"]


@pytest.mark.parametrize("status", [500, 502, 503])
async def test_5xx_raises_unavailable(client: CtxmanClient, status: int) -> None:
    with pytest.raises(CtxmanUnavailableError):
        await client._handle_response("POST", "u", FakeResponse(status))  # type: ignore[arg-type]


async def test_400_raises_generic_error(client: CtxmanClient) -> None:
    response = FakeResponse(400, '{"error": "bad provider"}')
    with pytest.raises(CtxmanError) as exc_info:
        await client._handle_response("POST", "u", response)  # type: ignore[arg-type]
    assert "bad provider" in str(exc_info.value)


# ---------------------------------------------------------------------------
# Retry behaviour
# ---------------------------------------------------------------------------


@pytest.fixture
def no_sleep(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "taskforce.infrastructure.context.ctxman_client.asyncio.sleep",
        AsyncMock(),
    )


async def test_retries_with_same_idempotency_key(
    client: CtxmanClient,
    no_sleep: None,
) -> None:
    calls: list[dict[str, str]] = []

    async def failing_send(method: str, url: str, **kwargs: Any) -> dict[str, Any]:
        calls.append(dict(kwargs["headers"]))
        if len(calls) < 3:
            raise CtxmanUnavailableError("boom")
        return {"segment_ids": [], "context_version": 1}

    client._send = failing_send  # type: ignore[method-assign]
    await client.append_segments("s1", [], idempotency_key="key-1")
    assert len(calls) == 3
    assert all(headers["Idempotency-Key"] == "key-1" for headers in calls)


async def test_no_retry_for_mutation_without_idempotency_key(
    client: CtxmanClient,
    no_sleep: None,
) -> None:
    send = AsyncMock(side_effect=CtxmanUnavailableError("down"))
    client._send = send  # type: ignore[method-assign]
    with pytest.raises(CtxmanUnavailableError):
        await client._request("POST", "/v1/sessions")
    assert send.await_count == 1


async def test_get_is_retried(client: CtxmanClient, no_sleep: None) -> None:
    send = AsyncMock(side_effect=CtxmanUnavailableError("down"))
    client._send = send  # type: ignore[method-assign]
    with pytest.raises(CtxmanUnavailableError):
        await client.get_session("s1")
    assert send.await_count == 3


# ---------------------------------------------------------------------------
# Headers / request shapes
# ---------------------------------------------------------------------------


async def test_auth_and_tenant_headers() -> None:
    client = CtxmanClient(
        base_url="http://x",
        auth_mode="api_key",
        api_key="secret",
        tenant_id="t1",
    )
    headers = client._base_headers()
    assert headers["X-Api-Key"] == "secret"
    assert headers["X-Tenant-Id"] == "t1"


async def test_no_auth_headers_in_none_mode(client: CtxmanClient) -> None:
    assert client._base_headers() == {}


async def test_render_parses_request_fragment(client: CtxmanClient) -> None:
    client._send = AsyncMock(  # type: ignore[method-assign]
        return_value={
            "request_fragment": {
                "system": "base",
                "tools": [{"name": "t"}],
                "messages": [{"role": "user", "content": "hi"}],
            },
            "builtin_tools": [{"name": "expand_context_ref"}],
            "context_version": 9,
            "tokens_total": 1234,
            "watermark_state": "soft",
        }
    )
    result = await client.render("s1", provider="openai")
    assert result.messages == [{"role": "user", "content": "hi"}]
    assert result.system == "base"
    assert result.context_version == 9
    assert result.tokens_total == 1234
    assert result.watermark_state == "soft"
    assert result.builtin_tools[0]["name"] == "expand_context_ref"


async def test_stream_events_parses_sse_records(client: CtxmanClient) -> None:
    stream = FakeStreamResponse(
        200,
        [
            b"id: 6\n",
            b'data: {"seq": 6, "type": "segment_appended", "payload": {}}\n',
            b"\n",
            b"id: 7\n",
            b'data: {"seq": 7, "type": "frame_pushed", "payload": {}}\n',
            b"\n",
        ],
    )
    http_session = FakeHttpSession(stream)
    client._ensure_session = lambda: http_session  # type: ignore[method-assign]

    events = [event async for event in client.stream_events("s1", after_seq=5)]
    assert [event["seq"] for event in events] == [6, 7]
    assert events[1]["type"] == "frame_pushed"
    url, headers = http_session.requested[0]
    assert "after_seq=5" in url
    assert headers["Accept"] == "text/event-stream"


async def test_stream_events_maps_http_error(client: CtxmanClient) -> None:
    http_session = FakeHttpSession(FakeStreamResponse(404, []))
    client._ensure_session = lambda: http_session  # type: ignore[method-assign]
    with pytest.raises(CtxmanError):
        async for _ in client.stream_events("missing"):
            pass


async def test_archive_session_posts_with_idempotency_key(
    client: CtxmanClient,
) -> None:
    send = AsyncMock(return_value={})
    client._send = send  # type: ignore[method-assign]
    await client.archive_session("s1", idempotency_key="arch-1")
    method, url = send.await_args.args[0], send.await_args.args[1]
    assert method == "POST"
    assert url.endswith("/v1/sessions/s1/archive")
    assert send.await_args.kwargs["headers"]["Idempotency-Key"] == "arch-1"


async def test_push_and_pop_frame_paths(client: CtxmanClient) -> None:
    send = AsyncMock(return_value={"frame_id": "f1"})
    client._send = send  # type: ignore[method-assign]
    frame_id = await client.push_frame("s1", "research", idempotency_key="k")
    assert frame_id == "f1"
    method, url = send.await_args.args[0], send.await_args.args[1]
    assert method == "POST"
    assert url.endswith("/v1/sessions/s1/frames")

    send.return_value = {"return_segment_id": "seg", "context_version": 5}
    await client.pop_frame("s1", "f1", return_content="done", idempotency_key="k2")
    method, url = send.await_args.args[0], send.await_args.args[1]
    assert method == "DELETE"
    assert url.endswith("/v1/sessions/s1/frames/f1")
    assert send.await_args.kwargs["json_body"] == {"return_content": "done"}
