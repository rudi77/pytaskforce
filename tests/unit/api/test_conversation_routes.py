"""Tests for the conversation REST API routes (ADR-016)."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient

from taskforce.api.routes.conversations import router
from taskforce.core.interfaces.conversation import ConversationInfo, ConversationSummary


@pytest.fixture
def mock_conversation_manager():
    """Build a mock ConversationManager."""
    mgr = AsyncMock()
    mgr.create_new = AsyncMock(return_value="abc123def456789012345678abcdef00")
    mgr.list_active = AsyncMock(
        return_value=[
            ConversationInfo(
                conversation_id="abc123def456789012345678abcdef00",
                channel="rest",
                started_at=datetime(2026, 3, 18, tzinfo=UTC),
                last_activity=datetime(2026, 3, 18, tzinfo=UTC),
                message_count=0,
                topic=None,
            ),
        ]
    )
    mgr.list_archived = AsyncMock(return_value=[])
    mgr.get_messages = AsyncMock(return_value=[])
    mgr.append_message = AsyncMock()
    mgr.archive = AsyncMock()
    return mgr


@pytest.fixture
def mock_executor():
    """Build a mock executor that returns a simple result."""
    from taskforce.core.domain.models import ExecutionResult

    executor = AsyncMock()
    executor.execute_mission = AsyncMock(
        return_value=ExecutionResult(
            session_id="sess-1",
            status="completed",
            final_message="Hello back!",
        )
    )
    return executor


@pytest.fixture
def client(mock_conversation_manager, mock_executor):
    """Create a test client with overridden dependencies."""
    from fastapi import FastAPI

    from taskforce.api.dependencies import get_conversation_manager, get_executor

    app = FastAPI()
    app.include_router(router, prefix="/api/v1")

    app.dependency_overrides[get_conversation_manager] = lambda: mock_conversation_manager
    app.dependency_overrides[get_executor] = lambda: mock_executor

    return TestClient(app)


class TestCreateConversation:
    def test_creates_and_returns_info(self, client, mock_conversation_manager):
        resp = client.post("/api/v1/conversations", json={"channel": "rest"})
        assert resp.status_code == 201
        data = resp.json()
        assert data["conversation_id"] == "abc123def456789012345678abcdef00"
        assert data["channel"] == "rest"
        mock_conversation_manager.create_new.assert_called_once_with("rest", None)


class TestListConversations:
    def test_list_active(self, client):
        resp = client.get("/api/v1/conversations")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["conversation_id"] == "abc123def456789012345678abcdef00"

    def test_list_archived(self, client, mock_conversation_manager):
        mock_conversation_manager.list_archived = AsyncMock(
            return_value=[
                ConversationSummary(
                    conversation_id="old-conv",
                    topic="Test topic",
                    summary="Summary here",
                    started_at=datetime(2026, 3, 1, tzinfo=UTC),
                    archived_at=datetime(2026, 3, 10, tzinfo=UTC),
                    message_count=12,
                ),
            ]
        )
        resp = client.get("/api/v1/conversations/archived")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["topic"] == "Test topic"


class TestAppendMessage:
    def test_sends_message_and_gets_reply(
        self, client, mock_conversation_manager, mock_executor
    ):
        # After append, get_messages should return updated messages.
        mock_conversation_manager.get_messages = AsyncMock(
            side_effect=[
                [{"role": "user", "content": "Hello"}],  # For executor history
                [
                    {"role": "user", "content": "Hello"},
                    {"role": "assistant", "content": "Hello back!"},
                ],  # Final count
            ]
        )
        resp = client.post(
            "/api/v1/conversations/conv-123/messages",
            json={"message": "Hello"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["reply"] == "Hello back!"
        assert data["status"] == "completed"
        assert data["message_count"] == 2

    def test_empty_message_rejected(self, client):
        resp = client.post(
            "/api/v1/conversations/conv-123/messages",
            json={"message": "   "},
        )
        assert resp.status_code == 400


class TestGetMessages:
    def test_returns_messages(self, client, mock_conversation_manager):
        mock_conversation_manager.get_messages = AsyncMock(
            return_value=[
                {"role": "user", "content": "Hi"},
                {"role": "assistant", "content": "Hello!"},
            ]
        )
        resp = client.get("/api/v1/conversations/conv-123/messages")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 2
        assert data[0]["role"] == "user"

    def test_returns_messages_with_limit(self, client, mock_conversation_manager):
        mock_conversation_manager.get_messages = AsyncMock(
            return_value=[{"role": "assistant", "content": "Last"}]
        )
        resp = client.get("/api/v1/conversations/conv-123/messages?limit=1")
        assert resp.status_code == 200
        mock_conversation_manager.get_messages.assert_called_once_with("conv-123", 1)


class TestArchiveConversation:
    def test_archive(self, client, mock_conversation_manager):
        resp = client.post(
            "/api/v1/conversations/conv-123/archive",
            json={"summary": "Done"},
        )
        assert resp.status_code == 204
        mock_conversation_manager.archive.assert_called_once_with("conv-123", "Done")

    def test_archive_without_summary(self, client, mock_conversation_manager):
        resp = client.post("/api/v1/conversations/conv-123/archive")
        assert resp.status_code == 204
        mock_conversation_manager.archive.assert_called_once_with("conv-123", None)
