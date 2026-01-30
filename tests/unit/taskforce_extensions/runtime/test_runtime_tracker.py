from datetime import datetime, timedelta, timezone

import pytest

from taskforce_extensions.infrastructure.runtime import (
    AgentRuntimeTracker,
    InMemoryCheckpointStore,
    InMemoryHeartbeatStore,
)


@pytest.mark.asyncio
async def test_runtime_tracker_records_heartbeat_and_checkpoint() -> None:
    now = datetime(2025, 1, 1, tzinfo=timezone.utc)

    def time_provider() -> datetime:
        return now

    heartbeat_store = InMemoryHeartbeatStore()
    checkpoint_store = InMemoryCheckpointStore()
    tracker = AgentRuntimeTracker(
        heartbeat_store=heartbeat_store,
        checkpoint_store=checkpoint_store,
        time_provider=time_provider,
    )

    await tracker.record_heartbeat("session-1", "running", {"step": 2})
    await tracker.record_checkpoint("session-1", {"state": "ok"})

    heartbeat = await heartbeat_store.load("session-1")
    latest_checkpoint = await checkpoint_store.latest("session-1")

    assert heartbeat is not None
    assert heartbeat.status == "running"
    assert heartbeat.details["step"] == 2
    assert latest_checkpoint is not None
    assert latest_checkpoint.state["state"] == "ok"


@pytest.mark.asyncio
async def test_runtime_tracker_lists_stale_sessions() -> None:
    now = datetime(2025, 1, 1, tzinfo=timezone.utc)

    def time_provider() -> datetime:
        return now

    heartbeat_store = InMemoryHeartbeatStore()
    checkpoint_store = InMemoryCheckpointStore()
    tracker = AgentRuntimeTracker(
        heartbeat_store=heartbeat_store,
        checkpoint_store=checkpoint_store,
        time_provider=time_provider,
    )

    await tracker.record_heartbeat("session-1", "running", None)

    stale = await tracker.list_stale_sessions(
        max_age_seconds=60,
        now=now + timedelta(minutes=10),
    )

    assert [record.session_id for record in stale] == ["session-1"]
