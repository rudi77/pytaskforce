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
        mock_store.get_or_create.assert_called_once_with("cli", None)

    async def test_create_new_delegates(self, manager, mock_store):
        result = await manager.create_new("telegram", sender_id="user_a")
        assert result == "conv-456"
        mock_store.create_new.assert_called_once_with("telegram", "user_a")

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
