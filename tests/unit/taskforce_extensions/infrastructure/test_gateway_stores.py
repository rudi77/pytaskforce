"""Tests for gateway conversation store and recipient registry."""

import pytest

from taskforce_extensions.infrastructure.communication.gateway_conversation_store import (
    FileConversationStore,
    InMemoryConversationStore,
)
from taskforce_extensions.infrastructure.communication.recipient_registry import (
    FileRecipientRegistry,
    InMemoryRecipientRegistry,
)


# ------------------------------------------------------------------
# ConversationStore tests
# ------------------------------------------------------------------


class TestInMemoryConversationStore:
    @pytest.mark.asyncio
    async def test_session_id_round_trip(self) -> None:
        store = InMemoryConversationStore()
        await store.set_session_id("telegram", "conv-1", "sess-abc")
        result = await store.get_session_id("telegram", "conv-1")
        assert result == "sess-abc"

    @pytest.mark.asyncio
    async def test_get_session_id_returns_none_if_missing(self) -> None:
        store = InMemoryConversationStore()
        assert await store.get_session_id("telegram", "nonexistent") is None

    @pytest.mark.asyncio
    async def test_history_round_trip(self) -> None:
        store = InMemoryConversationStore()
        await store.set_session_id("telegram", "conv-1", "sess-abc")
        history = [{"role": "user", "content": "hello"}]
        await store.save_history("telegram", "conv-1", history)
        loaded = await store.load_history("telegram", "conv-1")
        assert loaded == history

    @pytest.mark.asyncio
    async def test_save_history_requires_session_id(self) -> None:
        store = InMemoryConversationStore()
        with pytest.raises(ValueError, match="session_id must be set"):
            await store.save_history("telegram", "conv-1", [{"role": "user", "content": "hi"}])

    @pytest.mark.asyncio
    async def test_channels_are_isolated(self) -> None:
        store = InMemoryConversationStore()
        await store.set_session_id("telegram", "conv-1", "sess-tg")
        await store.set_session_id("teams", "conv-1", "sess-teams")
        assert await store.get_session_id("telegram", "conv-1") == "sess-tg"
        assert await store.get_session_id("teams", "conv-1") == "sess-teams"


class TestFileConversationStore:
    @pytest.mark.asyncio
    async def test_session_id_round_trip(self, tmp_path) -> None:
        store = FileConversationStore(work_dir=str(tmp_path))
        await store.set_session_id("telegram", "conv-1", "sess-abc")
        result = await store.get_session_id("telegram", "conv-1")
        assert result == "sess-abc"

    @pytest.mark.asyncio
    async def test_history_survives_reload(self, tmp_path) -> None:
        store = FileConversationStore(work_dir=str(tmp_path))
        await store.set_session_id("teams", "conv-99", "sess-xyz")
        await store.save_history("teams", "conv-99", [{"role": "assistant", "content": "hi"}])

        reloaded = FileConversationStore(work_dir=str(tmp_path))
        session_id = await reloaded.get_session_id("teams", "conv-99")
        history = await reloaded.load_history("teams", "conv-99")
        assert session_id == "sess-xyz"
        assert history == [{"role": "assistant", "content": "hi"}]


# ------------------------------------------------------------------
# RecipientRegistry tests
# ------------------------------------------------------------------


class TestInMemoryRecipientRegistry:
    @pytest.mark.asyncio
    async def test_register_and_resolve(self) -> None:
        registry = InMemoryRecipientRegistry()
        await registry.register(
            channel="telegram",
            user_id="user-1",
            reference={"chat_id": "12345"},
        )
        ref = await registry.resolve(channel="telegram", user_id="user-1")
        assert ref == {"chat_id": "12345"}

    @pytest.mark.asyncio
    async def test_resolve_returns_none_if_missing(self) -> None:
        registry = InMemoryRecipientRegistry()
        assert await registry.resolve(channel="telegram", user_id="none") is None

    @pytest.mark.asyncio
    async def test_list_recipients(self) -> None:
        registry = InMemoryRecipientRegistry()
        await registry.register(channel="telegram", user_id="a", reference={"chat_id": "1"})
        await registry.register(channel="telegram", user_id="b", reference={"chat_id": "2"})
        recipients = await registry.list_recipients("telegram")
        assert set(recipients) == {"a", "b"}

    @pytest.mark.asyncio
    async def test_remove(self) -> None:
        registry = InMemoryRecipientRegistry()
        await registry.register(channel="telegram", user_id="user-1", reference={"chat_id": "1"})
        assert await registry.remove(channel="telegram", user_id="user-1")
        assert await registry.resolve(channel="telegram", user_id="user-1") is None
        assert not await registry.remove(channel="telegram", user_id="user-1")

    @pytest.mark.asyncio
    async def test_channels_are_isolated(self) -> None:
        registry = InMemoryRecipientRegistry()
        await registry.register(channel="telegram", user_id="u1", reference={"chat_id": "tg1"})
        await registry.register(channel="teams", user_id="u1", reference={"ref": "teams1"})
        tg = await registry.resolve(channel="telegram", user_id="u1")
        teams = await registry.resolve(channel="teams", user_id="u1")
        assert tg == {"chat_id": "tg1"}
        assert teams == {"ref": "teams1"}


class TestFileRecipientRegistry:
    @pytest.mark.asyncio
    async def test_register_and_resolve(self, tmp_path) -> None:
        registry = FileRecipientRegistry(work_dir=str(tmp_path))
        await registry.register(
            channel="telegram",
            user_id="user-42",
            reference={"chat_id": "42"},
        )
        ref = await registry.resolve(channel="telegram", user_id="user-42")
        assert ref == {"chat_id": "42"}

    @pytest.mark.asyncio
    async def test_list_recipients(self, tmp_path) -> None:
        registry = FileRecipientRegistry(work_dir=str(tmp_path))
        await registry.register(channel="telegram", user_id="a", reference={})
        await registry.register(channel="telegram", user_id="b", reference={})
        recipients = await registry.list_recipients("telegram")
        assert set(recipients) == {"a", "b"}

    @pytest.mark.asyncio
    async def test_remove(self, tmp_path) -> None:
        registry = FileRecipientRegistry(work_dir=str(tmp_path))
        await registry.register(channel="telegram", user_id="user-1", reference={"x": 1})
        assert await registry.remove(channel="telegram", user_id="user-1")
        assert await registry.resolve(channel="telegram", user_id="user-1") is None

    @pytest.mark.asyncio
    async def test_survives_reload(self, tmp_path) -> None:
        reg1 = FileRecipientRegistry(work_dir=str(tmp_path))
        await reg1.register(channel="telegram", user_id="u1", reference={"chat_id": "100"})
        reg2 = FileRecipientRegistry(work_dir=str(tmp_path))
        ref = await reg2.resolve(channel="telegram", user_id="u1")
        assert ref == {"chat_id": "100"}
