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
        result = await manager.create_new("rest", sender_id=None, project_id="proj-7")
        assert result == "conv-456"
        mock_store.create_new.assert_called_once_with("rest", None, "proj-7")

    async def test_append_message_delegates(self, manager, mock_store):
        msg = {"role": "user", "content": "Hello"}
        await manager.append_message("conv-123", msg)
        mock_store.append_message.assert_called_once_with("conv-123", msg)

    @pytest.mark.spec("conversations.auto_archive_stale_on_get_or_create")
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

    @pytest.mark.spec("conversations.fork_copies_messages_and_strips_volatile_fields")
    @pytest.mark.spec("conversations.fork_preserves_tool_call_linkage")
    async def test_fork_preserves_tool_calls_and_strips_volatile_fields(self, manager, mock_store):
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

    @pytest.mark.spec("conversations.compact_below_threshold_is_noop")
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
        original = [{"role": "user", "content": f"msg {i}"} for i in range(10)]
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

    async def test_compact_with_keep_last_n_zero_summarizes_everything(self, manager, mock_store):
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

    @pytest.mark.spec("conversations.compact_rejects_empty_summary")
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
        await manager.replace_messages("conv-1", [{"role": "system", "content": "x"}])
        mock_store.replace_messages.assert_awaited_once_with(
            "conv-1", [{"role": "system", "content": "x"}]
        )


class TestConversationManagerRename:
    """Tests for the user-facing rename operation (PATCH route)."""

    @pytest.fixture
    def mock_store(self):
        store = AsyncMock()
        store.update_title = AsyncMock(return_value=True)
        return store

    @pytest.fixture
    def manager(self, mock_store):
        return ConversationManager(mock_store)

    @pytest.mark.spec("conversations.rename_updates_topic_for_active_and_archived")
    async def test_rename_normalizes_and_persists(self, manager, mock_store):
        ok = await manager.rename("conv-1", "  Hello   world\n")
        assert ok is True
        # Whitespace collapsed to single spaces, ends trimmed.
        mock_store.update_title.assert_awaited_once_with("conv-1", "Hello world")

    @pytest.mark.spec("conversations.rename_rejects_empty_or_oversized_title")
    async def test_rename_rejects_empty_title(self, manager, mock_store):
        with pytest.raises(ValueError, match="empty"):
            await manager.rename("conv-1", "")
        with pytest.raises(ValueError, match="empty"):
            await manager.rename("conv-1", "   \n\t  ")
        mock_store.update_title.assert_not_awaited()

    @pytest.mark.spec("conversations.rename_rejects_empty_or_oversized_title")
    async def test_rename_rejects_oversized_title(self, manager, mock_store):
        with pytest.raises(ValueError, match="too_long"):
            await manager.rename("conv-1", "x" * 81)
        mock_store.update_title.assert_not_awaited()

    @pytest.mark.spec("conversations.rename_returns_404_when_missing")
    async def test_rename_returns_false_when_unknown(self, manager, mock_store):
        mock_store.update_title = AsyncMock(return_value=False)
        ok = await manager.rename("missing", "Some title")
        assert ok is False


class TestConversationManagerAutoTitle:
    """Tests for ``maybe_generate_title`` (auto-titling on first turn)."""

    @staticmethod
    def _make_info(*, message_count: int, topic: str | None) -> ConversationInfo:
        now = datetime.now(UTC)
        return ConversationInfo(
            conversation_id="conv-1",
            channel="rest",
            started_at=now,
            last_activity=now,
            message_count=message_count,
            topic=topic,
        )

    @pytest.fixture
    def mock_store(self):
        store = AsyncMock()
        store.update_title = AsyncMock(return_value=True)
        store.get_messages = AsyncMock(
            return_value=[
                {"role": "user", "content": "When is the next VAT deadline?"},
                {"role": "assistant", "content": "April 15 in Austria."},
            ]
        )
        return store

    @pytest.fixture
    def manager(self, mock_store):
        return ConversationManager(mock_store)

    @pytest.mark.spec("conversations.auto_title_generated_after_first_assistant_reply")
    async def test_generates_and_persists_title(self, manager, mock_store):
        mock_store.list_active = AsyncMock(
            return_value=[self._make_info(message_count=2, topic=None)]
        )

        async def summarizer(_msgs, _system_prompt):
            return "VAT deadline question"

        title = await manager.maybe_generate_title("conv-1", summarizer)

        assert title == "VAT deadline question"
        mock_store.update_title.assert_awaited_once_with("conv-1", "VAT deadline question")

    @pytest.mark.spec("conversations.auto_title_does_not_overwrite_existing_topic")
    async def test_skips_when_topic_already_set(self, manager, mock_store):
        mock_store.list_active = AsyncMock(
            return_value=[self._make_info(message_count=2, topic="User chose this")]
        )
        summarizer = AsyncMock()

        title = await manager.maybe_generate_title("conv-1", summarizer)

        assert title is None
        summarizer.assert_not_awaited()
        mock_store.update_title.assert_not_awaited()

    async def test_skips_when_too_few_messages(self, manager, mock_store):
        mock_store.list_active = AsyncMock(
            return_value=[self._make_info(message_count=1, topic=None)]
        )
        summarizer = AsyncMock()

        title = await manager.maybe_generate_title("conv-1", summarizer)

        assert title is None
        summarizer.assert_not_awaited()

    @pytest.mark.spec("conversations.auto_title_failure_does_not_break_chat_reply")
    async def test_summarizer_failure_is_swallowed(self, manager, mock_store):
        mock_store.list_active = AsyncMock(
            return_value=[self._make_info(message_count=2, topic=None)]
        )

        async def boom(_msgs, _system_prompt):
            raise RuntimeError("LLM down")

        title = await manager.maybe_generate_title("conv-1", boom)

        assert title is None
        mock_store.update_title.assert_not_awaited()

    async def test_truncates_oversized_summary(self, manager, mock_store):
        mock_store.list_active = AsyncMock(
            return_value=[self._make_info(message_count=2, topic=None)]
        )

        async def long_summary(_msgs, _system_prompt):
            return "x" * 200

        title = await manager.maybe_generate_title("conv-1", long_summary)

        assert title is not None
        assert len(title) == ConversationManager.TITLE_MAX_LENGTH
        mock_store.update_title.assert_awaited_once()

    async def test_skips_when_summarizer_returns_blank(self, manager, mock_store):
        mock_store.list_active = AsyncMock(
            return_value=[self._make_info(message_count=2, topic=None)]
        )

        async def blank(_msgs, _system_prompt):
            return "   \n  "

        title = await manager.maybe_generate_title("conv-1", blank)

        assert title is None
        mock_store.update_title.assert_not_awaited()
