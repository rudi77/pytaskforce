"""Unit tests for InMemoryHeartbeatStore."""

from datetime import datetime, timezone

from taskforce.core.domain.runtime import HeartbeatRecord
from taskforce.infrastructure.runtime.heartbeat_store import InMemoryHeartbeatStore


def _make_record(session_id: str = "sess-1", status: str = "running") -> HeartbeatRecord:
    return HeartbeatRecord(
        session_id=session_id,
        status=status,
        timestamp=datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc),
        details={"step": 3},
    )


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
