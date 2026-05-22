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
    mgr.delete = AsyncMock(return_value=True)
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
        mock_conversation_manager.create_new.assert_called_once_with("rest", None, project_id=None)


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

    @pytest.mark.spec("cowork.list_filtered_by_project_id")
    def test_list_active_filters_by_project(self, client, mock_conversation_manager):
        """``?project_id`` keeps only conversations linked to the project."""
        mock_conversation_manager.list_active = AsyncMock(
            return_value=[
                ConversationInfo(
                    conversation_id="conv-a",
                    channel="rest",
                    started_at=datetime(2026, 4, 1, tzinfo=UTC),
                    last_activity=datetime(2026, 4, 1, tzinfo=UTC),
                    message_count=1,
                    topic=None,
                    project_id="proj-1",
                ),
                ConversationInfo(
                    conversation_id="conv-b",
                    channel="rest",
                    started_at=datetime(2026, 4, 2, tzinfo=UTC),
                    last_activity=datetime(2026, 4, 2, tzinfo=UTC),
                    message_count=1,
                    topic=None,
                    project_id="proj-2",
                ),
                ConversationInfo(
                    conversation_id="conv-c",
                    channel="rest",
                    started_at=datetime(2026, 4, 3, tzinfo=UTC),
                    last_activity=datetime(2026, 4, 3, tzinfo=UTC),
                    message_count=1,
                    topic=None,
                    project_id=None,
                ),
            ]
        )
        resp = client.get("/api/v1/conversations?project_id=proj-1")
        assert resp.status_code == 200
        data = resp.json()
        assert [c["conversation_id"] for c in data] == ["conv-a"]

    def test_list_archived_filters_by_project_and_exposes_id(
        self, client, mock_conversation_manager
    ):
        """``?project_id`` filters archived too; ``project_id`` is on the wire."""
        mock_conversation_manager.list_archived = AsyncMock(
            return_value=[
                ConversationSummary(
                    conversation_id="arch-a",
                    topic="t",
                    summary="s",
                    started_at=datetime(2026, 3, 1, tzinfo=UTC),
                    archived_at=datetime(2026, 3, 5, tzinfo=UTC),
                    message_count=4,
                    project_id="proj-1",
                ),
                ConversationSummary(
                    conversation_id="arch-b",
                    topic="t2",
                    summary="s2",
                    started_at=datetime(2026, 3, 2, tzinfo=UTC),
                    archived_at=datetime(2026, 3, 6, tzinfo=UTC),
                    message_count=2,
                    project_id="proj-2",
                ),
            ]
        )
        resp = client.get("/api/v1/conversations/archived?project_id=proj-1")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["conversation_id"] == "arch-a"
        assert data[0]["project_id"] == "proj-1"


