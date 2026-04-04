"""Protocol definitions for runtime tracking."""

from __future__ import annotations

from typing import Protocol

from taskforce.core.domain.runtime import CheckpointRecord, HeartbeatRecord


class HeartbeatStoreProtocol(Protocol):
    """Protocol for heartbeat persistence."""

    async def record(self, record: HeartbeatRecord) -> None:
        """Persist a heartbeat record."""
        ...

    async def load(self, session_id: str) -> HeartbeatRecord | None:
        """Load the latest heartbeat for a session."""
        ...

    async def list_records(self) -> list[HeartbeatRecord]:
        """List all heartbeat records."""
        ...


class CheckpointStoreProtocol(Protocol):
    """Protocol for checkpoint persistence."""

    async def save(self, record: CheckpointRecord) -> None:
        """Persist a checkpoint record."""
        ...

    async def latest(self, session_id: str) -> CheckpointRecord | None:
        """Return the most recent checkpoint for a session."""
        ...

    async def list(self, session_id: str) -> list[CheckpointRecord]:
        """List all checkpoints for a session."""
        ...


class AgentRuntimeTrackerProtocol(Protocol):
    """Protocol for runtime tracking helpers."""

    async def record_heartbeat(
        self,
        session_id: str,
        status: str,
        details: dict[str, object] | None = None,
    ) -> None:
        """Record a heartbeat for a session."""
        ...

    async def record_checkpoint(self, session_id: str, state: dict[str, object]) -> None:
        """Persist a checkpoint for a session."""
        ...

    async def mark_finished(
        self,
        session_id: str,
        status: str,
        details: dict[str, object] | None = None,
    ) -> None:
        """Record final status for a session."""
        ...
