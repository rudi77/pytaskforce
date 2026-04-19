"""State loading, resuming, and persistence functions for planning strategies."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

from taskforce.core.domain.enums import EventType
from taskforce.core.domain.models import StreamEvent
from taskforce.core.domain.planning.llm_interactions import _generate_and_register_plan
from taskforce.core.domain.planning.types import (
    DEFAULT_PLAN,
    ExecutionInit,
    ResumeContext,
)
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
    """Try to resume from a pause (``ask_user`` or cooperative interrupt).

    Two resume triggers are supported:

    * ``pending_question`` — an ``ask_user`` pause.  The user's answer
      (passed as *mission*) is injected as a synthetic tool result so
      the next LLM call sees it as the answer to the outstanding
      question.
    * ``pending_interrupt`` — a cooperative interrupt pause.  Messages
      and plan progress are restored; the new *mission* is treated as a
      fresh user turn and appended normally by the caller.

    Returns ``None`` when neither marker is present in *state*.
    """
    has_question = state.get("pending_question") is not None
    has_interrupt = state.get("pending_interrupt") is not None
    if (not has_question and not has_interrupt) or state.get("paused_messages") is None:
        return None

    messages: list[dict[str, Any]] = state.get("paused_messages", [])
    step: int = state.get("paused_step", 0)
    plan: list[str] = state.get("paused_plan", DEFAULT_PLAN)
    plan_step_idx: int = state.get("paused_plan_step_idx", 1)
    plan_iteration: int = state.get("paused_plan_iteration", 1)
    phase: str = state.get("paused_phase", "act")

    if has_question:
        pending_question: dict[str, Any] = state.get("pending_question", {})
        tool_call_id: str = state.get("paused_tool_call_id", "ask_user_call")
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
        logger.info("resumed_from_ask_user", session_id=session_id, user_answer=user_answer[:100])
    else:
        # Interrupt resume — treat the new mission as a fresh user turn and
        # append it so the LLM sees the continuation input on the next call.
        interrupt_info: dict[str, Any] = state.get("pending_interrupt", {})
        new_user_turn = mission.strip()
        if new_user_turn:
            messages.append({"role": "user", "content": new_user_turn})
        logger.info(
            "resumed_from_interrupt",
            session_id=session_id,
            reason=interrupt_info.get("reason"),
            paused_step=step,
            has_new_turn=bool(new_user_turn),
        )

    for key in [
        "pending_question",
        "pending_interrupt",
        "paused_messages",
        "paused_tool_call_id",
        "paused_step",
        "paused_plan",
        "paused_plan_step_idx",
        "paused_plan_iteration",
        "paused_phase",
    ]:
        state.pop(key, None)

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


async def _initialize_execution_context(
    agent: Agent,
    mission: str,
    session_id: str,
    logger: LoggerProtocol,
    *,
    generate_plan: bool = False,
    max_plan_steps: int = 12,
) -> AsyncIterator[StreamEvent | ExecutionInit]:
    """Shared initialize-or-resume phase for all planning strategies.

    Loads persisted state, either restores the paused context or initializes
    a fresh one, and optionally generates an upfront plan. Yields any
    plan-generation :class:`StreamEvent` s live and finishes by yielding a
    single :class:`ExecutionInit` sentinel that the caller picks up.

    Usage::

        init: ExecutionInit | None = None
        async for item in _initialize_execution_context(...):
            if isinstance(item, ExecutionInit):
                init = item
            else:
                yield item
        assert init is not None
    """
    state, resume = await _load_and_resume_state(agent, mission, session_id, logger)

    if resume is not None:
        agent.context.restore(resume.messages)
        yield ExecutionInit(state=state, resume=resume, plan=resume.plan)
        return

    plan: list[str] = DEFAULT_PLAN
    if generate_plan:
        async for item in _generate_and_register_plan(
            agent,
            mission,
            logger,
            max_plan_steps,
            session_id=session_id,
            state=state,
        ):
            if isinstance(item, list):
                plan = item
            else:
                yield item

    agent.context.initialize(mission, state, agent._base_system_prompt)
    yield ExecutionInit(state=state, resume=None, plan=plan)


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
