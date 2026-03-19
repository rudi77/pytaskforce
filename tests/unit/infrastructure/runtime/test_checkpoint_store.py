"""Unit tests for FileCheckpointStore and InMemoryCheckpointStore."""

from datetime import datetime, timezone

from taskforce.core.domain.runtime import CheckpointRecord
from taskforce.infrastructure.runtime.checkpoint_store import (
    FileCheckpointStore,
    InMemoryCheckpointStore,
)


def _make_checkpoint(
    session_id: str = "sess-1",
    checkpoint_id: str = "cp-1",
    ts: datetime | None = None,
) -> CheckpointRecord:
    return CheckpointRecord(
        session_id=session_id,
        checkpoint_id=checkpoint_id,
        state={"step": 5, "mission": "test"},
        timestamp=ts or datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc),
    )


# --- FileCheckpointStore ---


async def test_file_save_and_latest(tmp_path):
    store = FileCheckpointStore(work_dir=str(tmp_path))
    await store.save(_make_checkpoint())

    latest = await store.latest("sess-1")
    assert latest is not None
    assert latest.checkpoint_id == "cp-1"
    assert latest.state == {"step": 5, "mission": "test"}


async def test_file_latest_returns_most_recent(tmp_path):
    store = FileCheckpointStore(work_dir=str(tmp_path))
    early = datetime(2026, 1, 1, 10, 0, 0, tzinfo=timezone.utc)
    late = datetime(2026, 1, 1, 14, 0, 0, tzinfo=timezone.utc)

    await store.save(_make_checkpoint(checkpoint_id="cp-old", ts=early))
    await store.save(_make_checkpoint(checkpoint_id="cp-new", ts=late))

    latest = await store.latest("sess-1")
    assert latest is not None
    assert latest.checkpoint_id == "cp-new"


async def test_file_latest_nonexistent_returns_none(tmp_path):
    store = FileCheckpointStore(work_dir=str(tmp_path))
    assert await store.latest("nonexistent") is None


async def test_file_list_checkpoints(tmp_path):
    store = FileCheckpointStore(work_dir=str(tmp_path))
    await store.save(_make_checkpoint(checkpoint_id="cp-1"))
    await store.save(_make_checkpoint(checkpoint_id="cp-2"))

    records = await store.list("sess-1")
    ids = {r.checkpoint_id for r in records}
    assert ids == {"cp-1", "cp-2"}


async def test_file_list_empty_session(tmp_path):
    store = FileCheckpointStore(work_dir=str(tmp_path))
    assert await store.list("nonexistent") == []


async def test_file_separate_sessions(tmp_path):
    store = FileCheckpointStore(work_dir=str(tmp_path))
    await store.save(_make_checkpoint(session_id="sess-a", checkpoint_id="cp-1"))
    await store.save(_make_checkpoint(session_id="sess-b", checkpoint_id="cp-2"))

    assert len(await store.list("sess-a")) == 1
    assert len(await store.list("sess-b")) == 1


# --- InMemoryCheckpointStore ---


async def test_inmemory_save_and_latest():
    store = InMemoryCheckpointStore()
    await store.save(_make_checkpoint())

    latest = await store.latest("sess-1")
    assert latest is not None
    assert latest.checkpoint_id == "cp-1"


async def test_inmemory_latest_returns_most_recent():
    store = InMemoryCheckpointStore()
    early = datetime(2026, 1, 1, 10, 0, 0, tzinfo=timezone.utc)
    late = datetime(2026, 1, 1, 14, 0, 0, tzinfo=timezone.utc)

    await store.save(_make_checkpoint(checkpoint_id="cp-old", ts=early))
    await store.save(_make_checkpoint(checkpoint_id="cp-new", ts=late))

    latest = await store.latest("sess-1")
    assert latest is not None
    assert latest.checkpoint_id == "cp-new"


async def test_inmemory_latest_nonexistent_returns_none():
    store = InMemoryCheckpointStore()
    assert await store.latest("nonexistent") is None


async def test_inmemory_list():
    store = InMemoryCheckpointStore()
    await store.save(_make_checkpoint(checkpoint_id="cp-1"))
    await store.save(_make_checkpoint(checkpoint_id="cp-2"))

    records = await store.list("sess-1")
    assert len(records) == 2
