"""Messaging domain models for agent communication."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


def _utc_now() -> datetime:
    """Return the current UTC timestamp."""
    return datetime.now(timezone.utc)


@dataclass(frozen=True)
class MessageEnvelope:
    """Envelope for message bus payloads."""

    message_id: str
    topic: str
    payload: dict[str, Any]
    headers: dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=_utc_now)

    def to_dict(self) -> dict[str, Any]:
        """Serialize the envelope for storage or transport."""
        return {
            "message_id": self.message_id,
            "topic": self.topic,
            "payload": self.payload,
            "headers": self.headers,
            "created_at": self.created_at.isoformat(),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "MessageEnvelope":
        """Deserialize a stored envelope."""
        created_at_raw = data.get("created_at")
        created_at = (
            datetime.fromisoformat(created_at_raw)
            if created_at_raw
            else _utc_now()
        )
        return cls(
            message_id=str(data["message_id"]),
            topic=str(data["topic"]),
            payload=dict(data.get("payload", {})),
            headers=dict(data.get("headers", {})),
            created_at=created_at,
        )
