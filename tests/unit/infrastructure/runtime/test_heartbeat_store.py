"""Unit tests for FileHeartbeatStore and InMemoryHeartbeatStore."""

from datetime import datetime, timezone

from taskforce.core.domain.runtime import HeartbeatRecord
from taskforce.infrastructure.runtime.heartbeat_store import (
    FileHeartbeatStore,
    InMemoryHeartbeatStore,
)


def _make_record(session_id: str = "sess-1", status: str = "running") -> HeartbeatRecord:
    return HeartbeatRecord(
        session_id=session_id,
        status=status,
        timestamp=datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc),
        details={"step": 3},
    )


# --- FileHeartbeatStore ---


async def test_file_record_and_load(tmp_path):
    store = FileHeartbeatStore(work_dir=str(tmp_path))
    record = _make_record()

    await store.record(record)
    loaded = await store.load("sess-1")

    assert loaded is not None
    assert loaded.session_id == "sess-1"
    assert loaded.status == "running"
    assert loaded.details == {"step": 3}


async def test_file_load_nonexistent_returns_none(tmp_path):
    store = FileHeartbeatStore(work_dir=str(tmp_path))
    assert await store.load("nonexistent") is None


async def test_file_record_overwrites_previous(tmp_path):
    store = FileHeartbeatStore(work_dir=str(tmp_path))
    await store.record(_make_record(status="running"))
    await store.record(_make_record(status="completed"))

    loaded = await store.load("sess-1")
    assert loaded is not None
    assert loaded.status == "completed"


async def test_file_list_records(tmp_path):
    store = FileHeartbeatStore(work_dir=str(tmp_path))
    await store.record(_make_record("sess-1"))
    await store.record(_make_record("sess-2"))

    records = await store.list_records()
    session_ids = {r.session_id for r in records}
    assert session_ids == {"sess-1", "sess-2"}


async def test_file_list_records_empty(tmp_path):
    store = FileHeartbeatStore(work_dir=str(tmp_path))
    assert await store.list_records() == []


async def test_file_creates_directory_structure(tmp_path):
    store = FileHeartbeatStore(work_dir=str(tmp_path / "nested" / "dir"))
    await store.record(_make_record())
    loaded = await store.load("sess-1")
    assert loaded is not None


# --- InMemoryHeartbeatStore ---


async def test_inmemory_record_and_load():
    store = InMemoryHeartbeatStore()
    record = _make_record()
    await store.record(record)

    loaded = await store.load("sess-1")
    assert loaded is not None
    assert loaded.session_id == "sess-1"


async def test_inmemory_load_nonexistent_returns_none():
    store = InMemoryHeartbeatStore()
    assert await store.load("nonexistent") is None


async def test_inmemory_list_records():
    store = InMemoryHeartbeatStore()
    await store.record(_make_record("sess-1"))
    await store.record(_make_record("sess-2"))

    records = await store.list_records()
    assert len(records) == 2


async def test_inmemory_record_overwrites():
    store = InMemoryHeartbeatStore()
    await store.record(_make_record(status="running"))
    await store.record(_make_record(status="done"))

    loaded = await store.load("sess-1")
    assert loaded is not None
    assert loaded.status == "done"
