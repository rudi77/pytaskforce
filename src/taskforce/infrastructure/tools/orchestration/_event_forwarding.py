"""Shared helper for forwarding sub-agent stream events to a parent sink.

The sub-agent orchestration tools (``AgentTool``, ``ParallelAgentTool``,
``SubAgentTool``) all spawn an isolated sub-agent and historically called
``agent.execute(...)``, which collapsed the entire sub-execution into a
single ``ExecutionResult``.  The intermediate ``tool_call`` / ``tool_result``
events were lost, so the management UI showed only the parent's call into
the sub-agent.

This module centralises the streaming alternative: iterate
``agent.execute_stream(...)``, annotate each event with the agent's
position in the hierarchy (``agent_path``, ``parent_session_id``,
``source_agent``) and push them into an ``asyncio.Queue`` owned by the
root execution.  The root's tool-call pump (``_execute_tool_calls_with_event_pump``
in ``planning/tool_execution.py``) drains the queue and yields the events
back into the streaming response.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from taskforce.core.domain.enums import EventType, ExecutionStatus
from taskforce.core.domain.models import StreamEvent

if TYPE_CHECKING:
    from taskforce.core.domain.agent import Agent


# Events that describe sub-agent lifecycle but do not represent actual
# work — they would clutter the parent stream without adding signal.
_SUPPRESSED_FORWARD_EVENTS = frozenset(
    {EventType.STARTED, EventType.COMPLETE}
)


@dataclass
class SubAgentExecutionOutcome:
    """Final outcome captured while streaming a sub-agent."""

    status: str = ExecutionStatus.COMPLETED.value
    final_message: str = ""
    interrupt: dict[str, Any] | None = None

    @property
    def success(self) -> bool:
        return self.status in (
            ExecutionStatus.COMPLETED.value,
            ExecutionStatus.PAUSED.value,
        )


async def run_sub_agent_with_forwarding(
    sub_agent: Agent,
    *,
    mission: str,
    session_id: str,
    parent_session_id: str,
    parent_event_sink: asyncio.Queue[StreamEvent] | None,
    parent_agent_path: list[str],
    specialist: str | None,
) -> SubAgentExecutionOutcome:
    """Run a sub-agent via ``execute_stream`` and forward events upward.

    Args:
        sub_agent: The sub-agent instance to execute.
        mission: Mission text for the sub-agent.
        session_id: Sub-agent's own session ID.
        parent_session_id: Parent session ID (used to annotate events).
        parent_event_sink: Queue to push annotated events to.  When
            ``None`` the events are simply consumed (no forwarding) — this
            keeps the orchestration tools usable when the caller didn't
            install a sink (e.g. unit tests, CLI synchronous flows).
        parent_agent_path: The parent's agent_path; the sub-agent's path
            is computed as ``parent_agent_path + [specialist]``.
        specialist: Specialist label used in ``agent_path`` and
            ``source_agent`` annotations.  Falls back to ``"agent"`` when
            ``None``.

    Returns:
        ``SubAgentExecutionOutcome`` with the final status and message.
    """
    label = specialist or "agent"
    own_path = list(parent_agent_path) + [label]

    # Wire the sink + path into the sub-agent so its own ``_execute_tool``
    # forwards nested sub-agent events through the same root sink.
    sub_agent._sub_agent_event_sink = parent_event_sink
    sub_agent._agent_path = own_path

    outcome = SubAgentExecutionOutcome()
    async for event in sub_agent.execute_stream(mission=mission, session_id=session_id):
        _track_outcome(event, outcome)
        if parent_event_sink is None:
            continue
        if event.event_type in _SUPPRESSED_FORWARD_EVENTS:
            continue
        # COMPLETE is handled above; other lifecycle markers (STEP_START,
        # TOOL_CALL, TOOL_RESULT, FINAL_ANSWER, ERROR, …) all forward.
        annotated = _annotate(event, own_path, parent_session_id, label)
        await parent_event_sink.put(annotated)

    return outcome


def _track_outcome(event: StreamEvent, outcome: SubAgentExecutionOutcome) -> None:
    """Update ``outcome`` from terminal lifecycle events."""
    et = event.event_type
    if et == EventType.FINAL_ANSWER:
        content = event.data.get("content")
        if isinstance(content, str) and content:
            outcome.final_message = content
    elif et == EventType.ERROR:
        outcome.status = ExecutionStatus.FAILED.value
    elif et == EventType.INTERRUPTED:
        outcome.status = ExecutionStatus.PAUSED.value
        outcome.interrupt = dict(event.data)
        if not outcome.final_message:
            outcome.final_message = "Execution paused by user."
    elif et == EventType.COMPLETE:
        # The COMPLETE event carries the authoritative final state.
        status = event.data.get("status")
        if isinstance(status, str) and status:
            outcome.status = status
        msg = event.data.get("final_message")
        if isinstance(msg, str) and msg:
            outcome.final_message = msg


def _annotate(
    event: StreamEvent,
    agent_path: list[str],
    parent_session_id: str,
    source_agent: str,
) -> StreamEvent:
    """Return a copy of ``event`` with sub-agent provenance keys merged into data."""
    data = dict(event.data) if isinstance(event.data, dict) else {"value": event.data}
    # Don't overwrite existing annotations from deeper nesting.
    data.setdefault("agent_path", list(agent_path))
    data.setdefault("parent_session_id", parent_session_id)
    data.setdefault("source_agent", source_agent)
    return StreamEvent(
        event_type=event.event_type,
        data=data,
        timestamp=event.timestamp,
    )
