"""Tests for ExperienceTracker."""

from unittest.mock import AsyncMock

import pytest

from taskforce.core.domain.enums import EventType
from taskforce.core.domain.models import StreamEvent
from taskforce.infrastructure.memory.experience_tracker import ExperienceTracker


@pytest.fixture
def mock_store():
    store = AsyncMock()
    store.save_experience = AsyncMock()
    return store


@pytest.fixture
def tracker(mock_store):
    return ExperienceTracker(mock_store)


class TestExperienceTracker:
    def test_start_session(self, tracker):
        tracker.start_session("sess-1", "Test mission", "dev")
        assert tracker._current is not None
        assert tracker._current.session_id == "sess-1"
        assert tracker._current.mission == "Test mission"
        assert tracker._current.profile == "dev"

    def test_observe_without_session_is_noop(self, tracker):
        event = StreamEvent(event_type=EventType.STEP_START, data={"step": 1})
        tracker.observe(event)  # Should not raise

    def test_observe_step_start(self, tracker):
        tracker.start_session("sess-1", "mission", "dev")
        event = StreamEvent(event_type=EventType.STEP_START, data={"step": 3})
        tracker.observe(event)
        assert tracker._current.total_steps == 3

    def test_observe_tool_call_and_result(self, tracker):
        tracker.start_session("sess-1", "mission", "dev")

        call_event = StreamEvent(
            event_type=EventType.TOOL_CALL,
            data={
                "tool": "python",
                "tool_call_id": "tc-1",
                "arguments": {"code": "1+1"},
            },
        )
        tracker.observe(call_event)
        assert len(tracker._pending_tool_calls) == 1

        result_event = StreamEvent(
            event_type=EventType.TOOL_RESULT,
            data={
                "tool_call_id": "tc-1",
                "result": "2",
                "success": True,
            },
        )
        tracker.observe(result_event)
        assert len(tracker._current.tool_calls) == 1
        tc = tracker._current.tool_calls[0]
        assert tc.tool_name == "python"
        assert tc.success is True
        assert tc.output_summary == "2"

    def test_observe_tool_result_truncates_output(self, tracker):
        tracker.start_session("sess-1", "mission", "dev")

        tracker.observe(
            StreamEvent(
                event_type=EventType.TOOL_CALL,
                data={"tool": "shell", "tool_call_id": "tc-2", "arguments": {}},
            )
        )
        long_output = "x" * 1000
        tracker.observe(
            StreamEvent(
                event_type=EventType.TOOL_RESULT,
                data={"tool_call_id": "tc-2", "result": long_output},
            )
        )
        assert len(tracker._current.tool_calls[0].output_summary) == 503

    def test_observe_plan_updated(self, tracker):
        tracker.start_session("sess-1", "mission", "dev")
        tracker.observe(
            StreamEvent(
                event_type=EventType.PLAN_UPDATED,
                data={"action": "create_plan", "plan": "Step 1: Do X"},
            )
        )
        assert len(tracker._current.plan_updates) == 1

    def test_observe_ask_user(self, tracker):
        tracker.start_session("sess-1", "mission", "dev")
        tracker.observe(
            StreamEvent(
                event_type=EventType.ASK_USER,
                data={"question": "What file?"},
            )
        )
        assert len(tracker._current.user_interactions) == 1

    def test_observe_token_usage(self, tracker):
        tracker.start_session("sess-1", "mission", "dev")
        tracker.observe(
            StreamEvent(
                event_type=EventType.TOKEN_USAGE,
                data={"total_tokens": 500},
            )
        )
        tracker.observe(
            StreamEvent(
                event_type=EventType.TOKEN_USAGE,
                data={"total_tokens": 300},
            )
        )
        assert tracker._current.total_tokens == 800

    def test_observe_final_answer(self, tracker):
        tracker.start_session("sess-1", "mission", "dev")
        tracker.observe(
            StreamEvent(
                event_type=EventType.FINAL_ANSWER,
                data={"answer": "The result is 42."},
            )
        )
        assert tracker._current.final_answer == "The result is 42."

    def test_observe_error(self, tracker):
        tracker.start_session("sess-1", "mission", "dev")
        tracker.observe(
            StreamEvent(
                event_type=EventType.ERROR,
                data={"error": "LLM timeout"},
            )
        )
        assert "LLM timeout" in tracker._current.errors

    async def test_end_session_persists(self, tracker, mock_store):
        tracker.start_session("sess-1", "mission", "dev")
        tracker.observe(StreamEvent(event_type=EventType.STEP_START, data={"step": 1}))
        experience = await tracker.end_session("completed")

        assert experience is not None
        assert experience.session_id == "sess-1"
        assert experience.metadata["status"] == "completed"
        assert experience.ended_at is not None
        mock_store.save_experience.assert_awaited_once()

    async def test_end_session_without_start_returns_none(self, tracker):
        result = await tracker.end_session()
        assert result is None

    async def test_end_session_clears_state(self, tracker):
        tracker.start_session("sess-1", "mission", "dev")
        await tracker.end_session()
        assert tracker._current is None

    async def test_end_session_handles_save_failure(self, tracker, mock_store):
        mock_store.save_experience.side_effect = OSError("disk full")
        tracker.start_session("sess-1", "mission", "dev")
        experience = await tracker.end_session()
        assert experience is not None  # Returns experience despite save failure

    def test_events_are_recorded(self, tracker):
        tracker.start_session("sess-1", "mission", "dev")
        tracker.observe(StreamEvent(event_type=EventType.STEP_START, data={"step": 1}))
        tracker.observe(StreamEvent(event_type=EventType.TOOL_CALL, data={"tool": "python"}))
        assert len(tracker._current.events) == 2
