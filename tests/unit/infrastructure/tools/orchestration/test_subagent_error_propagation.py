"""Verify sub-agent failure cause propagates to the parent agent.

Before this fix, ``call_agents_parallel`` returned ``error: ''`` when a
sub-agent died on a content-filter abort, because the ERROR StreamEvent
carried the message but the outcome tracker only flipped status to
FAILED without capturing the text. The butler then had no idea why its
specialist failed and could not recover or surface the cause to the
user.
"""

from __future__ import annotations

from typing import Any

import pytest

from taskforce.core.domain.enums import EventType
from taskforce.core.domain.models import StreamEvent
from taskforce.core.domain.sub_agents import SubAgentResult
from taskforce.infrastructure.tools.orchestration._event_forwarding import (
    SubAgentExecutionOutcome,
    _track_outcome,
)
from taskforce.infrastructure.tools.orchestration.parallel_agent_tool import (
    ParallelAgentTool,
)


# ---------------------------------------------------------------------------
# _track_outcome
# ---------------------------------------------------------------------------


def test_error_event_captures_message_and_kind() -> None:
    outcome = SubAgentExecutionOutcome()

    _track_outcome(
        StreamEvent(
            event_type=EventType.ERROR,
            data={
                "message": "LLM call rejected (content_filter): ...",
                "error_kind": "content_filter",
                "non_retryable": True,
            },
        ),
        outcome,
    )

    assert outcome.status == "failed"
    assert outcome.error_message == "LLM call rejected (content_filter): ..."
    assert outcome.error_kind == "content_filter"


def test_error_event_without_kind_still_captures_message() -> None:
    """Plain errors (no structured error_kind) still surface the message."""
    outcome = SubAgentExecutionOutcome()

    _track_outcome(
        StreamEvent(
            event_type=EventType.ERROR,
            data={"message": "upstream timeout"},
        ),
        outcome,
    )

    assert outcome.status == "failed"
    assert outcome.error_message == "upstream timeout"
    assert outcome.error_kind == ""


# ---------------------------------------------------------------------------
# parallel_agent_tool — error_kind threaded through to the parent context
# ---------------------------------------------------------------------------


class _FakeSpawner:
    """Spawner stub that returns a pre-built SubAgentResult per spawn()."""

    def __init__(self, result: SubAgentResult) -> None:
        self._result = result
        self.calls: list[Any] = []

    async def spawn(self, spec: Any) -> SubAgentResult:
        self.calls.append(spec)
        return self._result


@pytest.mark.asyncio
async def test_parallel_tool_propagates_content_filter_kind() -> None:
    spawner = _FakeSpawner(
        SubAgentResult(
            session_id="s1",
            status="failed",
            success=False,
            final_message="",
            error="LLM call rejected (content_filter): Azure ContentPolicyViolationError",
            error_kind="content_filter",
        )
    )
    tool = ParallelAgentTool(sub_agent_spawner=spawner)

    output = await tool._execute(
        missions=[{"mission": "research X", "specialist": "research_agent"}],
        max_concurrency=1,
        _parent_session_id="parent",
    )

    assert output["success"] is False
    assert output["failed"] == 1
    entry = output["results"][0]
    assert entry["error_kind"] == "content_filter"
    assert "content_filter" in entry["error"]
    # The historical empty-string regression: error MUST not be falsy here.
    assert entry["error"]


@pytest.mark.asyncio
async def test_parallel_tool_passes_through_none_kind_on_success() -> None:
    spawner = _FakeSpawner(
        SubAgentResult(
            session_id="s1",
            status="completed",
            success=True,
            final_message="all done",
            error=None,
            error_kind=None,
        )
    )
    tool = ParallelAgentTool(sub_agent_spawner=spawner)

    output = await tool._execute(
        missions=[{"mission": "ok task", "specialist": "research_agent"}],
        max_concurrency=1,
        _parent_session_id="parent",
    )

    assert output["success"] is True
    entry = output["results"][0]
    assert entry["error"] is None
    assert entry["error_kind"] is None
    assert entry["result"] == "all done"


@pytest.mark.asyncio
async def test_parallel_tool_tags_unhandled_exception_as_kind_exception() -> None:
    """Spawner exceptions get the explicit ``exception`` kind, not silently ''."""

    class _BrokenSpawner:
        async def spawn(self, _spec: Any) -> SubAgentResult:
            raise RuntimeError("spawner blew up")

    tool = ParallelAgentTool(sub_agent_spawner=_BrokenSpawner())

    output = await tool._execute(
        missions=[{"mission": "boom", "specialist": "x"}],
        max_concurrency=1,
        _parent_session_id="parent",
    )

    entry = output["results"][0]
    assert entry["success"] is False
    assert entry["error_kind"] == "exception"
    assert "spawner blew up" in entry["error"]
