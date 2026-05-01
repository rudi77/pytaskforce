"""Tests for ProgressUpdate construction from StreamEvents."""

from __future__ import annotations

from taskforce.application.progress_update_builder import (
    stream_event_to_progress_update,
)
from taskforce.core.domain.enums import EventType
from taskforce.core.domain.models import StreamEvent


def test_lifts_sub_agent_metadata_into_progress_update() -> None:
    """When a sub-agent forwarded event carries agent_path/parent_session_id/
    source_agent in its data, those keys must be promoted to first-class
    ProgressUpdate fields so the management UI can read them without digging
    into ``details``."""
    event = StreamEvent(
        event_type=EventType.TOOL_CALL,
        data={
            "tool": "python",
            "id": "t1",
            "args": {"code": "print(42)"},
            "agent_path": ["coding_worker"],
            "parent_session_id": "root",
            "source_agent": "coding_worker",
        },
    )

    update = stream_event_to_progress_update(event)

    assert update.agent_path == ["coding_worker"]
    assert update.parent_session_id == "root"
    assert update.source_agent == "coding_worker"
    # Original details still carry the metadata for serialization.
    assert update.details["agent_path"] == ["coding_worker"]


def test_root_event_has_no_agent_path() -> None:
    """Events from the root agent leave the new fields as ``None``."""
    event = StreamEvent(
        event_type=EventType.TOOL_CALL,
        data={"tool": "python", "id": "t1", "args": {}},
    )

    update = stream_event_to_progress_update(event)

    assert update.agent_path is None
    assert update.parent_session_id is None
    assert update.source_agent is None


def test_invalid_agent_path_falls_back_to_none() -> None:
    """A malformed ``agent_path`` (e.g., a string) is ignored, not crashed on."""
    event = StreamEvent(
        event_type=EventType.TOOL_CALL,
        data={"tool": "x", "id": "t1", "agent_path": "not-a-list"},
    )

    update = stream_event_to_progress_update(event)

    assert update.agent_path is None
