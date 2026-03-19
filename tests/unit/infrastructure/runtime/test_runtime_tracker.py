"""Unit tests for AgentRuntimeTracker."""

from datetime import datetime, timedelta, timezone
from unittest.mock import Mock

from taskforce.infrastructure.runtime.checkpoint_store import InMemoryCheckpointStore
from taskforce.infrastructure.runtime.heartbeat_store import InMemoryHeartbeatStore
from taskforce.infrastructure.runtime.runtime_tracker import AgentRuntimeTracker

FIXED_TIME = datetime(2026, 3, 1, 12, 0, 0, tzinfo=timezone.utc)


def _make_tracker(
    heartbeat_store: InMemoryHeartbeatStore | None = None,
    checkpoint_store: InMemoryCheckpointStore | None = None,
    now: datetime = FIXED_TIME,
) -> AgentRuntimeTracker:
    return AgentRuntimeTracker(
        heartbeat_store=heartbeat_store or InMemoryHeartbeatStore(),
        checkpoint_store=checkpoint_store or InMemoryCheckpointStore(),
        logger=Mock(),
        time_provider=lambda: now,
    )


async def test_record_heartbeat():
    hb_store = InMemoryHeartbeatStore()
    tracker = _make_tracker(heartbeat_store=hb_store)

    await tracker.record_heartbeat("sess-1", "running", {"step": 1})

    loaded = await hb_store.load("sess-1")
    assert loaded is not None
    assert loaded.status == "running"
    assert loaded.details == {"step": 1}
    assert loaded.timestamp == FIXED_TIME


async def test_record_heartbeat_default_details():
    hb_store = InMemoryHeartbeatStore()
    tracker = _make_tracker(heartbeat_store=hb_store)

    await tracker.record_heartbeat("sess-1", "running")

    loaded = await hb_store.load("sess-1")
    assert loaded is not None
    assert loaded.details == {}


async def test_record_checkpoint():
    cp_store = InMemoryCheckpointStore()
    tracker = _make_tracker(checkpoint_store=cp_store)

    await tracker.record_checkpoint("sess-1", {"mission": "test", "step": 3})

    latest = await cp_store.latest("sess-1")
    assert latest is not None
    assert latest.session_id == "sess-1"
    assert latest.state == {"mission": "test", "step": 3}
    assert latest.timestamp == FIXED_TIME
    assert len(latest.checkpoint_id) > 0


async def test_mark_finished_records_heartbeat():
    hb_store = InMemoryHeartbeatStore()
    tracker = _make_tracker(heartbeat_store=hb_store)

    await tracker.mark_finished("sess-1", "completed", {"result": "ok"})

    loaded = await hb_store.load("sess-1")
    assert loaded is not None
    assert loaded.status == "completed"
    assert loaded.details == {"result": "ok"}


async def test_latest_checkpoint():
    cp_store = InMemoryCheckpointStore()
    tracker = _make_tracker(checkpoint_store=cp_store)

    await tracker.record_checkpoint("sess-1", {"step": 1})
    latest = await tracker.latest_checkpoint("sess-1")
    assert latest is not None
    assert latest.state == {"step": 1}


async def test_latest_checkpoint_nonexistent():
    tracker = _make_tracker()
    assert await tracker.latest_checkpoint("nonexistent") is None


async def test_list_stale_sessions():
    hb_store = InMemoryHeartbeatStore()
    old_time = FIXED_TIME - timedelta(seconds=600)
    recent_time = FIXED_TIME - timedelta(seconds=10)

    # Record old heartbeat directly in store
    from taskforce.core.domain.runtime import HeartbeatRecord

    await hb_store.record(
        HeartbeatRecord(session_id="old-sess", status="running", timestamp=old_time)
    )
    await hb_store.record(
        HeartbeatRecord(session_id="new-sess", status="running", timestamp=recent_time)
    )

    tracker = _make_tracker(heartbeat_store=hb_store)
    stale = await tracker.list_stale_sessions(max_age_seconds=300, now=FIXED_TIME)

    assert len(stale) == 1
    assert stale[0].session_id == "old-sess"


async def test_list_stale_sessions_none_stale():
    hb_store = InMemoryHeartbeatStore()
    from taskforce.core.domain.runtime import HeartbeatRecord

    await hb_store.record(
        HeartbeatRecord(session_id="sess-1", status="running", timestamp=FIXED_TIME)
    )

    tracker = _make_tracker(heartbeat_store=hb_store)
    stale = await tracker.list_stale_sessions(max_age_seconds=300, now=FIXED_TIME)
    assert stale == []


async def test_list_stale_sessions_uses_time_provider_when_no_now():
    hb_store = InMemoryHeartbeatStore()
    old_time = FIXED_TIME - timedelta(seconds=600)

    from taskforce.core.domain.runtime import HeartbeatRecord

    await hb_store.record(
        HeartbeatRecord(session_id="old-sess", status="running", timestamp=old_time)
    )

    tracker = _make_tracker(heartbeat_store=hb_store)
    # Call without explicit now - should use time_provider (FIXED_TIME)
    stale = await tracker.list_stale_sessions(max_age_seconds=300)
    assert len(stale) == 1
