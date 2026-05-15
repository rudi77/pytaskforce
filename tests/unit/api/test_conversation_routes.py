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
def mock_project_store():
    """Project store stub — returns None for any lookup."""
    store = AsyncMock()
    store.get = AsyncMock(return_value=None)
    return store


@pytest.fixture
def client(mock_conversation_manager, mock_executor, mock_project_store):
    """Create a test client with overridden dependencies."""
    from fastapi import FastAPI

    from taskforce.api.dependencies import (
        get_conversation_manager,
        get_executor,
        get_project_store,
    )

    app = FastAPI()
    app.include_router(router, prefix="/api/v1")

    app.dependency_overrides[get_conversation_manager] = lambda: mock_conversation_manager
    app.dependency_overrides[get_executor] = lambda: mock_executor
    app.dependency_overrides[get_project_store] = lambda: mock_project_store

    return TestClient(app)


class TestCreateConversation:
    def test_creates_and_returns_info(self, client, mock_conversation_manager):
        resp = client.post("/api/v1/conversations", json={"channel": "rest"})
        assert resp.status_code == 201
        data = resp.json()
        assert data["conversation_id"] == "abc123def456789012345678abcdef00"
        assert data["channel"] == "rest"
        mock_conversation_manager.create_new.assert_called_once_with(
            "rest", None, project_id=None
        )


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


class TestForkConversation:
    def test_forks_full_transcript(self, client, mock_conversation_manager):
        mock_conversation_manager.fork = AsyncMock(return_value=("new-conv-id", 2))
        resp = client.post(
            "/api/v1/conversations/conv-source/fork",
            json={"up_to_index": None, "channel": "rest"},
        )
        assert resp.status_code == 201
        body = resp.json()
        assert body["conversation_id"] == "new-conv-id"
        assert body["source_id"] == "conv-source"
        assert body["messages_copied"] == 2
        mock_conversation_manager.fork.assert_called_once()

    def test_forks_partial_transcript(self, client, mock_conversation_manager):
        mock_conversation_manager.fork = AsyncMock(return_value=("forked", 2))
        resp = client.post(
            "/api/v1/conversations/source/fork",
            json={"up_to_index": 2},
        )
        assert resp.status_code == 201
        assert resp.json()["messages_copied"] == 2

    def test_messages_copied_is_actual_count_not_request(
        self, client, mock_conversation_manager
    ):
        """``up_to_index`` may exceed the source length; reported count must
        be what was actually copied."""
        mock_conversation_manager.fork = AsyncMock(return_value=("forked", 3))
        resp = client.post(
            "/api/v1/conversations/source/fork",
            json={"up_to_index": 999},
        )
        assert resp.status_code == 201
        assert resp.json()["messages_copied"] == 3


class TestCompactConversation:
    """Tests for ``POST /api/v1/conversations/{id}/compact``."""

    def test_returns_compact_result_for_existing_conversation(
        self, client, mock_conversation_manager, monkeypatch
    ):
        # Stub the LLM provider so the test doesn't hit a real API.
        async def fake_complete(messages, model=None, **kwargs):
            assert any(m["role"] == "system" for m in messages)
            return {"success": True, "content": "summary text"}

        class _Stub:
            async def complete(self, messages, model=None, **kwargs):
                return await fake_complete(messages, model=model, **kwargs)

        monkeypatch.setattr(
            "taskforce.api.routes.conversations._build_default_llm_provider",
            lambda: _Stub(),
        )

        # Manager pretends compact succeeded.
        mock_conversation_manager.compact = AsyncMock(
            return_value={
                "status": "compacted",
                "summarized": 8,
                "kept": 4,
                "summary_preview": "summary preview",
            }
        )

        resp = client.post(
            "/api/v1/conversations/abc123def456789012345678abcdef00/compact",
            json={"keep_last_n": 4},
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["status"] == "compacted"
        assert body["summarized"] == 8
        assert body["kept"] == 4
        assert body["summary_preview"] == "summary preview"

        # Compact was called with our keep_last_n + a callable summarizer.
        mock_conversation_manager.compact.assert_awaited_once()
        args, kwargs = mock_conversation_manager.compact.await_args
        assert args[0] == "abc123def456789012345678abcdef00"
        assert callable(args[1])
        assert kwargs["keep_last_n"] == 4

    def test_returns_404_for_unknown_conversation(
        self, client, mock_conversation_manager
    ):
        # No active conversations match the id; existence check fails.
        mock_conversation_manager.get_messages = AsyncMock(return_value=[])
        mock_conversation_manager.list_active = AsyncMock(return_value=[])

        resp = client.post(
            "/api/v1/conversations/does-not-exist/compact",
            json={},
        )
        assert resp.status_code == 404
        assert "conversation_not_found" in resp.text

    def test_skipped_status_passes_through(
        self, client, mock_conversation_manager, monkeypatch
    ):
        """When the manager returns skipped, the route should NOT call the
        LLM but still return 200 with the skip details."""
        monkeypatch.setattr(
            "taskforce.api.routes.conversations._build_default_llm_provider",
            lambda: object(),  # never called
        )
        mock_conversation_manager.compact = AsyncMock(
            return_value={
                "status": "skipped",
                "reason": "below_threshold",
                "messages": 3,
            }
        )
        resp = client.post(
            "/api/v1/conversations/abc123def456789012345678abcdef00/compact",
            json={"keep_last_n": 4},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "skipped"
        assert body["reason"] == "below_threshold"
        assert body["messages"] == 3