class TestAppendMessage:
    def test_sends_message_and_gets_reply(self, client, mock_conversation_manager, mock_executor):
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
            "/api/v1/conversations/abc123def456789012345678abcdef00/messages",
            json={"message": "Hello"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["reply"] == "Hello back!"
        assert data["status"] == "completed"
        assert data["message_count"] == 2

    def test_empty_message_rejected(self, client):
        resp = client.post(
            "/api/v1/conversations/abc123def456789012345678abcdef00/messages",
            json={"message": "   "},
        )
        assert resp.status_code == 400

    @pytest.mark.spec("conversations.project_bound_conversation_routes_workdir_to_project_path")
    @pytest.mark.spec("cowork.conversation_with_project_id_routes_to_project_path")
    def test_runs_with_project_work_dir(
        self,
        client,
        mock_conversation_manager,
        mock_executor,
        mock_project_store,
    ):
        """When the conversation carries a ``project_id``, the executor
        receives the resolved project path as ``work_dir``."""
        from types import SimpleNamespace

        # Conversation is linked to project "proj-7".
        mock_conversation_manager.list_active = AsyncMock(
            return_value=[
                ConversationInfo(
                    conversation_id="abc123def456789012345678abcdef00",
                    channel="rest",
                    started_at=datetime(2026, 3, 18, tzinfo=UTC),
                    last_activity=datetime(2026, 3, 18, tzinfo=UTC),
                    message_count=1,
                    topic=None,
                    project_id="proj-7",
                )
            ]
        )
        mock_project_store.get = AsyncMock(
            return_value=SimpleNamespace(
                project_id="proj-7",
                name="TuttiPaletti",
                path="/srv/projects/tutti",
                created_at=datetime(2026, 3, 18, tzinfo=UTC),
            )
        )
        mock_conversation_manager.get_messages = AsyncMock(
            side_effect=[
                [{"role": "user", "content": "Hi"}],
                [
                    {"role": "user", "content": "Hi"},
                    {"role": "assistant", "content": "Hello back!"},
                ],
            ]
        )

        resp = client.post(
            "/api/v1/conversations/abc123def456789012345678abcdef00/messages",
            json={"message": "Hi"},
        )
        assert resp.status_code == 200
        # The executor must have been called with the project's path.
        _, kwargs = mock_executor.execute_mission.call_args
        assert kwargs["work_dir"] == "/srv/projects/tutti"
        # Project-scoped chats default to the ``default`` profile, not butler.
        # Butler underperforms on per-project work and aggressively delegates
        # to sub-agents instead of touching the workspace itself.
        assert kwargs["profile"] == "default"

    def test_deleted_project_falls_back_to_default_work_dir(
        self,
        client,
        mock_conversation_manager,
        mock_executor,
        mock_project_store,
    ):
        """Conversation references a project that was removed from the
        registry — the executor must still run, with ``work_dir=None`` so
        the profile's default work_dir is used."""
        mock_conversation_manager.list_active = AsyncMock(
            return_value=[
                ConversationInfo(
                    conversation_id="abc123def456789012345678abcdef00",
                    channel="rest",
                    started_at=datetime(2026, 3, 18, tzinfo=UTC),
                    last_activity=datetime(2026, 3, 18, tzinfo=UTC),
                    message_count=1,
                    topic=None,
                    project_id="ghost",
                )
            ]
        )
        mock_project_store.get = AsyncMock(return_value=None)
        mock_conversation_manager.get_messages = AsyncMock(
            side_effect=[
                [{"role": "user", "content": "Hi"}],
                [
                    {"role": "user", "content": "Hi"},
                    {"role": "assistant", "content": "Hello back!"},
                ],
            ]
        )

        resp = client.post(
            "/api/v1/conversations/abc123def456789012345678abcdef00/messages",
            json={"message": "Hi"},
        )
        assert resp.status_code == 200
        _, kwargs = mock_executor.execute_mission.call_args
        assert kwargs["work_dir"] is None

    @pytest.mark.spec("cowork.conversation_without_project_id_uses_global_workdir")
    def test_no_project_id_uses_default_work_dir(
        self,
        client,
        mock_conversation_manager,
        mock_executor,
        mock_project_store,
    ):
        """A conversation with no ``project_id`` runs with ``work_dir=None``.

        Project binding is strictly opt-in: an unbound conversation falls
        back to the profile's global work directory, and the project store
        is never consulted.
        """
        # Default fixture conversation carries no project_id.
        resp = client.post(
            "/api/v1/conversations/abc123def456789012345678abcdef00/messages",
            json={"message": "Hi"},
        )
        assert resp.status_code == 200
        _, kwargs = mock_executor.execute_mission.call_args
        assert kwargs["work_dir"] is None
        mock_project_store.get.assert_not_called()


class TestGetMessages:
    def test_returns_messages(self, client, mock_conversation_manager):
        mock_conversation_manager.get_messages = AsyncMock(
            return_value=[
                {"role": "user", "content": "Hi"},
                {"role": "assistant", "content": "Hello!"},
            ]
        )
        resp = client.get("/api/v1/conversations/abc123def456789012345678abcdef00/messages")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 2
        assert data[0]["role"] == "user"

    def test_returns_messages_with_limit(self, client, mock_conversation_manager):
        mock_conversation_manager.get_messages = AsyncMock(
            return_value=[{"role": "assistant", "content": "Last"}]
        )
        resp = client.get("/api/v1/conversations/abc123def456789012345678abcdef00/messages?limit=1")
        assert resp.status_code == 200
        mock_conversation_manager.get_messages.assert_called_once_with(
            "abc123def456789012345678abcdef00", 1
        )

    def test_unknown_conversation_returns_404(self, client):
        """A conversation_id outside the caller's scoped manager is 404 —
        the cross-tenant / cross-user ownership guard (#279). The mock
        manager's active + archived lists do not contain this id."""
        resp = client.get("/api/v1/conversations/not-my-conversation/messages")
        assert resp.status_code == 404
        assert "conversation_not_found" in resp.text


class TestArchiveConversation:
    def test_archive(self, client, mock_conversation_manager):
        resp = client.post(
            "/api/v1/conversations/abc123def456789012345678abcdef00/archive",
            json={"summary": "Done"},
        )
        assert resp.status_code == 204
        mock_conversation_manager.archive.assert_called_once_with(
            "abc123def456789012345678abcdef00", "Done"
        )

    def test_archive_without_summary(self, client, mock_conversation_manager):
        resp = client.post("/api/v1/conversations/abc123def456789012345678abcdef00/archive")
        assert resp.status_code == 204
        mock_conversation_manager.archive.assert_called_once_with(
            "abc123def456789012345678abcdef00", None
        )


class TestDeleteConversation:
    def test_delete_returns_204(self, client, mock_conversation_manager):
        resp = client.delete("/api/v1/conversations/abc123def456789012345678abcdef00")
        assert resp.status_code == 204
        mock_conversation_manager.delete.assert_awaited_once_with(
            "abc123def456789012345678abcdef00"
        )

    @pytest.mark.spec("conversations.delete_returns_404_when_missing")
    def test_delete_unknown_returns_404(self, client, mock_conversation_manager):
        mock_conversation_manager.delete = AsyncMock(return_value=False)
        resp = client.delete("/api/v1/conversations/ghost")
        assert resp.status_code == 404
        assert "conversation_not_found" in resp.text

    def test_delete_out_of_scope_id_blocked_before_delete(
        self, client, mock_conversation_manager
    ):
        """#279 — delete_conversation enforces the same ownership/scope check
        as the other conversation routes: an id outside the caller's scope
        404s and the manager's delete is never reached."""
        # This id is in neither list_active (only abc123...) nor list_archived.
        foreign_id = "ffffffffffffffffffffffffffffffff"
        resp = client.delete(f"/api/v1/conversations/{foreign_id}")
        assert resp.status_code == 404
        # The access check gated the route before the destructive delete ran.
        mock_conversation_manager.delete.assert_not_awaited()


class TestForkConversation:
    def test_forks_full_transcript(self, client, mock_conversation_manager):
        mock_conversation_manager.fork = AsyncMock(return_value=("new-conv-id", 2))
        resp = client.post(
            "/api/v1/conversations/abc123def456789012345678abcdef00/fork",
            json={"up_to_index": None, "channel": "rest"},
        )
        assert resp.status_code == 201
        body = resp.json()
        assert body["conversation_id"] == "new-conv-id"
        assert body["source_id"] == "abc123def456789012345678abcdef00"
        assert body["messages_copied"] == 2
        mock_conversation_manager.fork.assert_called_once()

    def test_forks_partial_transcript(self, client, mock_conversation_manager):
        mock_conversation_manager.fork = AsyncMock(return_value=("forked", 2))
        resp = client.post(
            "/api/v1/conversations/abc123def456789012345678abcdef00/fork",
            json={"up_to_index": 2},
        )
        assert resp.status_code == 201
        assert resp.json()["messages_copied"] == 2

    def test_messages_copied_is_actual_count_not_request(self, client, mock_conversation_manager):
        """``up_to_index`` may exceed the source length; reported count must
        be what was actually copied."""
        mock_conversation_manager.fork = AsyncMock(return_value=("forked", 3))
        resp = client.post(
            "/api/v1/conversations/abc123def456789012345678abcdef00/fork",
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

    @pytest.mark.spec("conversations.compact_returns_404_for_unknown_id")
    def test_returns_404_for_unknown_conversation(self, client, mock_conversation_manager):
        # No active conversations match the id; existence check fails.
        mock_conversation_manager.get_messages = AsyncMock(return_value=[])
        mock_conversation_manager.list_active = AsyncMock(return_value=[])

        resp = client.post(
            "/api/v1/conversations/does-not-exist/compact",
            json={},
        )
        assert resp.status_code == 404
        assert "conversation_not_found" in resp.text

    def test_skipped_status_passes_through(self, client, mock_conversation_manager, monkeypatch):
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
