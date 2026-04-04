"""Unit tests for the conversations routes (ADR-016)."""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

pytest.importorskip("fastapi")

from fastapi.testclient import TestClient

from taskforce.api.server import create_app
from taskforce.core.interfaces.conversation import ConversationInfo, ConversationSummary


def _mock_conversation_manager():
    """Create a mock ConversationManager."""
    mgr = AsyncMock()
    now = datetime.now(UTC)

    mgr.create_new = AsyncMock(return_value="conv-new-123")
    mgr.list_active = AsyncMock(
        return_value=[
            ConversationInfo(
                conversation_id="conv-new-123",
                channel="rest",
                started_at=now,
                last_activity=now,
                message_count=0,
                topic=None,
            ),
            ConversationInfo(
                conversation_id="conv-abc",
                channel="cli",
                started_at=now,
                last_activity=now,
                message_count=5,
                topic="Testing",
            ),
        ]
    )
    mgr.list_archived = AsyncMock(
        return_value=[
            ConversationSummary(
                conversation_id="conv-old",
                topic="Old topic",
                summary="Was about testing.",
                started_at=now,
                archived_at=now,
                message_count=10,
            ),
        ]
    )
    mgr.get_messages = AsyncMock(
        return_value=[
            {"role": "user", "content": "Hello"},
            {"role": "assistant", "content": "Hi there!"},
        ]
    )
    mgr.append_message = AsyncMock()
    mgr.archive = AsyncMock()
    return mgr


def _mock_executor():
    """Create a mock AgentExecutor."""
    executor = AsyncMock()
    result = MagicMock()
    result.final_message = "Agent reply"
    result.status_value = "completed"
    executor.execute_mission = AsyncMock(return_value=result)
    return executor


@pytest.fixture
def client():
    app = create_app()
    mgr = _mock_conversation_manager()
    executor = _mock_executor()

    from taskforce.api.dependencies import get_conversation_manager, get_executor

    app.dependency_overrides[get_conversation_manager] = lambda: mgr
    app.dependency_overrides[get_executor] = lambda: executor
    yield TestClient(app), mgr, executor
    app.dependency_overrides.clear()


class TestCreateConversation:
    """Tests for POST /api/v1/conversations."""

    def test_create_conversation_success(self, client):
        tc, mgr, _ = client
        response = tc.post(
            "/api/v1/conversations",
            json={"channel": "rest"},
        )
        assert response.status_code == 201
        body = response.json()
        assert body["conversation_id"] == "conv-new-123"
        assert body["channel"] == "rest"
        mgr.create_new.assert_awaited_once()


class TestListConversations:
    """Tests for GET /api/v1/conversations."""

    def test_list_active_conversations(self, client):
        tc, _, _ = client
        response = tc.get("/api/v1/conversations")
        assert response.status_code == 200
        body = response.json()
        assert isinstance(body, list)
        assert len(body) == 2
        assert body[0]["conversation_id"] == "conv-new-123"

    def test_list_archived_conversations(self, client):
        tc, _, _ = client
        response = tc.get("/api/v1/conversations/archived")
        assert response.status_code == 200
        body = response.json()
        assert len(body) == 1
        assert body[0]["conversation_id"] == "conv-old"
        assert body[0]["topic"] == "Old topic"


class TestGetMessages:
    """Tests for GET /api/v1/conversations/{id}/messages."""

    def test_get_messages_success(self, client):
        tc, _, _ = client
        response = tc.get("/api/v1/conversations/conv-abc/messages")
        assert response.status_code == 200
        body = response.json()
        assert len(body) == 2
        assert body[0]["role"] == "user"
        assert body[1]["role"] == "assistant"


class TestAppendMessage:
    """Tests for POST /api/v1/conversations/{id}/messages."""

    def test_append_message_success(self, client):
        tc, mgr, executor = client
        # After appending, get_messages returns 3 messages
        mgr.get_messages = AsyncMock(
            return_value=[
                {"role": "user", "content": "Hello"},
                {"role": "assistant", "content": "Hi there!"},
                {"role": "user", "content": "New message"},
            ]
        )
        response = tc.post(
            "/api/v1/conversations/conv-abc/messages",
            json={"message": "New message", "profile": "dev"},
        )
        assert response.status_code == 200
        body = response.json()
        assert body["reply"] == "Agent reply"
        assert body["status"] == "completed"
        assert body["conversation_id"] == "conv-abc"

    def test_append_empty_message_rejected(self, client):
        tc, _, _ = client
        response = tc.post(
            "/api/v1/conversations/conv-abc/messages",
            json={"message": "  "},
        )
        assert response.status_code == 400


class TestArchiveConversation:
    """Tests for POST /api/v1/conversations/{id}/archive."""

    def test_archive_conversation_success(self, client):
        tc, mgr, _ = client
        response = tc.post("/api/v1/conversations/conv-abc/archive")
        assert response.status_code == 204
        mgr.archive.assert_awaited_once()
