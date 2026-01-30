"""Runtime tracking helpers for long-running agent sessions."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Callable
from uuid import uuid4

import structlog

from taskforce.core.domain.runtime import CheckpointRecord, HeartbeatRecord
from taskforce.core.interfaces.logging import LoggerProtocol
from taskforce.core.interfaces.runtime import (
    AgentRuntimeTrackerProtocol,
    CheckpointStoreProtocol,
    HeartbeatStoreProtocol,
)


def _utc_now() -> datetime:
    """Return the current UTC timestamp."""
    return datetime.now(timezone.utc)


class AgentRuntimeTracker(AgentRuntimeTrackerProtocol):
    """Default runtime tracker using heartbeat and checkpoint stores."""

    def __init__(
        self,
        heartbeat_store: HeartbeatStoreProtocol,
        checkpoint_store: CheckpointStoreProtocol,
        *,
        logger: LoggerProtocol | None = None,
        time_provider: Callable[[], datetime] | None = None,
    ) -> None:
        self._heartbeat_store = heartbeat_store
        self._checkpoint_store = checkpoint_store
        self._logger = logger or structlog.get_logger().bind(component="AgentRuntimeTracker")
        self._time_provider = time_provider or _utc_now

    async def record_heartbeat(
        self,
        session_id: str,
        status: str,
        details: dict[str, object] | None = None,
    ) -> None:
        record = HeartbeatRecord(
            session_id=session_id,
            status=status,
            timestamp=self._time_provider(),
            details=details or {},
        )
        await self._heartbeat_store.record(record)
        self._logger.debug("heartbeat_recorded", session_id=session_id, status=status)

    async def record_checkpoint(self, session_id: str, state: dict[str, object]) -> None:
        record = CheckpointRecord(
            session_id=session_id,
            checkpoint_id=uuid4().hex,
            state=state,
            timestamp=self._time_provider(),
        )
        await self._checkpoint_store.save(record)
        self._logger.debug("checkpoint_recorded", session_id=session_id)

    async def mark_finished(
        self,
        session_id: str,
        status: str,
        details: dict[str, object] | None = None,
    ) -> None:
        await self.record_heartbeat(session_id, status, details)

    async def list_stale_sessions(
        self,
        max_age_seconds: int,
        *,
        now: datetime | None = None,
    ) -> list[HeartbeatRecord]:
        cutoff = (now or self._time_provider()) - timedelta(seconds=max_age_seconds)
        records = await self._heartbeat_store.list_records()
        return [record for record in records if record.timestamp < cutoff]

    async def latest_checkpoint(self, session_id: str) -> CheckpointRecord | None:
        return await self._checkpoint_store.latest(session_id)
