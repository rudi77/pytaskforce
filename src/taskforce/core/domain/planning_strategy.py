"""Planning strategies for Agent execution.

Defines the :class:`PlanningStrategy` protocol and four concrete
implementations:

* :class:`NativeReActStrategy` — pure ReAct loop
* :class:`PlanAndExecuteStrategy` — plan first, execute sequentially
* :class:`PlanAndReactStrategy` — alias for NativeReAct with plan
* :class:`SparStrategy` — Sense → Plan → Act → Reflect cycle

Shared helpers live in :mod:`planning_helpers` to keep this module
focused on strategy orchestration.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import TYPE_CHECKING, Any, Protocol

from taskforce.core.domain.enums import (
    EventType,
    ExecutionStatus,
    MessageRole,
    PlannerAction,
)
from taskforce.core.domain.models import ExecutionResult, StreamEvent
from taskforce.core.domain.planning_helpers import (
    DEFAULT_PLAN,
    _collect_result,
    _generate_and_register_plan,
    _llm_call_and_process,
    _load_and_resume_state,
    _react_loop,
    _rebuild_system_prompt,
    _save_and_emit_max_steps,
    _stream_final_response,
)
from taskforce.core.interfaces.logging import LoggerProtocol

if TYPE_CHECKING:
    from taskforce.core.domain.agent import Agent


class PlanningStrategy(Protocol):
    """Protocol for planning strategies."""

    name: str

    async def execute(
        self, agent: Agent, mission: str, session_id: str
    ) -> ExecutionResult: ...

    async def execute_stream(
        self, agent: Agent, mission: str, session_id: str
    ) -> AsyncIterator[StreamEvent]: ...


# ---------------------------------------------------------------------------
# NativeReActStrategy
# ---------------------------------------------------------------------------


class NativeReActStrategy:
    """ReAct loop with optional upfront plan generation."""

    name = "native_react"

    def __init__(
        self,
        generate_plan_first: bool = False,
        max_plan_steps: int = 12,
        logger: LoggerProtocol | None = None,
    ):
        self.generate_plan_first = generate_plan_first
        self.max_plan_steps = max_plan_steps
        self._logger = logger

    async def execute(
        self, agent: Agent, mission: str, session_id: str
    ) -> ExecutionResult:
        return await _collect_result(
            session_id, self.execute_stream(agent, mission, session_id)
        )

    async def execute_stream(
        self, agent: Agent, mission: str, session_id: str
    ) -> AsyncIterator[StreamEvent]:
        logger = self._logger or agent.logger
        state, resume = await _load_and_resume_state(
            agent, mission, session_id, logger
        )

        if resume is not None:
            messages = resume.messages
            step = resume.step
        else:
            if self.generate_plan_first:
                async for item in _generate_and_register_plan(
                    agent, mission, logger, self.max_plan_steps,
                    session_id=session_id, state=state,
                ):
                    if isinstance(item, StreamEvent):
                        yield item

            messages = agent._build_initial_messages(mission, state)
            step = 0

        async for e in _react_loop(
            agent, mission, session_id, messages, state,
            start_step=step, logger=logger,
        ):
            yield e

        await agent.state_store.save(
            session_id=session_id, state=state, planner=agent.planner
        )


# ---------------------------------------------------------------------------
# PlanAndExecuteStrategy
# ---------------------------------------------------------------------------


class PlanAndExecuteStrategy:
    """Generate plan, execute steps sequentially."""

    name = "plan_and_execute"

    def __init__(
        self,
        max_step_iterations: int = 4,
        max_plan_steps: int = 12,
        logger: LoggerProtocol | None = None,
    ):
        self.max_step_iterations = max_step_iterations
        self.max_plan_steps = max_plan_steps
        self.logger = logger

    async def execute(
        self, agent: Agent, mission: str, session_id: str
    ) -> ExecutionResult:
        return await _collect_result(
            session_id, self.execute_stream(agent, mission, session_id)
        )

    async def execute_stream(
        self, agent: Agent, mission: str, session_id: str
    ) -> AsyncIterator[StreamEvent]:
        logger = self.logger or agent.logger
        state, resume = await _load_and_resume_state(
            agent, mission, session_id, logger
        )

        if resume is not None:
            messages = resume.messages
            progress = resume.step
            plan = resume.plan
            start_idx = resume.plan_step_idx
            start_it = resume.plan_iteration
        else:
            messages = agent._build_initial_messages(mission, state)
            plan = DEFAULT_PLAN
            async for item in _generate_and_register_plan(
                agent, mission, logger, self.max_plan_steps,
            ):
                if isinstance(item, list):
                    plan = item
                elif isinstance(item, StreamEvent):
                    yield item
            progress = 0
            start_idx = 1
            start_it = 1

        for idx, desc in enumerate(plan, 1):
            if idx < start_idx:
                continue
            if progress >= agent.max_steps:
                break

            for it in range(1, self.max_step_iterations + 1):
                if idx == start_idx and it < start_it:
                    continue
                if progress >= agent.max_steps:
                    break

                await agent.record_heartbeat(
                    session_id,
                    ExecutionStatus.PENDING.value,
                    {"plan_step": idx, "iteration": it},
                )
                _rebuild_system_prompt(agent, messages, mission, state)
                messages.append(
                    {
                        "role": MessageRole.USER.value,
                        "content": (
                            f"Execute step {idx}: {desc}\n"
                            "Call tools or respond when done."
                        ),
                    }
                )

                async for outcome, events in _llm_call_and_process(
                    agent, messages, session_id, progress + 1,
                    state, logger, model_hint="acting",
                    plan=plan, plan_step_idx=idx,
                    plan_iteration=it,
                ):
                    for event in events:
                        yield event

                    if outcome == "paused":
                        return
                    if outcome == "tool_calls":
                        progress += 1
                    elif outcome == "content":
                        if agent._planner:
                            await agent._planner.execute(
                                action=PlannerAction.MARK_DONE.value,
                                step_index=idx,
                            )
                            yield StreamEvent(
                                event_type=EventType.PLAN_UPDATED,
                                data={
                                    "action": PlannerAction.MARK_DONE.value,
                                    "step": idx,
                                    "status": ExecutionStatus.COMPLETED.value,
                                    "plan": agent._planner.get_plan_summary(),
                                },
                            )
                        break
                    # "error" and "empty" fall through to next iteration

        if progress < agent.max_steps:
            async for e in _stream_final_response(agent, messages):
                yield e

        async for e in _save_and_emit_max_steps(
            agent, session_id, state, progress
        ):
            yield e


# ---------------------------------------------------------------------------
# PlanAndReactStrategy
# ---------------------------------------------------------------------------


class PlanAndReactStrategy:
    """Alias for NativeReActStrategy with generate_plan_first=True."""

    name = "plan_and_react"

    def __init__(
        self,
        max_plan_steps: int = 12,
        logger: LoggerProtocol | None = None,
    ):
        self._delegate = NativeReActStrategy(
            generate_plan_first=True,
            max_plan_steps=max_plan_steps,
            logger=logger,
        )

    async def execute(
        self, agent: Agent, mission: str, session_id: str
    ) -> ExecutionResult:
        return await self._delegate.execute(agent, mission, session_id)

    async def execute_stream(
        self, agent: Agent, mission: str, session_id: str
    ) -> AsyncIterator[StreamEvent]:
        async for e in self._delegate.execute_stream(
            agent, mission, session_id
        ):
            yield e


# ---------------------------------------------------------------------------
# SparStrategy
# ---------------------------------------------------------------------------


class SparStrategy:
    """SPAR planning strategy with Sense, Plan, Act, Reflect phases."""

    name = "spar"

    def __init__(
        self,
        max_step_iterations: int = 3,
        max_plan_steps: int = 12,
        reflect_every_step: bool = True,
        max_reflection_iterations: int = 2,
        logger: LoggerProtocol | None = None,
    ):
        self.max_step_iterations = max_step_iterations
        self.max_plan_steps = max_plan_steps
        self.reflect_every_step = reflect_every_step
        self.max_reflection_iterations = max_reflection_iterations
        self.logger = logger

    async def execute(
        self, agent: Agent, mission: str, session_id: str
    ) -> ExecutionResult:
        return await _collect_result(
            session_id, self.execute_stream(agent, mission, session_id)
        )

    async def execute_stream(
        self, agent: Agent, mission: str, session_id: str
    ) -> AsyncIterator[StreamEvent]:
        logger = self.logger or agent.logger
        state, resume = await _load_and_resume_state(
            agent, mission, session_id, logger
        )

        if resume is not None:
            messages = resume.messages
            progress = resume.step
            plan = resume.plan
            start_idx = resume.plan_step_idx
            start_it = resume.plan_iteration
            start_phase = resume.phase
        else:
            messages = agent._build_initial_messages(mission, state)
            plan = DEFAULT_PLAN
            async for item in _generate_and_register_plan(
                agent, mission, logger, self.max_plan_steps,
            ):
                if isinstance(item, list):
                    plan = item
                elif isinstance(item, StreamEvent):
                    yield item
            progress = 0
            start_idx = 1
            start_it = 1
            start_phase = "act"

        for idx, desc in enumerate(plan, 1):
            if idx < start_idx:
                continue
            if progress >= agent.max_steps:
                break

            for it in range(1, self.max_step_iterations + 1):
                if idx == start_idx and it < start_it:
                    continue
                if progress >= agent.max_steps:
                    break

                await agent.record_heartbeat(
                    session_id,
                    ExecutionStatus.PENDING.value,
                    {"plan_step": idx, "iteration": it},
                )
                _rebuild_system_prompt(agent, messages, mission, state)

                reflect_only = (
                    idx == start_idx
                    and it == start_it
                    and start_phase == "reflect"
                )
                if not reflect_only:
                    action_done, used_tools, paused, events = (
                        await _run_spar_action(
                            agent=agent,
                            messages=messages,
                            desc=desc,
                            session_id=session_id,
                            step=progress + 1,
                            state=state,
                            logger=logger,
                            plan=plan,
                            plan_step_idx=idx,
                            plan_iteration=it,
                        )
                    )
                    for event in events:
                        yield event
                    if paused:
                        return
                    if used_tools:
                        progress += 1
                    if not action_done:
                        continue

                    if agent._planner:
                        await agent._planner.execute(
                            action=PlannerAction.MARK_DONE.value,
                            step_index=idx,
                        )
                        yield StreamEvent(
                            event_type=EventType.PLAN_UPDATED,
                            data={
                                "action": PlannerAction.MARK_DONE.value,
                                "step": idx,
                                "status": ExecutionStatus.COMPLETED.value,
                                "plan": agent._planner.get_plan_summary(),
                            },
                        )

                if self.reflect_every_step:
                    reflect_used, paused, events = (
                        await _run_reflection_cycle(
                            agent=agent,
                            messages=messages,
                            prompt=(
                                "REFLECT: Review the result of the last "
                                "action step. Check correctness, edge cases, "
                                "tests, and security. If more info is needed, "
                                "ask_user. If validation tools should be "
                                "used, call them."
                            ),
                            session_id=session_id,
                            step=progress + 1,
                            state=state,
                            logger=logger,
                            plan=plan,
                            plan_step_idx=idx,
                            plan_iteration=it,
                            max_reflections=self.max_reflection_iterations,
                        )
                    )
                    for event in events:
                        yield event
                    if paused:
                        return
                    if reflect_used:
                        progress += 1

                break

        if progress < agent.max_steps:
            reflect_used, paused, events = (
                await _run_reflection_cycle(
                    agent=agent,
                    messages=messages,
                    prompt=(
                        "REFLECT: Review the overall outcome for the "
                        "mission. Verify quality, tests, and completeness. "
                        "If anything is missing, ask_user or call tools "
                        "to validate."
                    ),
                    session_id=session_id,
                    step=progress + 1,
                    state=state,
                    logger=logger,
                    plan=None,
                    plan_step_idx=None,
                    plan_iteration=None,
                    max_reflections=self.max_reflection_iterations,
                )
            )
            for event in events:
                yield event
            if paused:
                return
            if reflect_used:
                progress += 1

        if progress < agent.max_steps:
            async for e in _stream_final_response(agent, messages):
                yield e

        async for e in _save_and_emit_max_steps(
            agent, session_id, state, progress
        ):
            yield e


# ---------------------------------------------------------------------------
# SPAR helper functions
# ---------------------------------------------------------------------------


async def _run_spar_action(
    agent: Agent,
    messages: list[dict[str, Any]],
    desc: str,
    session_id: str,
    step: int,
    state: dict[str, Any],
    logger: LoggerProtocol,
    plan: list[str],
    plan_step_idx: int,
    plan_iteration: int,
) -> tuple[bool, bool, bool, list[StreamEvent]]:
    """Run the Act phase for a single plan step.

    Passes ``"acting"`` as the model hint for LLMRouter routing.
    Delegates to :func:`_llm_call_and_process` for the LLM call.

    Returns:
        Tuple of (action_done, used_tools, paused, events).
    """
    messages.append(
        {
            "role": MessageRole.USER.value,
            "content": (
                f"ACT: Execute step {plan_step_idx}: {desc}\n"
                "Call tools or respond when done."
            ),
        }
    )
    async for outcome, events in _llm_call_and_process(
        agent, messages, session_id, step,
        state, logger, model_hint="acting",
        plan=plan, plan_step_idx=plan_step_idx,
        plan_iteration=plan_iteration, paused_phase="act",
    ):
        if outcome == "paused":
            return False, True, True, events
        if outcome == "tool_calls":
            return False, True, False, events
        if outcome == "content":
            return True, False, False, events
        # "error" or "empty"
        return False, False, False, events

    # Should not be reached, but satisfy type checker
    return False, False, False, []


async def _run_reflection_cycle(
    agent: Agent,
    messages: list[dict[str, Any]],
    prompt: str,
    session_id: str,
    step: int,
    state: dict[str, Any],
    logger: LoggerProtocol,
    plan: list[str] | None,
    plan_step_idx: int | None,
    plan_iteration: int | None,
    max_reflections: int,
) -> tuple[bool, bool, list[StreamEvent]]:
    """Execute reflection with optional tool calls.

    Passes ``"reflecting"`` as the model hint so that an LLMRouter
    can route reflection calls to a strong reasoning model.
    Delegates to :func:`_llm_call_and_process` for each LLM call.

    Returns:
        Tuple of (used_tools, paused, events).
    """
    all_events: list[StreamEvent] = []
    used_tools = False
    for _ in range(max_reflections):
        messages.append(
            {"role": MessageRole.USER.value, "content": prompt}
        )
        async for outcome, events in _llm_call_and_process(
            agent, messages, session_id, step,
            state, logger, model_hint="reflecting",
            plan=plan, plan_step_idx=plan_step_idx,
            plan_iteration=plan_iteration, paused_phase="reflect",
        ):
            all_events.extend(events)

            if outcome == "paused":
                return True, True, all_events
            if outcome == "tool_calls":
                used_tools = True
                continue
            if outcome == "content":
                return used_tools, False, all_events
            # "error" or "empty" → continue to next reflection iteration

    return used_tools, False, all_events
