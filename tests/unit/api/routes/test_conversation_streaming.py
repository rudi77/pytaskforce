"""Tests for the streaming chat endpoint (Phase 4)."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, AsyncIterator

import pytest

pytest.importorskip("fastapi")

from fastapi.testclient import TestClient

from taskforce.api.dependencies import get_conversation_manager, get_executor
from taskforce.api.server import create_app
from taskforce.application import file_storage
from taskforce.core.domain.enums import EventType


@dataclass
class _Update:
    event_type: str
    message: str = ""
    details: dict[str, Any] | None = None
    timestamp: str = "2026-04-29T00:00:00"


class _RecordingConversationManager:
    """Plain async manager double — avoids AsyncMock side-effect quirks."""

    def __init__(self) -> None:
        self.persisted: list[dict[str, Any]] = []

    async def append_message(self, _conv_id: str, msg: dict[str, Any]) -> None:
        self.persisted.append(msg)

    async def get_messages(
        self, _conv_id: str, _limit: int | None = None
    ) -> list[dict[str, Any]]:
        return list(self.persisted)


class _StreamingExecutor:
    """Plain executor double exposing an async-iterating mission stream."""

    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def execute_mission_streaming(self, **_kwargs) -> AsyncIterator[_Update]:
        self.calls.append(dict(_kwargs))
        async def _stream() -> AsyncIterator[_Update]:
            yield _Update(event_type=EventType.STARTED.value, message="started")
            yield _Update(
                event_type=EventType.LLM_TOKEN.value, details={"token": "Hello "}
            )
            yield _Update(
                event_type=EventType.LLM_TOKEN.value, details={"token": "world"}
            )
            yield _Update(
                event_type=EventType.FINAL_ANSWER.value,
                details={"content": "Hello world"},
            )
            yield _Update(event_type=EventType.COMPLETE.value, message="done")

        return _stream()


@pytest.fixture
def storage_root(tmp_path: Path) -> Path:
    target = tmp_path / "uploads"
    target.mkdir()
    file_storage.reset_root_for_tests(target)
    yield target
    file_storage.reset_file_storage()


@pytest.fixture
def conv_manager() -> _RecordingConversationManager:
    return _RecordingConversationManager()


@pytest.fixture
def streaming_executor() -> _StreamingExecutor:
    return _StreamingExecutor()


@pytest.fixture
def client(
    conv_manager: _RecordingConversationManager,
    streaming_executor: _StreamingExecutor,
    storage_root: Path,
):
    app = create_app()
    app.dependency_overrides[get_conversation_manager] = lambda: conv_manager
    app.dependency_overrides[get_executor] = lambda: streaming_executor
    return TestClient(app)


def test_streaming_persists_user_and_assistant(
    client: TestClient, conv_manager: _RecordingConversationManager
) -> None:
    response = client.post(
        "/api/v1/conversations/conv-1/messages/stream",
        json={"message": "hi", "profile": "default"},
    )
    assert response.status_code == 200
    body = response.text
    assert "event: message_persisted" in body
    assert '"event_type": "llm_token"' in body or '"event_type":"llm_token"' in body
    assert '"event_type": "final_answer"' in body or '"event_type":"final_answer"' in body
    assert "event: assistant_persisted" in body

    persisted = conv_manager.persisted
    assert [m["role"] for m in persisted] == ["user", "assistant"]
    assert persisted[0]["content"] == "hi"
    assert persisted[1]["content"] == "Hello world"


def test_streaming_with_attachment(
    client: TestClient, conv_manager: _RecordingConversationManager
) -> None:
    upload = client.post(
        "/api/v1/files",
        files={"file": ("note.txt", b"important data", "text/plain")},
    )
    assert upload.status_code == 201
    file_id = upload.json()["file_id"]

    response = client.post(
        "/api/v1/conversations/conv-2/messages/stream",
        json={
            "message": "summarise the attachment",
            "attachments": [{"file_id": file_id}],
        },
    )
    assert response.status_code == 200
    persisted = conv_manager.persisted
    user_msg = next(m for m in persisted if m["role"] == "user")
    assert user_msg["attachments"]
    assert user_msg["attachments"][0]["file_id"] == file_id


def test_streaming_rejects_unknown_attachment(client: TestClient) -> None:
    response = client.post(
        "/api/v1/conversations/conv-3/messages/stream",
        json={
            "message": "go",
            "attachments": [{"file_id": "00000000000000000000000000000000"}],
        },
    )
    assert response.status_code == 400
    assert response.json()["code"] == "attachment_not_found"


class _SlowExecutor:
    """Executor that idles long enough to trigger the SSE keepalive."""

    def execute_mission_streaming(self, **_kwargs) -> AsyncIterator[_Update]:
        async def _stream() -> AsyncIterator[_Update]:
            import asyncio as _asyncio

            yield _Update(event_type=EventType.STARTED.value, message="started")
            # Idle for longer than the ping interval so the consumer must
            # emit at least one ``: ping`` SSE comment.
            await _asyncio.sleep(0.3)
            yield _Update(
                event_type=EventType.FINAL_ANSWER.value,
                details={"content": "done"},
            )
            yield _Update(event_type=EventType.COMPLETE.value, message="done")

        return _stream()


def test_streaming_emits_keepalive_ping(
    monkeypatch: pytest.MonkeyPatch,
    storage_root: Path,
    conv_manager: _RecordingConversationManager,
) -> None:
    """When the executor stalls, the SSE response must include ``: ping``."""
    monkeypatch.setenv("TASKFORCE_SSE_PING_INTERVAL", "0.1")
    app = create_app()
    app.dependency_overrides[get_conversation_manager] = lambda: conv_manager
    app.dependency_overrides[get_executor] = lambda: _SlowExecutor()
    client = TestClient(app)

    response = client.post(
        "/api/v1/conversations/conv-keepalive/messages/stream",
        json={"message": "hi"},
    )
    assert response.status_code == 200
    assert ": ping" in response.text
    # The real events still get through.
    assert "event: assistant_persisted" in response.text


def test_streaming_forwards_permission_mode_to_executor(
    client: TestClient, streaming_executor: _StreamingExecutor
) -> None:
    response = client.post(
        "/api/v1/conversations/conv-perm/messages/stream",
        json={"message": "hi", "permission_mode": "plan"},
    )
    assert response.status_code == 200
    assert streaming_executor.calls, "executor should be invoked"
    assert streaming_executor.calls[-1].get("user_context") == {
        "permission_mode": "plan"
    }
