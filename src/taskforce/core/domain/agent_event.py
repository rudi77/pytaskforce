"""Agent event domain models for the event-driven butler architecture.

Defines the core event types that flow through the butler's event bus,
connecting external event sources (calendar, email, webhooks) to the
agent's rule engine and action dispatcher.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any
from uuid import uuid4

from taskforce.core.utils.time import utc_now


class AgentEventType(str, Enum):
    """Types of events from external sources processed by the butler."""

    # Calendar events
    CALENDAR_UPCOMING = "calendar.upcoming"
    CALENDAR_STARTED = "calendar.started"
    CALENDAR_ENDED = "calendar.ended"
    CALENDAR_CHANGED = "calendar.changed"

    # Email events
    EMAIL_RECEIVED = "email.received"

    # Scheduler events
    SCHEDULE_TRIGGERED = "schedule.triggered"

    # Rule engine events
    RULE_FIRED = "rule.fired"

    # Learning events
    LEARNING_EXTRACTED = "learning.extracted"

    # Webhook events
    WEBHOOK_RECEIVED = "webhook.received"

    # File watch events
    FILE_CHANGED = "file.changed"

    # Generic
    CUSTOM = "custom"


@dataclass(frozen=True)
class AgentEvent:
    """An event from an external source processed by the butler.

    AgentEvents are published to the message bus by event sources and
    consumed by the EventRouter for rule evaluation and action dispatch.

    Attributes:
        event_id: Unique identifier for this event.
        source: Name of the event source (e.g. "calendar", "email").
        event_type: Categorized type of the event.
        payload: Source-specific event data.
        timestamp: When the event occurred or was detected.
        metadata: Additional context (user_id, priority, etc.).
    """

    event_id: str = field(default_factory=lambda: uuid4().hex)
    source: str = ""
    event_type: AgentEventType = AgentEventType.CUSTOM
    payload: dict[str, Any] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=utc_now)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Serialize the event for transport or storage."""
        return {
            "event_id": self.event_id,
            "source": self.source,
            "event_type": self.event_type.value,
            "payload": self.payload,
            "timestamp": self.timestamp.isoformat(),
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> AgentEvent:
        """Deserialize an event from a stored dict."""
        event_type_raw = data.get("event_type", "custom")
        try:
            event_type = AgentEventType(event_type_raw)
        except ValueError:
            event_type = AgentEventType.CUSTOM

        ts_raw = data.get("timestamp")
        timestamp = datetime.fromisoformat(ts_raw) if ts_raw else utc_now()

        return cls(
            event_id=str(data.get("event_id", uuid4().hex)),
            source=str(data.get("source", "")),
            event_type=event_type,
            payload=dict(data.get("payload", {})),
            timestamp=timestamp,
            metadata=dict(data.get("metadata", {})),
        )
