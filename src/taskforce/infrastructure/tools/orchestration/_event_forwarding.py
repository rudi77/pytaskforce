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
from typing import TYPE_CHECKING

from taskforce.core.domain.enums import EventType, ExecutionStatus
from taskforce.core.domain.models import StreamEvent

if TYPE_CHECKING:
    from taskforce.core.domain.agent import Agent


# Sub-agent events that are safe to forward into the *parent's* stream.
#
# Parent-stream consumers (e.g. ``simple_chat._stream_response``,
# ``api/routes/conversations.py``) treat ``LLM_TOKEN`` and
# ``FINAL_ANSWER`` as the parent assistant's reply: they append the
# token text into the rendered response and persist it as the
# assistant message.  Forwarding those events from a sub-agent would
# splice the sub-agent's internal text into the parent's reply (and on
# parent failure, persist the sub-agent's text as the assistant
# message).  Likewise ``ERROR`` and ``INTERRUPTED`` are translated
# into the sub-agent tool's return value (failed/paused status) by
# ``_track_outcome``; forwarding the raw events would trigger
# parent-level error / interrupt UX for what is really an internal
# sub-agent state.
#
# ``ASK_USER`` is the exception: parent-stream consumers only render
# the question and pause the chat when they observe this event, and
# ``LeanAgent.execute_stream`` does not translate it into a paused
# COMPLETE status, so dropping it would silently turn a sub-agent
# that needs user input into a "no-result" success.  It must reach
# the consumer.
#
# What the parent additionally benefits from is the sub-agent's
# tool-call trace (so the UI can render nested tool calls) and the
# step / token accounting events.  Everything else is intentionally
# dropped.
_FORWARDED_EVENT_TYPES = frozenset(
    {
        EventType.TOOL_CALL,
        EventType.TOOL_RESULT,
        EventType.STEP_START,
        EventType.TOKEN_USAGE,
        EventType.ASK_USER,
    }
)


@dataclass
class SubAgentExecutionOutcome:
    """Final outcome captured while streaming a sub-agent."""

    status: str = ExecutionStatus.COMPLETED.value
    final_message: str = ""

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
        if event.event_type not in _FORWARDED_EVENT_TYPES:
            # FINAL_ANSWER / ERROR / LLM_TOKEN / etc. are tracked
            # locally by ``_track_outcome`` (and surfaced via the
            # sub-agent tool's return value), but must not bleed into
            # the parent stream — see ``_FORWARDED_EVENT_TYPES``.
            continue
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
        if not outcome.final_message:
            outcome.final_message = "Execution paused by user."
    elif et == EventType.ASK_USER:
        # ``LeanAgent.execute_stream`` does not translate ``ASK_USER``
        # into a paused COMPLETE status, so the only signal that the
        # sub-agent is waiting for user input is the event itself.
        # Reflect that in the outcome so the orchestration tool's
        # return value carries a meaningful question instead of an
        # empty "completed" string.
        outcome.status = ExecutionStatus.PAUSED.value
        question = event.data.get("question")
        if isinstance(question, str) and question and not outcome.final_message:
            outcome.final_message = question
    elif et == EventType.COMPLETE:
        # The COMPLETE event carries the authoritative final state —
        # but only when it actually advances the outcome. ASK_USER /
        # INTERRUPTED already set ``status=paused`` above; the
        # subsequent COMPLETE (which LeanAgent.execute_stream emits
        # with ``status=completed`` after ``ASK_USER`` because it has
        # no pause branch) must not downgrade that.
        status = event.data.get("status")
        if (
            isinstance(status, str)
            and status
            and outcome.status != ExecutionStatus.PAUSED.value
        ):
            outcome.status = status
        msg = event.data.get("final_message")
        if isinstance(msg, str) and msg and not outcome.final_message:
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
