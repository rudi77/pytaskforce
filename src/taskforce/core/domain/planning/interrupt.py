"""Cooperative interrupt handling for planning strategies.

Mirrors the ``_handle_ask_user`` pause/resume mechanism.  When a user
requests an interrupt (via CLI Ctrl+C or the REST cancel endpoint), the
ReAct loop calls :func:`_handle_interrupt` at the next iteration
boundary.  The handler persists the full execution state using the same
``paused_*`` state keys as ``ask_user``, so the existing
``_resume_from_pause`` logic can pick execution back up on the next turn.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from taskforce.core.domain.enums import EventType
from taskforce.core.domain.models import StreamEvent
from taskforce.core.domain.planning.utils import _persist_active_skill
from taskforce.core.interfaces.logging import LoggerProtocol

if TYPE_CHECKING:
    from taskforce.core.domain.agent import Agent


async def _handle_interrupt(
    agent: Agent,
    session_id: str,
    state: dict[str, Any],
    logger: LoggerProtocol,
    step: int,
    plan: list[str] | None = None,
    plan_step_idx: int | None = None,
    plan_iteration: int | None = None,
    paused_phase: str | None = None,
    reason: str = "user_requested",
) -> AsyncIterator[StreamEvent]:
    """Persist state and emit an ``INTERRUPTED`` event.

    Called from the top of a planning-strategy loop when
    ``agent.is_interrupt_requested()`` is true.  Leaves the agent in a
    resumable state: the next call to ``execute_stream`` with the same
    ``session_id`` will transparently restore messages, step counter and
    plan progress via :func:`_resume_from_pause`.
    """
    timestamp = datetime.now(UTC).isoformat()

    state["pending_interrupt"] = {"reason": reason, "timestamp": timestamp}
    state["paused_messages"] = list(agent.context.messages)
    state["paused_step"] = step
    if plan is not None:
        state["paused_plan"] = plan
    if plan_step_idx is not None:
        state["paused_plan_step_idx"] = plan_step_idx
    if plan_iteration is not None:
        state["paused_plan_iteration"] = plan_iteration
    if paused_phase is not None:
        state["paused_phase"] = paused_phase
    _persist_active_skill(agent, state)
    await agent.state_store.save(session_id=session_id, state=state, planner=agent.planner)

    # Clear the flag so a later resume doesn't immediately re-trigger.
    agent.clear_interrupt()

    logger.info(
        "execution_interrupted",
        session_id=session_id,
        reason=reason,
        step=step,
        paused_phase=paused_phase,
    )

    yield StreamEvent(
        event_type=EventType.INTERRUPTED,
        data={"reason": reason, "timestamp": timestamp, "step": step},
    )
