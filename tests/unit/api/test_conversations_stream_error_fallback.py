"""Tests for the conversations stream's ERROR-event fallback.

The chat stream used to fall back to the literal placeholder
``"[no response]"`` whenever no ``FINAL_ANSWER`` arrived — even when
the agent had emitted a structured ``ERROR`` event with
``error_kind="content_filter"`` carrying the actionable German recovery
hint from ADR-025. The persisted assistant reply then surfaced as
"[no response]" in the chat, masking the real cause.

The fix consumes ``EventType.ERROR`` events alongside ``FINAL_ANSWER``
and ``LLM_TOKEN``, runs them through ``build_user_message_for_error``,
and uses that as the persisted reply when no answer was produced.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import AsyncIterator
from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from taskforce.api.dependencies import get_conversation_manager, get_executor
from taskforce.api.routes.conversations import router
from taskforce.application.executor import ProgressUpdate
from taskforce.core.domain.enums import EventType
from taskforce.core.interfaces.conversation import ConversationInfo


CONV_ID = "abc123def456789012345678abcdef00"


@pytest.fixture
def mock_manager() -> AsyncMock:
    mgr = AsyncMock()
    mgr.get_messages = AsyncMock(return_value=[])
    mgr.append_message = AsyncMock()
    mgr.list_active = AsyncMock(
        return_value=[
            ConversationInfo(
                conversation_id=CONV_ID,
                channel="rest",
                started_at=datetime(2026, 5, 15, tzinfo=UTC),
                last_activity=datetime(2026, 5, 15, tzinfo=UTC),
                message_count=0,
                topic=None,
            )
        ]
    )
    return mgr


def _build_client(
    manager: AsyncMock, updates: list[ProgressUpdate]
) -> TestClient:
    async def _stream(*_args, **_kwargs) -> AsyncIterator[ProgressUpdate]:
        for upd in updates:
            yield upd

    executor = AsyncMock()
    executor.execute_mission_streaming = _stream

    app = FastAPI()
    app.include_router(router, prefix="/api/v1")
    app.dependency_overrides[get_conversation_manager] = lambda: manager
    app.dependency_overrides[get_executor] = lambda: executor
    return TestClient(app)


def _post_stream(client: TestClient) -> None:
    """Trigger the stream endpoint and drain the SSE body."""
    with client.stream(
        "POST",
        f"/api/v1/conversations/{CONV_ID}/messages/stream",
        json={"message": "egal", "profile": "dev"},
    ) as resp:
        assert resp.status_code == 200
        for _ in resp.iter_bytes():
            pass


def _persisted_assistant_message(manager: AsyncMock) -> str:
    """Pull the assistant reply that the stream finally persisted."""
    # append_message is called twice: once for the user input, once for the
    # assistant reply. The assistant reply is the call with role=assistant.
    for call in manager.append_message.await_args_list:
        msg = call.args[1] if len(call.args) > 1 else call.kwargs.get("message")
        if isinstance(msg, dict) and msg.get("role") == "assistant":
            return msg.get("content", "")
    raise AssertionError("no assistant message was persisted")


@pytest.mark.spec("conversations.stream_persists_error_message_when_no_tokens")
def test_content_filter_error_message_is_persisted_instead_of_no_response(
    mock_manager: AsyncMock,
) -> None:
    """An ERROR(error_kind=content_filter) → German recovery hint, not '[no response]'."""
    updates = [
        ProgressUpdate(
            timestamp=datetime.now(),
            event_type=EventType.ERROR,
            message="Exceeded max steps (30)",
            details={"error_kind": "content_filter"},
        ),
        ProgressUpdate(
            timestamp=datetime.now(),
            event_type=EventType.COMPLETE,
            message="Done",
            details={"status": "failed"},
        ),
    ]
    client = _build_client(mock_manager, updates)

    _post_stream(client)

    text = _persisted_assistant_message(mock_manager)
    assert "[no response]" not in text
    # The German hint from build_user_message_for_error / ADR-025.
    assert "Inhaltsfilter" in text or "content" in text.lower()


@pytest.mark.spec("conversations.stream_persists_error_message_when_no_tokens")
def test_generic_error_event_is_surfaced_with_raw_text(
    mock_manager: AsyncMock,
) -> None:
    """Without error_kind, the raw error text is wrapped into a user message."""
    updates = [
        ProgressUpdate(
            timestamp=datetime.now(),
            event_type=EventType.ERROR,
            message="provider timeout after 30s",
            details={},
        ),
        ProgressUpdate(
            timestamp=datetime.now(),
            event_type=EventType.COMPLETE,
            message="Done",
            details={"status": "failed"},
        ),
    ]
    client = _build_client(mock_manager, updates)

    _post_stream(client)

    text = _persisted_assistant_message(mock_manager)
    assert "[no response]" not in text
    assert "provider timeout" in text


def test_no_response_placeholder_still_used_when_no_error_event(
    mock_manager: AsyncMock,
) -> None:
    """Sanity: when the stream is genuinely silent, the placeholder still wins."""
    updates = [
        ProgressUpdate(
            timestamp=datetime.now(),
            event_type=EventType.COMPLETE,
            message="Done",
            details={"status": "completed"},
        ),
    ]
    client = _build_client(mock_manager, updates)

    _post_stream(client)

    text = _persisted_assistant_message(mock_manager)
    assert text == "[no response]"


@pytest.mark.spec("conversations.append_persists_user_message_before_agent_runs")
def test_user_message_persisted_independently_of_agent_output(
    mock_manager: AsyncMock,
) -> None:
    """The user's input is persisted as its own message — the SSE variant
    persists it before the agent runs, so it survives even a silent run."""
    updates = [
        ProgressUpdate(
            timestamp=datetime.now(),
            event_type=EventType.COMPLETE,
            message="Done",
            details={"status": "completed"},
        ),
    ]
    client = _build_client(mock_manager, updates)

    _post_stream(client)

    user_msgs = [
        (call.args[1] if len(call.args) > 1 else call.kwargs.get("message"))
        for call in mock_manager.append_message.await_args_list
        if isinstance(
            (call.args[1] if len(call.args) > 1 else call.kwargs.get("message")), dict
        )
        and (call.args[1] if len(call.args) > 1 else call.kwargs.get("message")).get(
            "role"
        )
        == "user"
    ]
    assert len(user_msgs) == 1
    assert user_msgs[0]["content"] == "egal"


@pytest.mark.spec("conversations.stream_persists_partial_on_cancel")
def test_partial_tokens_persisted_with_interrupted_marker(
    mock_manager: AsyncMock,
) -> None:
    """Tokens arrived but no COMPLETE event → the persisted assistant reply
    carries the '[partial — interrupted]' marker."""
    updates = [
        ProgressUpdate(
            timestamp=datetime.now(),
            event_type=EventType.LLM_TOKEN,
            message="Here is a partial answer",
            details={},
        ),
    ]
    client = _build_client(mock_manager, updates)

    _post_stream(client)

    text = _persisted_assistant_message(mock_manager)
    assert "Here is a partial answer" in text
    assert "[partial — interrupted]" in text
