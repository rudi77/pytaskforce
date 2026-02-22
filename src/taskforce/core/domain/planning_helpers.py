"""Shared helpers for planning strategies.

Extracted from ``planning_strategy.py`` to reduce module size and
improve maintainability.  All helpers are internal (prefixed with ``_``)
and consumed only by the strategy implementations.

Key helpers:

* :func:`_ensure_event_type` — coerce ``str | EventType`` to ``EventType``
* :func:`_resume_from_pause` — restore state after an ``ask_user`` pause
* :func:`_stream_final_response` — stream or non-stream final answer
* :func:`_process_tool_calls` — execute tools, emit events, update messages
* :func:`_execute_tool_calls` — run tool calls with optional parallelism
* :func:`_collect_result` — collect stream events into ``ExecutionResult``
* :func:`_parse_plan_steps` — parse LLM plan output into step list
* :func:`_generate_plan` — generate plan via LLM call
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from taskforce.core.domain.enums import (
    EventType,
    ExecutionStatus,
    LLMStreamEventType,
    MessageRole,
)
from taskforce.core.domain.models import ExecutionResult, StreamEvent, TokenUsage
from taskforce.core.interfaces.logging import LoggerProtocol
from taskforce.core.tools.tool_converter import assistant_tool_calls_to_message

if TYPE_CHECKING:
    from taskforce.core.domain.agent import Agent


@dataclass(frozen=True)
class ToolCallRequest:
    """Parsed tool call request."""

    tool_call_id: str
    tool_name: str
    tool_args: dict[str, Any]


@dataclass
class ResumeContext:
    """State restored when resuming from an ``ask_user`` pause."""

    messages: list[dict[str, Any]]
    step: int
    plan: list[str]
    plan_step_idx: int
    plan_iteration: int
    phase: str


class ToolCallStatus:
    """Status constants for tool call events."""

    EXECUTING = "executing"
    COMPLETED = "completed"
    FAILED = "failed"


DEFAULT_PLAN = [
    "Analyze the mission and identify required actions.",
    "Execute the required actions using available tools.",
    "Summarize the results and provide the final response.",
]


# ---------------------------------------------------------------------------
# Pure helpers
# ---------------------------------------------------------------------------


def _ensure_event_type(event: StreamEvent) -> EventType:
    """Coerce ``event.event_type`` to ``EventType`` enum.

    Some code paths store event types as plain strings for backwards
    compatibility.  This helper normalises them so callers can compare
    via ``==`` against enum members.
    """
    et = event.event_type
    return et if isinstance(et, EventType) else EventType(et)


def _parse_tool_args(
    tool_call: dict[str, Any], logger: LoggerProtocol
) -> dict[str, Any]:
    """Parse tool call arguments from JSON string."""
    try:
        return json.loads(tool_call["function"]["arguments"])
    except json.JSONDecodeError:
        logger.warning("tool_args_parse_failed", tool=tool_call["function"]["name"])
        return {}


def _extract_tool_output(result: dict[str, Any]) -> str:
    """Extract display-friendly output from a tool result dict."""
    if "output" in result:
        out = result["output"]
        return out if isinstance(out, str) else json.dumps(out, default=str)
    return result.get("error", "") or json.dumps(result, default=str)


def _parse_plan_steps(content: str, logger: LoggerProtocol) -> list[str]:
    """Parse plan steps from LLM response."""
    text = content.strip()
    if not text:
        return []

    # Extract JSON from code blocks
    json_text = text
    if "```" in text:
        parts = text.split("```")
        if len(parts) >= 2:
            json_text = parts[1].strip()
            if "\n" in json_text and not json_text.split("\n")[0].startswith("["):
                json_text = json_text.split("\n", 1)[1].strip()

    try:
        data = json.loads(json_text)
        if isinstance(data, list):
            return [str(x).strip() for x in data if str(x).strip()]
    except (json.JSONDecodeError, TypeError):
        logger.debug("json_parse_failed")

    # Fallback: line-based
    steps = []
    for line in text.splitlines():
        c = line.strip().lstrip("-").strip()
        if c and not c.startswith("```"):
            if c[0].isdigit() and "." in c:
                c = c.split(".", 1)[1].strip()
            if c:
                steps.append(c)
    return steps


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
            "content": json.dumps({"success": True, "output": user_answer}),
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

    logger.info(
        "resumed_from_ask_user", session_id=session_id, user_answer=user_answer[:100]
    )

    return ResumeContext(
        messages=messages,
        step=step,
        plan=plan,
        plan_step_idx=plan_step_idx,
        plan_iteration=plan_iteration,
        phase=phase,
    )


# ---------------------------------------------------------------------------
# Async helpers
# ---------------------------------------------------------------------------


async def _generate_plan(
    agent: Agent, mission: str, logger: LoggerProtocol
) -> list[str]:
    """Generate plan steps via LLM.

    Passes ``"planning"`` as the model hint so that an LLMRouter (if active)
    can route this call to a model suited for task decomposition.
    """
    result = await agent.llm_provider.complete(
        messages=[
            {"role": MessageRole.SYSTEM.value, "content": agent.system_prompt},
            {
                "role": MessageRole.USER.value,
                "content": (
                    f"{mission}\n\nCreate a concise step-by-step plan. "
                    "Return ONLY a JSON array."
                ),
            },
        ],
        model="planning",
        tools=None,
        tool_choice="none",
        temperature=0.1,
    )
    if not result.get("success"):
        return []
    return _parse_plan_steps(result.get("content", ""), logger)


async def _execute_tool_calls(
    agent: Agent,
    requests: list[ToolCallRequest],
    session_id: str | None = None,
) -> list[tuple[ToolCallRequest, dict[str, Any]]]:
    """Execute tools with optional parallelism."""
    if not requests:
        return []

    max_p = max(1, agent.max_parallel_tools)
    sem = asyncio.Semaphore(max_p)
    results: dict[str, dict[str, Any]] = {}
    tasks: list[tuple[ToolCallRequest, asyncio.Task[dict[str, Any]]]] = []

    async def run(name: str, args: dict[str, Any]) -> dict[str, Any]:
        async with sem:
            return await agent._execute_tool(name, args, session_id=session_id)

    for req in requests:
        tool = agent.tools.get(req.tool_name)
        can_parallel = (
            tool
            and getattr(tool, "supports_parallelism", False)
            and not tool.requires_approval
        )
        if can_parallel and max_p > 1:
            tasks.append(
                (req, asyncio.create_task(run(req.tool_name, req.tool_args)))
            )
        else:
            results[req.tool_call_id] = await agent._execute_tool(
                req.tool_name, req.tool_args, session_id=session_id
            )

    if tasks:
        gathered = await asyncio.gather(*(t for _, t in tasks))
        for (req, _), res in zip(tasks, gathered, strict=True):
            results[req.tool_call_id] = res

    return [(req, results[req.tool_call_id]) for req in requests]


async def _collect_result(
    session_id: str, events: AsyncIterator[StreamEvent]
) -> ExecutionResult:
    """Collect events into ExecutionResult."""
    history: list[dict[str, Any]] = []
    final_msg, error = "", ""
    pending: dict[str, Any] | None = None
    usage = TokenUsage()
    track = {
        EventType.TOOL_CALL,
        EventType.TOOL_RESULT,
        EventType.ASK_USER,
        EventType.PLAN_UPDATED,
        EventType.FINAL_ANSWER,
        EventType.ERROR,
    }

    async for e in events:
        event_type = _ensure_event_type(e)
        if event_type in track:
            history.append({"type": event_type.value, **e.data})
        if event_type == EventType.FINAL_ANSWER:
            final_msg = e.data.get("content", "")
        elif event_type == EventType.ASK_USER:
            pending = dict(e.data)
            final_msg = final_msg or e.data.get("question", "Waiting for input")
        elif event_type == EventType.ERROR:
            error = e.data.get("message", "")
        elif event_type == EventType.TOKEN_USAGE:
            usage.prompt_tokens += e.data.get("prompt_tokens", 0)
            usage.completion_tokens += e.data.get("completion_tokens", 0)
            usage.total_tokens += e.data.get("total_tokens", 0)

    if pending:
        status = ExecutionStatus.PAUSED
    elif error or not final_msg:
        status = ExecutionStatus.FAILED
    else:
        status = ExecutionStatus.COMPLETED

    return ExecutionResult(
        session_id=session_id,
        status=status,
        final_message=final_msg or error,
        execution_history=history,
        pending_question=pending,
        token_usage=usage,
    )


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

    final = ""
    if hasattr(agent.llm_provider, "complete_stream"):
        async for chunk in agent.llm_provider.complete_stream(
            messages=messages,
            model="summarizing",
            tools=None,
            tool_choice="none",
            temperature=0.2,
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
            elif chunk.get("type") == "usage":
                yield StreamEvent(
                    event_type=EventType.TOKEN_USAGE,
                    data=chunk.get("usage", {}),
                )
    else:
        r = await agent.llm_provider.complete(
            messages=messages,
            model="summarizing",
            tools=None,
            tool_choice="none",
            temperature=0.2,
        )
        final = r.get("content", "") if r.get("success") else ""

    if final:
        yield StreamEvent(
            event_type=EventType.FINAL_ANSWER, data={"content": final}
        )
    else:
        yield StreamEvent(
            event_type=EventType.FINAL_ANSWER,
            data={"content": "Plan completed."},
        )


async def _handle_ask_user(
    agent: Agent,
    args: dict[str, Any],
    session_id: str,
    state: dict[str, Any],
    logger: LoggerProtocol,
    messages: list[dict[str, Any]],
    tool_call_id: str,
    step: int,
    plan: list[str] | None = None,
    plan_step_idx: int | None = None,
    plan_iteration: int | None = None,
    paused_phase: str | None = None,
) -> AsyncIterator[StreamEvent]:
    """Handle ask_user tool and save state for resume."""
    q = str(args.get("question", "")).strip()
    missing = args.get("missing") or []
    state["pending_question"] = {"question": q, "missing": missing}
    state["paused_messages"] = messages
    state["paused_tool_call_id"] = tool_call_id
    state["paused_step"] = step
    if plan is not None:
        state["paused_plan"] = plan
    if plan_step_idx is not None:
        state["paused_plan_step_idx"] = plan_step_idx
    if plan_iteration is not None:
        state["paused_plan_iteration"] = plan_iteration
    if paused_phase is not None:
        state["paused_phase"] = paused_phase
    await agent.state_store.save(
        session_id=session_id, state=state, planner=agent.planner
    )
    yield StreamEvent(
        event_type=EventType.ASK_USER,
        data={"question": q, "missing": missing},
    )
    logger.info("paused_for_user_input", session_id=session_id)


async def _emit_tool_result(
    agent: Agent, req: ToolCallRequest, result: dict[str, Any]
) -> AsyncIterator[StreamEvent]:
    """Emit tool result event."""
    yield StreamEvent(
        event_type=EventType.TOOL_RESULT,
        data={
            "tool": req.tool_name,
            "id": req.tool_call_id,
            "success": result.get("success", False),
            "output": agent._truncate_output(_extract_tool_output(result)),
            "args": req.tool_args,
        },
    )
    if req.tool_name in ("planner", "manage_plan") and result.get("success"):
        plan = result.get("output") or (
            agent._planner.get_plan_summary() if agent._planner else None
        )
        if plan:
            yield StreamEvent(
                event_type=EventType.PLAN_UPDATED,
                data={
                    "action": req.tool_args.get("action", "unknown"),
                    "plan": plan,
                },
            )


async def _process_tool_calls(
    agent: Agent,
    tool_calls: list[dict[str, Any]],
    session_id: str,
    step: int,
    state: dict[str, Any],
    messages: list[dict[str, Any]],
    logger: LoggerProtocol,
    plan: list[str] | None = None,
    plan_step_idx: int | None = None,
    plan_iteration: int | None = None,
    paused_phase: str | None = None,
) -> AsyncIterator[StreamEvent]:
    """Process tool calls, yield events, update messages."""
    messages.append(assistant_tool_calls_to_message(tool_calls))
    requests = []

    for tc in tool_calls:
        name, tc_id = tc["function"]["name"], tc["id"]
        args = _parse_tool_args(tc, logger)
        yield StreamEvent(
            event_type=EventType.TOOL_CALL,
            data={
                "tool": name,
                "id": tc_id,
                "status": ToolCallStatus.EXECUTING,
                "args": args,
            },
        )

        if name == "ask_user":
            async for e in _handle_ask_user(
                agent,
                args,
                session_id,
                state,
                logger,
                messages=messages,
                tool_call_id=tc_id,
                step=step,
                plan=plan,
                plan_step_idx=plan_step_idx,
                plan_iteration=plan_iteration,
                paused_phase=paused_phase,
            ):
                yield e
            return

        requests.append(ToolCallRequest(tc_id, name, args))

    for req, res in await _execute_tool_calls(agent, requests, session_id):
        async for e in _emit_tool_result(agent, req, res):
            yield e
        messages.append(
            await agent.tool_result_message_factory.build_message(
                tool_call_id=req.tool_call_id,
                tool_name=req.tool_name,
                tool_result=res,
                session_id=session_id,
                step=step,
            )
        )
