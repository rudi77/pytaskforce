"""LLM calling functions for planning strategies."""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import TYPE_CHECKING, Any

from taskforce.core.domain.enums import (
    EventType,
    LLMStreamEventType,
    MessageRole,
    PlannerAction,
)
from taskforce.core.domain.models import StreamEvent
from taskforce.core.domain.planning.types import DEFAULT_PLAN
from taskforce.core.domain.planning.utils import _parse_plan_steps, _persist_active_skill
from taskforce.core.interfaces.logging import LoggerProtocol

if TYPE_CHECKING:
    from taskforce.core.domain.agent import Agent


async def _generate_plan(
    agent: Agent,
    mission: str,
    logger: LoggerProtocol,
    conversation_context: list[dict[str, Any]] | None = None,
) -> list[str]:
    """Generate plan steps via LLM.

    Passes ``"planning"`` as the model hint so that an LLMRouter (if active)
    can route this call to a model suited for task decomposition.

    Args:
        agent: The agent instance.
        mission: The current mission/user message.
        logger: Logger instance.
        conversation_context: Optional prior conversation messages
            (user/assistant pairs) so the planner knows what was already done.
    """
    messages: list[dict[str, Any]] = [
        {"role": MessageRole.SYSTEM.value, "content": agent.system_prompt},
    ]
    # Include conversation history so the planner is aware of prior work
    if conversation_context:
        for msg in conversation_context:
            role = msg.get("role")
            content = msg.get("content", "")
            if role in ("user", "assistant") and content:
                messages.append({"role": role, "content": content})
    messages.append(
        {
            "role": MessageRole.USER.value,
            "content": (
                f"{mission}\n\nCreate a concise step-by-step plan. "
                "Consider what has already been done in the conversation above. "
                "Do NOT repeat completed work. "
                "Return ONLY a JSON array."
            ),
        },
    )
    result = await agent.llm_provider.complete(
        messages=messages,
        model="planning",
        tools=None,
        tool_choice="none",
        temperature=0.1,
        metadata={"step_number": None, "phase": "planning"},
    )
    if not result.get("success"):
        return []
    return _parse_plan_steps(result.get("content", ""), logger)


async def _stream_final_response(
    agent: Agent,
    messages: list[dict[str, Any]],
) -> AsyncIterator[StreamEvent]:
    """Generate a final-answer LLM call, streaming when possible.

    Passes ``"summarizing"`` as the model hint so that an LLMRouter
    can route this to a fast/cheap model.

    Yields :data:`EventType.LLM_TOKEN`, :data:`EventType.TOKEN_USAGE`,
    and :data:`EventType.FINAL_ANSWER` events.
    """
    messages.append(
        {
            "role": MessageRole.USER.value,
            "content": "All steps complete. Provide final response.",
        }
    )

    # Try fast model first; fall back to main model if content-filtered.
    final = ""
    for model_hint in ("summarizing", "reasoning"):
        try:
            if hasattr(agent.llm_provider, "complete_stream"):
                async for chunk in agent.llm_provider.complete_stream(
                    messages=messages,
                    model=model_hint,
                    tools=None,
                    tool_choice="none",
                    temperature=0.2,
                    metadata={"step_number": None, "phase": "summarizing"},
                ):
                    if (
                        chunk.get("type") == LLMStreamEventType.TOKEN.value
                        and chunk.get("content")
                    ):
                        yield StreamEvent(
                            event_type=EventType.LLM_TOKEN,
                            data={"content": chunk["content"]},
                        )
                        final += chunk["content"]
                    elif (
                        chunk.get("type") == LLMStreamEventType.STREAM_RESTART.value
                    ):
                        # Content-filter recovery is re-streaming this
                        # summary; drop the partial output and signal
                        # downstream so any UI rendering is reset.
                        final = ""
                        yield StreamEvent(
                            event_type=EventType.LLM_STREAM_RESTART,
                            data={
                                "reason": chunk.get("reason", "unknown"),
                                "stage": chunk.get("stage", ""),
                            },
                        )
                    elif (
                        chunk.get("type") == LLMStreamEventType.DONE.value
                        and chunk.get("usage")
                    ):
                        yield StreamEvent(
                            event_type=EventType.TOKEN_USAGE,
                            data=chunk["usage"],
                        )
            else:
                r = await agent.llm_provider.complete(
                    messages=messages,
                    model=model_hint,
                    tools=None,
                    tool_choice="none",
                    temperature=0.2,
                    metadata={"step_number": None, "phase": "summarizing"},
                )
                final = r.get("content", "") if r.get("success") else ""
                if r.get("usage"):
                    yield StreamEvent(
                        event_type=EventType.TOKEN_USAGE,
                        data=r["usage"],
                    )
            if final:
                break  # Success — no need to try fallback model
        except Exception:
            final = ""  # Reset and try next model

    if final:
        yield StreamEvent(event_type=EventType.FINAL_ANSWER, data={"content": final})
    else:
        yield StreamEvent(
            event_type=EventType.FINAL_ANSWER,
            data={"content": "Plan completed."},
        )


