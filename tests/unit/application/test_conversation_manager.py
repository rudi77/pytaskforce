"""Tests for ConversationManager — application-layer conversation orchestration."""

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock

import pytest

from taskforce.application.conversation_manager import ConversationManager
from taskforce.core.interfaces.conversation import ConversationInfo


class TestConversationManager:
    @pytest.fixture
    def mock_store(self):
        store = AsyncMock()
        store.get_or_create = AsyncMock(return_value="conv-123")
        store.create_new = AsyncMock(return_value="conv-456")
        store.list_active = AsyncMock(return_value=[])
        store.list_archived = AsyncMock(return_value=[])
        store.append_message = AsyncMock()
        store.get_messages = AsyncMock(return_value=[])
        store.archive = AsyncMock()
        return store

    @pytest.fixture
    def manager(self, mock_store):
        return ConversationManager(mock_store, inactivity_threshold_hours=24)

    async def test_get_or_create_delegates(self, manager, mock_store):
        result = await manager.get_or_create("cli")
        assert result == "conv-123"
        mock_store.get_or_create.assert_called_once_with("cli", None, None)

    async def test_create_new_delegates(self, manager, mock_store):
        result = await manager.create_new("telegram", sender_id="user_a")
        assert result == "conv-456"
        mock_store.create_new.assert_called_once_with("telegram", "user_a", None)

    async def test_create_new_with_project_id(self, manager, mock_store):
        result = await manager.create_new(
            "rest", sender_id=None, project_id="proj-7"
        )
        assert result == "conv-456"
        mock_store.create_new.assert_called_once_with("rest", None, "proj-7")

    async def test_append_message_delegates(self, manager, mock_store):
        msg = {"role": "user", "content": "Hello"}
        await manager.append_message("conv-123", msg)
        mock_store.append_message.assert_called_once_with("conv-123", msg)

    async def test_auto_archive_stale_conversations(self, mock_store):
        stale_time = datetime.now(UTC) - timedelta(hours=25)
        mock_store.list_active = AsyncMock(
            return_value=[
                ConversationInfo(
                    conversation_id="old-conv",
                    channel="cli",
                    started_at=stale_time,
                    last_activity=stale_time,
                    message_count=5,
                ),
            ]
        )
        manager = ConversationManager(mock_store, inactivity_threshold_hours=24)
        await manager.get_or_create("cli")

        mock_store.archive.assert_called_once_with("old-conv")

    async def test_fork_preserves_tool_calls_and_strips_volatile_fields(
        self, manager, mock_store
    ):
        """Fork must keep tool_calls / tool_call_id / name and drop volatile ids."""
        mock_store.get_messages = AsyncMock(
            return_value=[
                {
                    "role": "user",
                    "content": "weather?",
                    "message_id": "msg-1",
                    "timestamp": "2026-04-29T10:00:00Z",
                },
                {
                    "role": "assistant",
                    "content": "",
                    "tool_calls": [{"id": "call-1", "name": "weather"}],
                    "message_id": "msg-2",
                    "created_at": "2026-04-29T10:00:01Z",
                    "conversation_id": "old-id",
                },
                {
                    "role": "tool",
                    "tool_call_id": "call-1",
                    "name": "weather",
                    "content": "sunny",
                    "message_id": "msg-3",
                },
            ]
        )
        mock_store.create_new = AsyncMock(return_value="new-conv")

        new_id, copied = await manager.fork("source", up_to_index=None)

        assert new_id == "new-conv"
        assert copied == 3
        # Three append calls — capture the payload of each.
        calls = mock_store.append_message.call_args_list
        assert len(calls) == 3
        forwarded = [args.args[1] for args in calls]
        # Tool linkage preserved on assistant + tool turns.
        assert forwarded[1]["tool_calls"] == [{"id": "call-1", "name": "weather"}]
        assert forwarded[2]["tool_call_id"] == "call-1"
        assert forwarded[2]["name"] == "weather"
        # Volatile fields stripped on every payload.
        for payload in forwarded:
            assert "message_id" not in payload
            assert "timestamp" not in payload
            assert "created_at" not in payload
            assert "conversation_id" not in payload

    async def test_fork_clamps_oversized_up_to_index(self, manager, mock_store):
        mock_store.get_messages = AsyncMock(
            return_value=[{"role": "user", "content": str(i)} for i in range(3)]
        )
        mock_store.create_new = AsyncMock(return_value="new-id")

        _, copied = await manager.fork("source", up_to_index=999)
        assert copied == 3

    async def test_no_archive_of_recent_conversations(self, mock_store):
        recent_time = datetime.now(UTC) - timedelta(hours=1)
        mock_store.list_active = AsyncMock(
            return_value=[
                ConversationInfo(
                    conversation_id="recent-conv",
                    channel="cli",
                    started_at=recent_time,
                    last_activity=recent_time,
                    message_count=2,
                ),
            ]
        )
        manager = ConversationManager(mock_store, inactivity_threshold_hours=24)
        await manager.get_or_create("cli")

        mock_store.archive.assert_not_called()


