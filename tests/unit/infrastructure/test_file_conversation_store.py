"""Tests for FileConversationStore — file-based conversation management."""

import pytest

from taskforce.infrastructure.persistence.file_conversation_store import (
    FileConversationStore,
)


class TestFileConversationStore:
    @pytest.fixture
    def store(self, tmp_path):
        return FileConversationStore(work_dir=str(tmp_path))

    async def test_get_or_create_returns_new_id(self, store):
        conv_id = await store.get_or_create("cli")
        assert conv_id
        assert len(conv_id) == 32  # uuid hex

    async def test_get_or_create_returns_same_active(self, store):
        id1 = await store.get_or_create("cli")
        id2 = await store.get_or_create("cli")
        assert id1 == id2

    async def test_get_or_create_different_channels(self, store):
        id_cli = await store.get_or_create("cli")
        id_tg = await store.get_or_create("telegram")
        assert id_cli != id_tg

    async def test_create_new_archives_previous(self, store):
        id1 = await store.get_or_create("cli")
        id2 = await store.create_new("cli")
        assert id1 != id2

        active = await store.list_active()
        active_ids = [c.conversation_id for c in active]
        assert id2 in active_ids
        assert id1 not in active_ids

        archived = await store.list_archived()
        archived_ids = [c.conversation_id for c in archived]
        assert id1 in archived_ids

    async def test_append_and_get_messages(self, store):
        conv_id = await store.get_or_create("cli")
        await store.append_message(conv_id, {"role": "user", "content": "Hello"})
        await store.append_message(conv_id, {"role": "assistant", "content": "Hi!"})

        messages = await store.get_messages(conv_id)
        assert len(messages) == 2
        assert messages[0]["content"] == "Hello"
        assert messages[1]["content"] == "Hi!"

    async def test_get_messages_with_limit(self, store):
        conv_id = await store.get_or_create("cli")
        for i in range(5):
            await store.append_message(conv_id, {"role": "user", "content": f"msg-{i}"})

        messages = await store.get_messages(conv_id, limit=2)
        assert len(messages) == 2
        assert messages[0]["content"] == "msg-3"
        assert messages[1]["content"] == "msg-4"

    async def test_archive_conversation(self, store):
        conv_id = await store.get_or_create("cli")
        await store.archive(conv_id, summary="Test conversation about X")

        active = await store.list_active()
        assert all(c.conversation_id != conv_id for c in active)

        archived = await store.list_archived()
        assert len(archived) == 1
        assert archived[0].conversation_id == conv_id
        assert archived[0].summary == "Test conversation about X"

    async def test_list_active_ordered_by_activity(self, store):
        id1 = await store.get_or_create("cli")
        id2 = await store.get_or_create("telegram")
        # Append message to id1 to make it more recent.
        await store.append_message(id1, {"role": "user", "content": "recent"})

        active = await store.list_active()
        assert len(active) == 2
        assert active[0].conversation_id == id1  # Most recent activity.

    async def test_message_count_updates(self, store):
        conv_id = await store.get_or_create("cli")
        await store.append_message(conv_id, {"role": "user", "content": "msg"})
        await store.append_message(conv_id, {"role": "user", "content": "msg2"})

        active = await store.list_active()
        conv = next(c for c in active if c.conversation_id == conv_id)
        assert conv.message_count == 2

    async def test_sender_id_isolation(self, store):
        id_a = await store.get_or_create("telegram", sender_id="user_a")
        id_b = await store.get_or_create("telegram", sender_id="user_b")
        assert id_a != id_b

        # Same sender gets same conversation.
        id_a2 = await store.get_or_create("telegram", sender_id="user_a")
        assert id_a == id_a2
