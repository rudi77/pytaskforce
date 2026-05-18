"""Tests for ``_collect_result`` mapping salvaged FINAL_ANSWER → FAILED (#407)."""

from __future__ import annotations

from collections.abc import AsyncIterator

import pytest

from taskforce.core.domain.enums import EventType, ExecutionStatus
from taskforce.core.domain.models import StreamEvent
from taskforce.core.domain.planning.react_loop import _collect_result


async def _aiter(events: list[StreamEvent]) -> AsyncIterator[StreamEvent]:
    for e in events:
        yield e


@pytest.mark.asyncio
async def test_normal_final_answer_completes() -> None:
    events = [
        StreamEvent(event_type=EventType.FINAL_ANSWER, data={"content": "All done."})
    ]
    result = await _collect_result("sess", _aiter(events))
    assert result.status == ExecutionStatus.COMPLETED
    assert result.final_message == "All done."


@pytest.mark.asyncio
async def test_salvaged_final_answer_maps_to_failed() -> None:
    events = [
        StreamEvent(
            event_type=EventType.FINAL_ANSWER,
            data={"content": "Best-effort summary.", "salvaged": True, "salvage_reason": "stall"},
        )
    ]
    result = await _collect_result("sess", _aiter(events))
    assert result.status == ExecutionStatus.FAILED
    # Final message is still the salvaged content (good for UX), but
    # status flags the failure for downstream consumers.
    assert result.final_message == "Best-effort summary."


@pytest.mark.asyncio
async def test_salvage_reason_max_steps_propagates() -> None:
    events = [
        StreamEvent(
            event_type=EventType.FINAL_ANSWER,
            data={"content": "partial", "salvaged": True, "salvage_reason": "max_steps"},
        )
    ]
    result = await _collect_result("sess", _aiter(events))
    assert result.status == ExecutionStatus.FAILED


@pytest.mark.asyncio
async def test_explicit_error_still_wins_over_salvage() -> None:
    events = [
        StreamEvent(
            event_type=EventType.FINAL_ANSWER,
            data={"content": "partial", "salvaged": True, "salvage_reason": "stall"},
        ),
        StreamEvent(
            event_type=EventType.ERROR,
            data={"message": "Boom!"},
        ),
    ]
    result = await _collect_result("sess", _aiter(events))
    assert result.status == ExecutionStatus.FAILED


@pytest.mark.asyncio
async def test_no_final_answer_is_failed() -> None:
    """Empty event stream → FAILED (no content + no error)."""
    result = await _collect_result("sess", _aiter([]))
    assert result.status == ExecutionStatus.FAILED


@pytest.mark.asyncio
async def test_ask_user_is_paused_not_failed_even_with_salvage_marker() -> None:
    """ASK_USER takes precedence — the run is paused, not failed."""
    events = [
        StreamEvent(
            event_type=EventType.ASK_USER,
            data={"question": "what next?", "channel": "cli", "recipient_id": "user"},
        ),
    ]
    result = await _collect_result("sess", _aiter(events))
    assert result.status == ExecutionStatus.PAUSED