class TestConversationManagerCompact:
    """Tests for the Cowork-style ``/compact`` operation."""

    @pytest.fixture
    def mock_store(self):
        store = AsyncMock()
        store.replace_messages = AsyncMock()
        return store

    @pytest.fixture
    def manager(self, mock_store):
        return ConversationManager(mock_store)

    async def test_compact_skips_when_below_threshold(self, manager, mock_store):
        # 4 kept + 1 summary slot = 5 messages minimum to compact; 4 messages
        # is too few — must skip without calling the summarizer.
        mock_store.get_messages = AsyncMock(
            return_value=[
                {"role": "user", "content": "hi"},
                {"role": "assistant", "content": "hello"},
                {"role": "user", "content": "again"},
                {"role": "assistant", "content": "yes"},
            ]
        )
        summarizer = AsyncMock()

        result = await manager.compact("conv-1", summarizer, keep_last_n=4)

        assert result["status"] == "skipped"
        assert result["reason"] == "below_threshold"
        assert result["messages"] == 4
        summarizer.assert_not_awaited()
        mock_store.replace_messages.assert_not_awaited()

    async def test_compact_summarizes_and_replaces(self, manager, mock_store):
        # 10 messages, keep last 4 → summarize the first 6.
        original = [
            {"role": "user", "content": f"msg {i}"} for i in range(10)
        ]
        mock_store.get_messages = AsyncMock(return_value=original)

        async def fake_summary(msgs):
            assert len(msgs) == 6
            return "concise summary of the early back-and-forth"

        result = await manager.compact("conv-1", fake_summary, keep_last_n=4)

        assert result["status"] == "compacted"
        assert result["summarized"] == 6
        assert result["kept"] == 4
        assert "concise summary" in result["summary_preview"]

        # Store was rewritten with [summary, ...last_4_originals].
        mock_store.replace_messages.assert_awaited_once()
        _conv_id, new_messages = mock_store.replace_messages.await_args.args
        assert _conv_id == "conv-1"
        assert len(new_messages) == 5  # 1 summary + 4 kept
        assert new_messages[0]["role"] == "system"
        assert "Compacted summary of 6 earlier messages" in new_messages[0]["content"]
        assert "concise summary" in new_messages[0]["content"]
        # Tail messages preserved verbatim, in order.
        assert [m["content"] for m in new_messages[1:]] == [
            "msg 6",
            "msg 7",
            "msg 8",
            "msg 9",
        ]

    async def test_compact_with_keep_last_n_zero_summarizes_everything(
        self, manager, mock_store
    ):
        original = [{"role": "user", "content": f"m{i}"} for i in range(8)]
        mock_store.get_messages = AsyncMock(return_value=original)

        async def fake_summary(msgs):
            assert len(msgs) == 8
            return "all of it"

        result = await manager.compact("conv-1", fake_summary, keep_last_n=0)

        assert result["status"] == "compacted"
        assert result["summarized"] == 8
        assert result["kept"] == 0

        _conv_id, new_messages = mock_store.replace_messages.await_args.args
        assert len(new_messages) == 1  # just the summary
        assert "all of it" in new_messages[0]["content"]

    async def test_compact_refuses_empty_summary(self, manager, mock_store):
        # Defence against silently destroying history when the LLM call
        # returns nothing usable.
        mock_store.get_messages = AsyncMock(
            return_value=[{"role": "user", "content": str(i)} for i in range(10)]
        )

        async def empty_summary(_msgs):
            return "   "  # whitespace only

        with pytest.raises(RuntimeError, match="empty content"):
            await manager.compact("conv-1", empty_summary, keep_last_n=4)
        mock_store.replace_messages.assert_not_awaited()

    async def test_replace_messages_delegates(self, manager, mock_store):
        await manager.replace_messages(
            "conv-1", [{"role": "system", "content": "x"}]
        )
        mock_store.replace_messages.assert_awaited_once_with(
            "conv-1", [{"role": "system", "content": "x"}]
        )
