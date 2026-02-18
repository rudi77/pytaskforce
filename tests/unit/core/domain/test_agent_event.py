"""Tests for AgentEvent domain model."""

import pytest
from datetime import datetime, timezone

from taskforce.core.domain.agent_event import AgentEvent, AgentEventType


class TestAgentEventType:
    """Tests for AgentEventType enum."""

    def test_calendar_events(self) -> None:
        assert AgentEventType.CALENDAR_UPCOMING.value == "calendar.upcoming"
        assert AgentEventType.CALENDAR_STARTED.value == "calendar.started"
        assert AgentEventType.CALENDAR_ENDED.value == "calendar.ended"

    def test_schedule_events(self) -> None:
        assert AgentEventType.SCHEDULE_TRIGGERED.value == "schedule.triggered"

    def test_custom_event(self) -> None:
        assert AgentEventType.CUSTOM.value == "custom"


class TestAgentEvent:
    """Tests for AgentEvent dataclass."""

    def test_create_default(self) -> None:
        event = AgentEvent()
        assert event.event_id
        assert event.source == ""
        assert event.event_type == AgentEventType.CUSTOM
        assert event.payload == {}
        assert event.metadata == {}
        assert isinstance(event.timestamp, datetime)

    def test_create_with_values(self) -> None:
        event = AgentEvent(
            source="calendar",
            event_type=AgentEventType.CALENDAR_UPCOMING,
            payload={"title": "Meeting", "minutes_until": 30},
            metadata={"calendar_id": "primary"},
        )
        assert event.source == "calendar"
        assert event.event_type == AgentEventType.CALENDAR_UPCOMING
        assert event.payload["title"] == "Meeting"
        assert event.metadata["calendar_id"] == "primary"

    def test_is_frozen(self) -> None:
        event = AgentEvent(source="test")
        with pytest.raises(AttributeError):
            event.source = "changed"  # type: ignore[misc]

    def test_to_dict(self) -> None:
        event = AgentEvent(
            event_id="abc123",
            source="calendar",
            event_type=AgentEventType.CALENDAR_UPCOMING,
            payload={"title": "Meeting"},
        )
        d = event.to_dict()
        assert d["event_id"] == "abc123"
        assert d["source"] == "calendar"
        assert d["event_type"] == "calendar.upcoming"
        assert d["payload"]["title"] == "Meeting"
        assert "timestamp" in d

    def test_from_dict(self) -> None:
        data = {
            "event_id": "xyz789",
            "source": "email",
            "event_type": "email.received",
            "payload": {"subject": "Hello"},
            "timestamp": "2026-02-18T10:00:00+00:00",
            "metadata": {"folder": "INBOX"},
        }
        event = AgentEvent.from_dict(data)
        assert event.event_id == "xyz789"
        assert event.source == "email"
        assert event.event_type == AgentEventType.EMAIL_RECEIVED
        assert event.payload["subject"] == "Hello"
        assert event.metadata["folder"] == "INBOX"

    def test_from_dict_unknown_event_type(self) -> None:
        data = {"event_type": "unknown.type"}
        event = AgentEvent.from_dict(data)
        assert event.event_type == AgentEventType.CUSTOM

    def test_roundtrip(self) -> None:
        original = AgentEvent(
            source="webhook.github",
            event_type=AgentEventType.WEBHOOK_RECEIVED,
            payload={"action": "push"},
        )
        restored = AgentEvent.from_dict(original.to_dict())
        assert restored.event_id == original.event_id
        assert restored.source == original.source
        assert restored.event_type == original.event_type
        assert restored.payload == original.payload
