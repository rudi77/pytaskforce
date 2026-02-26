"""Tests for FilePendingChannelQuestionStore.

Verifies file-based tracking of pending channel questions including
registration, resolution, response retrieval, and cleanup.
"""

import pytest

from taskforce.infrastructure.persistence.pending_channel_store import (
    FilePendingChannelQuestionStore,
)


@pytest.fixture
def store(tmp_path):
    """Create a store backed by a temporary directory."""
    return FilePendingChannelQuestionStore(work_dir=str(tmp_path))


class TestRegisterAndRetrieve:
    """Test registering and retrieving pending questions."""

    @pytest.mark.asyncio
    async def test_register_creates_session_file(self, store, tmp_path):
        await store.register(
            session_id="sess-1",
            channel="telegram",
            recipient_id="user-42",
            question="What is the invoice date?",
        )

        path = tmp_path / "pending_channel_questions" / "sess-1.json"
        assert path.exists()

    @pytest.mark.asyncio
    async def test_get_response_returns_none_before_resolve(self, store):
        await store.register(
            session_id="sess-1",
            channel="telegram",
            recipient_id="user-42",
            question="What is the invoice date?",
        )

        response = await store.get_response(session_id="sess-1")
        assert response is None

    @pytest.mark.asyncio
    async def test_get_response_for_unknown_session(self, store):
        response = await store.get_response(session_id="nonexistent")
        assert response is None


class TestResolve:
    """Test resolving pending questions with inbound responses."""

    @pytest.mark.asyncio
    async def test_resolve_returns_session_id(self, store):
        await store.register(
            session_id="sess-1",
            channel="telegram",
            recipient_id="user-42",
            question="Missing tax number?",
        )

        result = await store.resolve(
            channel="telegram",
            sender_id="user-42",
            response="DE123456789",
        )

        assert result == "sess-1"

    @pytest.mark.asyncio
    async def test_resolve_stores_response(self, store):
        await store.register(
            session_id="sess-1",
            channel="telegram",
            recipient_id="user-42",
            question="Missing date?",
        )

        await store.resolve(
            channel="telegram",
            sender_id="user-42",
            response="2026-01-15",
        )

        response = await store.get_response(session_id="sess-1")
        assert response == "2026-01-15"

    @pytest.mark.asyncio
    async def test_resolve_no_pending_question(self, store):
        result = await store.resolve(
            channel="telegram",
            sender_id="unknown-user",
            response="Some answer",
        )
        assert result is None

    @pytest.mark.asyncio
    async def test_resolve_wrong_channel(self, store):
        await store.register(
            session_id="sess-1",
            channel="telegram",
            recipient_id="user-42",
            question="Missing date?",
        )

        result = await store.resolve(
            channel="teams",
            sender_id="user-42",
            response="2026-01-15",
        )
        assert result is None

    @pytest.mark.asyncio
    async def test_resolve_already_resolved(self, store):
        await store.register(
            session_id="sess-1",
            channel="telegram",
            recipient_id="user-42",
            question="Missing date?",
        )

        first = await store.resolve(
            channel="telegram",
            sender_id="user-42",
            response="2026-01-15",
        )
        assert first == "sess-1"

        # Second resolve for the same question should return None
        second = await store.resolve(
            channel="telegram",
            sender_id="user-42",
            response="2026-02-01",
        )
        assert second is None


class TestRemove:
    """Test removing pending questions."""

    @pytest.mark.asyncio
    async def test_remove_deletes_session_file(self, store, tmp_path):
        await store.register(
            session_id="sess-1",
            channel="telegram",
            recipient_id="user-42",
            question="What is the date?",
        )

        await store.remove(session_id="sess-1")

        path = tmp_path / "pending_channel_questions" / "sess-1.json"
        assert not path.exists()

    @pytest.mark.asyncio
    async def test_remove_cleans_index(self, store):
        await store.register(
            session_id="sess-1",
            channel="telegram",
            recipient_id="user-42",
            question="What is the date?",
        )

        await store.remove(session_id="sess-1")

        # After removal a new question from the same user should not resolve
        result = await store.resolve(
            channel="telegram",
            sender_id="user-42",
            response="Some answer",
        )
        assert result is None

    @pytest.mark.asyncio
    async def test_remove_nonexistent_session(self, store):
        # Should not raise
        await store.remove(session_id="nonexistent")

    @pytest.mark.asyncio
    async def test_get_response_after_remove(self, store):
        await store.register(
            session_id="sess-1",
            channel="telegram",
            recipient_id="user-42",
            question="What is the date?",
        )

        await store.remove(session_id="sess-1")

        response = await store.get_response(session_id="sess-1")
        assert response is None


class TestMultipleSessions:
    """Test concurrent pending questions from different sessions."""

    @pytest.mark.asyncio
    async def test_multiple_pending_questions(self, store):
        await store.register(
            session_id="sess-1",
            channel="telegram",
            recipient_id="user-A",
            question="Invoice date?",
        )
        await store.register(
            session_id="sess-2",
            channel="telegram",
            recipient_id="user-B",
            question="Tax number?",
        )

        result_b = await store.resolve(
            channel="telegram", sender_id="user-B", response="DE111"
        )
        assert result_b == "sess-2"

        result_a = await store.resolve(
            channel="telegram", sender_id="user-A", response="2026-01-01"
        )
        assert result_a == "sess-1"

    @pytest.mark.asyncio
    async def test_same_user_different_channels(self, store):
        await store.register(
            session_id="sess-1",
            channel="telegram",
            recipient_id="user-X",
            question="Question via telegram",
        )
        await store.register(
            session_id="sess-2",
            channel="teams",
            recipient_id="user-X",
            question="Question via teams",
        )

        result_tg = await store.resolve(
            channel="telegram", sender_id="user-X", response="TG answer"
        )
        assert result_tg == "sess-1"

        result_teams = await store.resolve(
            channel="teams", sender_id="user-X", response="Teams answer"
        )
        assert result_teams == "sess-2"

    @pytest.mark.asyncio
    async def test_register_overwrites_previous_for_same_recipient(self, store):
        """If the same recipient gets a new question, it replaces the old one."""
        await store.register(
            session_id="sess-old",
            channel="telegram",
            recipient_id="user-42",
            question="Old question",
        )
        await store.register(
            session_id="sess-new",
            channel="telegram",
            recipient_id="user-42",
            question="New question",
        )

        result = await store.resolve(
            channel="telegram", sender_id="user-42", response="Answer"
        )
        assert result == "sess-new"


class TestMetadata:
    """Test metadata handling."""

    @pytest.mark.asyncio
    async def test_register_with_metadata(self, store):
        await store.register(
            session_id="sess-1",
            channel="telegram",
            recipient_id="user-42",
            question="Missing fields?",
            metadata={"missing_fields": ["date", "tax_number"]},
        )

        # Registration should succeed — verify via resolve
        result = await store.resolve(
            channel="telegram", sender_id="user-42", response="Here you go"
        )
        assert result == "sess-1"


class TestEdgeCases:
    """Test edge cases and robustness."""

    @pytest.mark.asyncio
    async def test_session_id_with_special_chars(self, store):
        await store.register(
            session_id="sess/with\\special",
            channel="telegram",
            recipient_id="user-42",
            question="Test?",
        )

        result = await store.resolve(
            channel="telegram", sender_id="user-42", response="Answer"
        )
        assert result == "sess/with\\special"

        response = await store.get_response(session_id="sess/with\\special")
        assert response == "Answer"
