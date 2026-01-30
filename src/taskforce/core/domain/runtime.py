"""Runtime tracking domain models."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


def _utc_now() -> datetime:
    """Return the current UTC timestamp."""
    return datetime.now(timezone.utc)


def _parse_timestamp(raw: str | None) -> datetime:
    """Parse an ISO timestamp string."""
    if not raw:
        return _utc_now()
    return datetime.fromisoformat(raw)


@dataclass(frozen=True)
class HeartbeatRecord:
    """Heartbeat metadata for a running agent session."""

    session_id: str
    status: str
    timestamp: datetime = field(default_factory=_utc_now)
    details: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Serialize the heartbeat record."""
        return {
            "session_id": self.session_id,
            "status": self.status,
            "timestamp": self.timestamp.isoformat(),
            "details": self.details,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "HeartbeatRecord":
        """Deserialize a heartbeat record."""
        return cls(
            session_id=str(data["session_id"]),
            status=str(data.get("status", "unknown")),
            timestamp=_parse_timestamp(data.get("timestamp")),
            details=dict(data.get("details", {})),
        )


@dataclass(frozen=True)
class CheckpointRecord:
    """Checkpoint metadata for agent recovery."""

    session_id: str
    checkpoint_id: str
    state: dict[str, Any]
    timestamp: datetime = field(default_factory=_utc_now)

    def to_dict(self) -> dict[str, Any]:
        """Serialize the checkpoint record."""
        return {
            "session_id": self.session_id,
            "checkpoint_id": self.checkpoint_id,
            "state": self.state,
            "timestamp": self.timestamp.isoformat(),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "CheckpointRecord":
        """Deserialize a checkpoint record."""
        return cls(
            session_id=str(data["session_id"]),
            checkpoint_id=str(data["checkpoint_id"]),
            state=dict(data.get("state", {})),
            timestamp=_parse_timestamp(data.get("timestamp")),
        )
