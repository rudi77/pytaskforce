import pytest

from taskforce_extensions.infrastructure.communication.conversation_store import (
    FileConversationStore,
    InMemoryConversationStore,
)


@pytest.mark.asyncio
async def test_in_memory_store_persists_history() -> None:
    store = InMemoryConversationStore()
    await store.set_session_id("telegram", "conv-1", "session-123")
    await store.save_history(
        "telegram",
        "conv-1",
        [{"role": "user", "content": "hello"}],
    )

    session_id = await store.get_session_id("telegram", "conv-1")
    history = await store.load_history("telegram", "conv-1")

    assert session_id == "session-123"
    assert history == [{"role": "user", "content": "hello"}]


@pytest.mark.asyncio
async def test_file_store_round_trip(tmp_path) -> None:
    store = FileConversationStore(work_dir=str(tmp_path))
    await store.set_session_id("teams", "conv-99", "session-abc")
    await store.save_history(
        "teams",
        "conv-99",
        [{"role": "assistant", "content": "hi"}],
    )

    reloaded = FileConversationStore(work_dir=str(tmp_path))
    session_id = await reloaded.get_session_id("teams", "conv-99")
    history = await reloaded.load_history("teams", "conv-99")

    assert session_id == "session-abc"
    assert history == [{"role": "assistant", "content": "hi"}]
