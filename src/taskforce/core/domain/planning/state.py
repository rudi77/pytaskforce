"""State loading, resuming, and persistence functions for planning strategies."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

from taskforce.core.domain.enums import EventType
from taskforce.core.domain.models import StreamEvent
from taskforce.core.domain.planning.types import DEFAULT_PLAN, ResumeContext
from taskforce.core.domain.planning.utils import _persist_active_skill
from taskforce.core.interfaces.logging import LoggerProtocol

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

    from taskforce.core.domain.agent import Agent


# ---------------------------------------------------------------------------
# Resume from pause
# ---------------------------------------------------------------------------


def _resume_from_pause(
    state: dict[str, Any],
    mission: str,
    logger: LoggerProtocol,
    session_id: str,
) -> ResumeContext | None:
    """Try to resume from an ``ask_user`` pause.

    If the *state* dict contains a ``pending_question`` key the function
    restores messages, injects the user's answer (passed as *mission*),
    clears the pause markers from *state* and returns a
    :class:`ResumeContext`.  Returns ``None`` when there is nothing to
    resume.
    """
    if state.get("pending_question") is None or state.get("paused_messages") is None:
        return None

    messages: list[dict[str, Any]] = state.get("paused_messages", [])
    pending_question: dict[str, Any] = state.get("pending_question", {})
    tool_call_id: str = state.get("paused_tool_call_id", "ask_user_call")
    step: int = state.get("paused_step", 0)
    plan: list[str] = state.get("paused_plan", DEFAULT_PLAN)
    plan_step_idx: int = state.get("paused_plan_step_idx", 1)
    plan_iteration: int = state.get("paused_plan_iteration", 1)
    phase: str = state.get("paused_phase", "act")

    user_answer = mission.strip()
    messages.append(
        {
            "role": "tool",
            "tool_call_id": tool_call_id,
            "name": "ask_user",
            "content": json.dumps(
                {
                    "success": True,
                    "output": user_answer,
                    "question": pending_question.get("question", ""),
                    "missing": pending_question.get("missing", []),
                    "resume_instruction": (
                        "Interpret 'output' strictly as the answer to the previous "
                        "ask_user question. It is not a new mission."
                    ),
                }
            ),
        }
    )

    for key in [
        "pending_question",
        "paused_messages",
        "paused_tool_call_id",
        "paused_step",
        "paused_plan",
        "paused_plan_step_idx",
        "paused_plan_iteration",
        "paused_phase",
    ]:
        state.pop(key, None)

    logger.info("resumed_from_ask_user", session_id=session_id, user_answer=user_answer[:100])

    return ResumeContext(
        messages=messages,
        step=step,
        plan=plan,
        plan_step_idx=plan_step_idx,
        plan_iteration=plan_iteration,
        phase=phase,
    )


async def _load_and_resume_state(
    agent: Agent,
    mission: str,
    session_id: str,
    logger: LoggerProtocol,
) -> tuple[dict[str, Any], ResumeContext | None]:
    """Load persisted state, restore planner, and attempt resume.

    Returns:
        Tuple of (state_dict, resume_context_or_none).
    """
    state = await agent.state_manager.load_state(session_id) or {}
    if agent._planner and state.get("planner_state"):
        agent._planner.set_state(state["planner_state"])
    # Restore active skill from persisted state
    saved_skill = state.get("active_skill")
    if saved_skill and agent.skill_manager:
        agent.skill_manager.activate_skill(saved_skill)
        logger.debug("skill_restored_from_state", skill=saved_skill)
    # Load long-term memories once at session start for prompt injection (lazy).
    # Pass the mission so contextually relevant memories are boosted.
    await agent.load_memory_context(mission=mission)
    resume = _resume_from_pause(state, mission, logger, session_id)
    return state, resume


async def _save_and_emit_max_steps(
    agent: Agent,
    session_id: str,
    state: dict[str, Any],
    progress: int,
) -> AsyncIterator[StreamEvent]:
    """Emit max-steps error if needed, then persist final state.

    Always saves state at the end.  Yields an error event only when
    ``progress >= agent.max_steps``.
    """
    if progress >= agent.max_steps:
        yield StreamEvent(
            event_type=EventType.ERROR,
            data={"message": f"Exceeded max steps ({agent.max_steps})"},
        )
    _persist_active_skill(agent, state)
    await agent.state_store.save(session_id=session_id, state=state, planner=agent.planner)
