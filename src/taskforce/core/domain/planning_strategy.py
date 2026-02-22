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
    LLMStreamEventType,
    MessageRole,
    PlannerAction,
)
from taskforce.core.domain.models import ExecutionResult, StreamEvent
from taskforce.core.domain.planning_helpers import (
    DEFAULT_PLAN,
    _collect_result,
    _ensure_event_type,
    _generate_plan,
    _process_tool_calls,
    _resume_from_pause,
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
        state = await agent.state_manager.load_state(session_id) or {}
        if agent._planner and state.get("planner_state"):
            agent._planner.set_state(state["planner_state"])

        resume = _resume_from_pause(state, mission, logger, session_id)
        if resume is not None:
            messages = resume.messages
            step = resume.step
        else:
            if self.generate_plan_first:
                steps = (
                    await _generate_plan(agent, mission, logger) or DEFAULT_PLAN
                )[: self.max_plan_steps]
                if agent._planner:
                    await agent._planner.execute(
                        action=PlannerAction.CREATE_PLAN.value, tasks=steps
                    )
                    yield StreamEvent(
                        event_type=EventType.PLAN_UPDATED,
                        data={
                            "action": PlannerAction.CREATE_PLAN.value,
                            "steps": steps,
                            "plan": agent._planner.get_plan_summary(),
                        },
                    )
                await agent.state_store.save(
                    session_id=session_id, state=state, planner=agent.planner
                )

            messages = agent._build_initial_messages(mission, state)
            step = 0

        use_stream = hasattr(agent.llm_provider, "complete_stream")
        final = ""

        while step < agent.max_steps:
            await agent.record_heartbeat(
                session_id, ExecutionStatus.PENDING.value, {"step": step}
            )
            messages[0] = {
                "role": MessageRole.SYSTEM.value,
                "content": agent._build_system_prompt(
                    mission=mission, state=state, messages=messages
                ),
            }

            if use_stream:
                messages = await agent.message_history_manager.compress_messages(
                    messages
                )
                messages = agent.message_history_manager.preflight_budget_check(
                    messages
                )

            tool_calls: list[dict[str, Any]] = []
            content = ""

            if use_stream:
                tc_acc: dict[int, dict[str, str]] = {}
                content_acc = ""
                try:
                    async for chunk in agent.llm_provider.complete_stream(
                        messages=messages,
                        model="reasoning",
                        tools=agent._openai_tools,
                        tool_choice="auto",
                        temperature=0.2,
                    ):
                        t = chunk.get("type")
                        if (
                            t == LLMStreamEventType.TOKEN.value
                            and chunk.get("content")
                        ):
                            yield StreamEvent(
                                event_type=EventType.LLM_TOKEN,
                                data={"content": chunk["content"]},
                            )
                            content_acc += chunk["content"]
                        elif t == LLMStreamEventType.TOOL_CALL_START.value:
                            tc_acc[chunk.get("index", 0)] = {
                                "id": chunk.get("id", ""),
                                "name": chunk.get("name", ""),
                                "arguments": "",
                            }
                        elif (
                            t == LLMStreamEventType.TOOL_CALL_DELTA.value
                            and chunk.get("index", 0) in tc_acc
                        ):
                            tc_acc[chunk["index"]]["arguments"] += chunk.get(
                                "arguments_delta", ""
                            )
                        elif (
                            t == LLMStreamEventType.TOOL_CALL_END.value
                            and chunk.get("index", 0) in tc_acc
                        ):
                            tc_acc[chunk["index"]]["arguments"] = chunk.get(
                                "arguments",
                                tc_acc[chunk["index"]]["arguments"],
                            )
                        elif (
                            t == LLMStreamEventType.DONE.value
                            and chunk.get("usage")
                        ):
                            yield StreamEvent(
                                event_type=EventType.TOKEN_USAGE,
                                data=chunk["usage"],
                            )
                        elif t == "error":
                            yield StreamEvent(
                                event_type=EventType.ERROR,
                                data={
                                    "message": chunk.get("message", "Error")
                                },
                            )
                except Exception as e:
                    yield StreamEvent(
                        event_type=EventType.ERROR,
                        data={"message": str(e)},
                    )
                    continue

                if tc_acc:
                    tool_calls = [
                        {
                            "id": v["id"],
                            "type": "function",
                            "function": {
                                "name": v["name"],
                                "arguments": v["arguments"],
                            },
                        }
                        for v in tc_acc.values()
                    ]
                else:
                    content = content_acc
            else:
                result = await agent.llm_provider.complete(
                    messages=messages,
                    model="reasoning",
                    tools=agent._openai_tools,
                    tool_choice="auto",
                    temperature=0.2,
                )
                if result.get("usage"):
                    yield StreamEvent(
                        event_type=EventType.TOKEN_USAGE,
                        data=result["usage"],
                    )
                if not result.get("success"):
                    messages.append(
                        {
                            "role": MessageRole.USER.value,
                            "content": (
                                f"[System Error: {result.get('error')}. "
                                "Try again.]"
                            ),
                        }
                    )
                    continue
                tool_calls = result.get("tool_calls") or []
                content = result.get("content", "")

            if tool_calls:
                paused = False
                async for e in _process_tool_calls(
                    agent, tool_calls, session_id, step + 1,
                    state, messages, logger,
                ):
                    event_type = _ensure_event_type(e)
                    if event_type == EventType.ASK_USER:
                        paused = True
                    yield e
                if paused:
                    return
                step += 1
            elif content:
                step += 1
                final = content
                yield StreamEvent(
                    event_type=EventType.FINAL_ANSWER,
                    data={"content": content},
                )
                break
            else:
                messages.append(
                    {
                        "role": MessageRole.USER.value,
                        "content": (
                            "[System: Empty response. "
                            "Provide answer or use tool.]"
                        ),
                    }
                )

        if step >= agent.max_steps and not final:
            yield StreamEvent(
                event_type=EventType.ERROR,
                data={
                    "message": f"Exceeded max steps ({agent.max_steps})"
                },
            )

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
        state = await agent.state_manager.load_state(session_id) or {}
        if agent._planner and state.get("planner_state"):
            agent._planner.set_state(state["planner_state"])

        resume = _resume_from_pause(state, mission, logger, session_id)
        if resume is not None:
            messages = resume.messages
            progress = resume.step
            plan = resume.plan
            start_idx = resume.plan_step_idx
            start_it = resume.plan_iteration
        else:
            messages = agent._build_initial_messages(mission, state)
            plan = (
                await _generate_plan(agent, mission, logger) or DEFAULT_PLAN
            )[: self.max_plan_steps]
            progress = 0
            start_idx = 1
            start_it = 1

            if agent._planner:
                await agent._planner.execute(
                    action=PlannerAction.CREATE_PLAN.value, tasks=plan
                )
                yield StreamEvent(
                    event_type=EventType.PLAN_UPDATED,
                    data={
                        "action": PlannerAction.CREATE_PLAN.value,
                        "steps": plan,
                        "plan": agent._planner.get_plan_summary(),
                    },
                )

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
                messages[0] = {
                    "role": MessageRole.SYSTEM.value,
                    "content": agent._build_system_prompt(
                        mission=mission, state=state, messages=messages
                    ),
                }
                messages.append(
                    {
                        "role": MessageRole.USER.value,
                        "content": (
                            f"Execute step {idx}: {desc}\n"
                            "Call tools or respond when done."
                        ),
                    }
                )

                result = await agent.llm_provider.complete(
                    messages=messages,
                    model="acting",
                    tools=agent._openai_tools,
                    tool_choice="auto",
                    temperature=0.2,
                )
                if result.get("usage"):
                    yield StreamEvent(
                        event_type=EventType.TOKEN_USAGE,
                        data=result["usage"],
                    )

                if not result.get("success"):
                    messages.append(
                        {
                            "role": MessageRole.USER.value,
                            "content": (
                                f"[Error: {result.get('error')}. Try again.]"
                            ),
                        }
                    )
                    continue

                if result.get("tool_calls"):
                    progress += 1
                    paused = False
                    async for e in _process_tool_calls(
                        agent, result["tool_calls"], session_id,
                        progress, state, messages, logger,
                        plan=plan, plan_step_idx=idx,
                        plan_iteration=it,
                    ):
                        event_type = _ensure_event_type(e)
                        if event_type == EventType.ASK_USER:
                            paused = True
                        yield e
                    if paused:
                        return
                elif result.get("content"):
                    messages.append(
                        {
                            "role": MessageRole.ASSISTANT.value,
                            "content": result["content"],
                        }
                    )
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
                else:
                    messages.append(
                        {
                            "role": MessageRole.USER.value,
                            "content": (
                                "[Empty response. "
                                "Provide answer or use tool.]"
                            ),
                        }
                    )

        if progress < agent.max_steps:
            async for e in _stream_final_response(agent, messages):
                yield e
        elif progress >= agent.max_steps:
            yield StreamEvent(
                event_type=EventType.ERROR,
                data={
                    "message": f"Exceeded max steps ({agent.max_steps})"
                },
            )

        await agent.state_store.save(
            session_id=session_id, state=state, planner=agent.planner
        )


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
        state = await agent.state_manager.load_state(session_id) or {}
        if agent._planner and state.get("planner_state"):
            agent._planner.set_state(state["planner_state"])

        resume = _resume_from_pause(state, mission, logger, session_id)
        if resume is not None:
            messages = resume.messages
            progress = resume.step
            plan = resume.plan
            start_idx = resume.plan_step_idx
            start_it = resume.plan_iteration
            start_phase = resume.phase
        else:
            messages = agent._build_initial_messages(mission, state)
            plan = (
                await _generate_plan(agent, mission, logger) or DEFAULT_PLAN
            )[: self.max_plan_steps]
            progress = 0
            start_idx = 1
            start_it = 1
            start_phase = "act"

            if agent._planner:
                await agent._planner.execute(
                    action=PlannerAction.CREATE_PLAN.value, tasks=plan
                )
                yield StreamEvent(
                    event_type=EventType.PLAN_UPDATED,
                    data={
                        "action": PlannerAction.CREATE_PLAN.value,
                        "steps": plan,
                        "plan": agent._planner.get_plan_summary(),
                    },
                )

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
                messages[0] = {
                    "role": MessageRole.SYSTEM.value,
                    "content": agent._build_system_prompt(
                        mission=mission, state=state, messages=messages
                    ),
                }

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
                        await _run_spar_reflection(
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
                await _run_spar_final_reflection(
                    agent=agent,
                    messages=messages,
                    session_id=session_id,
                    step=progress + 1,
                    state=state,
                    logger=logger,
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
        elif progress >= agent.max_steps:
            yield StreamEvent(
                event_type=EventType.ERROR,
                data={
                    "message": f"Exceeded max steps ({agent.max_steps})"
                },
            )

        await agent.state_store.save(
            session_id=session_id, state=state, planner=agent.planner
        )


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

    Returns:
        Tuple of (action_done, used_tools, paused, events).
    """
    events: list[StreamEvent] = []
    messages.append(
        {
            "role": MessageRole.USER.value,
            "content": (
                f"ACT: Execute step {plan_step_idx}: {desc}\n"
                "Call tools or respond when done."
            ),
        }
    )
    result = await agent.llm_provider.complete(
        messages=messages,
        model="acting",
        tools=agent._openai_tools,
        tool_choice="auto",
        temperature=0.2,
    )
    if result.get("usage"):
        events.append(
            StreamEvent(
                event_type=EventType.TOKEN_USAGE, data=result["usage"]
            )
        )

    if not result.get("success"):
        messages.append(
            {
                "role": MessageRole.USER.value,
                "content": f"[Error: {result.get('error')}. Try again.]",
            }
        )
        return False, False, False, events

    if result.get("tool_calls"):
        paused = False
        async for e in _process_tool_calls(
            agent, result["tool_calls"], session_id, step,
            state, messages, logger,
            plan=plan, plan_step_idx=plan_step_idx,
            plan_iteration=plan_iteration, paused_phase="act",
        ):
            event_type = _ensure_event_type(e)
            if event_type == EventType.ASK_USER:
                paused = True
            events.append(e)
        return False, True, paused, events

    if result.get("content"):
        messages.append(
            {"role": MessageRole.ASSISTANT.value, "content": result["content"]}
        )
        return True, False, False, events

    messages.append(
        {
            "role": MessageRole.USER.value,
            "content": "[Empty response. Provide answer or use tool.]",
        }
    )
    return False, False, False, events


async def _run_spar_reflection(
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
    max_reflections: int,
) -> tuple[bool, bool, list[StreamEvent]]:
    """Run the Reflect phase for a single plan step."""
    return await _run_reflection_cycle(
        agent=agent,
        messages=messages,
        prompt=(
            "REFLECT: Review the result of the last action step. "
            "Check correctness, edge cases, tests, and security. "
            "If more info is needed, ask_user. "
            "If validation tools should be used, call them."
        ),
        session_id=session_id,
        step=step,
        state=state,
        logger=logger,
        plan=plan,
        plan_step_idx=plan_step_idx,
        plan_iteration=plan_iteration,
        max_reflections=max_reflections,
    )


async def _run_spar_final_reflection(
    agent: Agent,
    messages: list[dict[str, Any]],
    session_id: str,
    step: int,
    state: dict[str, Any],
    logger: LoggerProtocol,
    max_reflections: int,
) -> tuple[bool, bool, list[StreamEvent]]:
    """Run a final reflection after all steps."""
    return await _run_reflection_cycle(
        agent=agent,
        messages=messages,
        prompt=(
            "REFLECT: Review the overall outcome for the mission. "
            "Verify quality, tests, and completeness. "
            "If anything is missing, ask_user or call tools to validate."
        ),
        session_id=session_id,
        step=step,
        state=state,
        logger=logger,
        plan=None,
        plan_step_idx=None,
        plan_iteration=None,
        max_reflections=max_reflections,
    )


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

    Returns:
        Tuple of (used_tools, paused, events).
    """
    events: list[StreamEvent] = []
    used_tools = False
    for _ in range(max_reflections):
        messages.append(
            {"role": MessageRole.USER.value, "content": prompt}
        )
        result = await agent.llm_provider.complete(
            messages=messages,
            model="reflecting",
            tools=agent._openai_tools,
            tool_choice="auto",
            temperature=0.2,
        )
        if result.get("usage"):
            events.append(
                StreamEvent(
                    event_type=EventType.TOKEN_USAGE,
                    data=result["usage"],
                )
            )

        if not result.get("success"):
            messages.append(
                {
                    "role": MessageRole.USER.value,
                    "content": (
                        f"[Error: {result.get('error')}. Try again.]"
                    ),
                }
            )
            continue

        if result.get("tool_calls"):
            used_tools = True
            paused = False
            async for e in _process_tool_calls(
                agent, result["tool_calls"], session_id, step,
                state, messages, logger,
                plan=plan, plan_step_idx=plan_step_idx,
                plan_iteration=plan_iteration,
                paused_phase="reflect",
            ):
                event_type = _ensure_event_type(e)
                if event_type == EventType.ASK_USER:
                    paused = True
                events.append(e)
            if paused:
                return used_tools, True, events
            continue

        if result.get("content"):
            messages.append(
                {
                    "role": MessageRole.ASSISTANT.value,
                    "content": result["content"],
                }
            )
            return used_tools, False, events

        messages.append(
            {
                "role": MessageRole.USER.value,
                "content": (
                    "[Empty response. Provide answer or use tool.]"
                ),
            }
        )

    return used_tools, False, events
