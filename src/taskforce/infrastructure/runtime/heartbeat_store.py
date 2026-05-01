"""Heartbeat storage adapter for long-running agent sessions.

Heartbeats are recorded per ReAct step but are never read on the production
path — ``runtime_tracker.list_stale_sessions`` is only exercised in tests.
The previous file-backed implementation therefore wrote one JSON file per
step without any reader, so it has been removed. The in-memory store is
sufficient for the existing call sites and for keeping the protocol
satisfied. If durable cross-process liveness is needed in the future,
infer it from ``FileCheckpointStore`` mtimes instead.
"""

from __future__ import annotations

from taskforce.core.domain.runtime import HeartbeatRecord
from taskforce.core.interfaces.runtime import HeartbeatStoreProtocol


class InMemoryHeartbeatStore(HeartbeatStoreProtocol):
    """In-memory heartbeat store. Used as the default everywhere."""

    def __init__(self) -> None:
        self._records: dict[str, HeartbeatRecord] = {}

    async def record(self, record: HeartbeatRecord) -> None:
        self._records[record.session_id] = record

    async def load(self, session_id: str) -> HeartbeatRecord | None:
        return self._records.get(session_id)

    async def list_records(self) -> list[HeartbeatRecord]:
        return list(self._records.values())