async def _salvage_answer(
    agent: Agent,
    messages: list[dict[str, Any]],
    logger: LoggerProtocol,
) -> str:
    """Force a final answer from the LLM when execution stalls or exceeds max steps.

    Makes one last LLM call WITHOUT tools, asking the model to produce the best
    answer it can from the conversation context so far. This prevents returning
    empty "Execution failed" responses.

    Returns:
        The salvage answer text, or empty string if the LLM call fails.
    """
    salvage_messages = messages + [
        {
            "role": MessageRole.USER.value,
            "content": (
                "[System: Execution is ending. You MUST provide your best answer NOW "
                "based on all information gathered so far. Do NOT call any tools. "
                "Respond with ONLY the answer, nothing else.]"
            ),
        }
    ]
    # Try fast model first, fall back to main model if content-filtered.
    for model_hint in ("summarizing", "reasoning"):
        try:
            result = await agent.llm_provider.complete(
                messages=salvage_messages,
                model=model_hint,
                tools=None,
                tool_choice=None,
                temperature=0.0,
            )
            answer = (result.get("content") or "").strip()
            if answer:
                logger.info("salvage_answer_generated", length=len(answer), model=model_hint)
                return answer
        except Exception as e:
            logger.warning(
                "salvage_answer_attempt_failed", model=model_hint, error=str(e)
            )
    return ""


async def _generate_and_register_plan(
    agent: Agent,
    mission: str,
    logger: LoggerProtocol,
    max_plan_steps: int,
    session_id: str | None = None,
    state: dict[str, Any] | None = None,
    conversation_context: list[dict[str, Any]] | None = None,
) -> AsyncIterator[StreamEvent | list[str]]:
    """Generate plan steps, register with planner, yield events.

    Yields:
        A single ``list[str]`` (the plan steps) first, then zero or one
        ``StreamEvent`` if the planner emitted a plan-updated event.

    The caller should iterate and pick up the ``list[str]`` result::

        plan: list[str] = DEFAULT_PLAN
        async for item in _generate_and_register_plan(...):
            if isinstance(item, list):
                plan = item
            else:
                yield item  # StreamEvent
    """
    # If no explicit context, try extracting from state
    if conversation_context is None and state:
        conversation_context = state.get("conversation_history")
    steps = (await _generate_plan(agent, mission, logger, conversation_context) or DEFAULT_PLAN)[
        :max_plan_steps
    ]

    if agent._planner:
        await agent._planner.execute(action=PlannerAction.CREATE_PLAN.value, tasks=steps)
        yield steps
        yield StreamEvent(
            event_type=EventType.PLAN_UPDATED,
            data={
                "action": PlannerAction.CREATE_PLAN.value,
                "steps": steps,
                "plan": agent._planner.get_plan_summary(),
            },
        )
    else:
        yield steps

    if session_id is not None and state is not None:
        _persist_active_skill(agent, state)
        await agent.state_store.save(session_id=session_id, state=state, planner=agent.planner)
