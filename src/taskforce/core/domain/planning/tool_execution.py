"""Tool call processing functions for planning strategies."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from typing import TYPE_CHECKING, Any

from taskforce.core.domain.enums import EventType
from taskforce.core.domain.models import StreamEvent
from taskforce.core.domain.planning.types import ToolCallRequest, ToolCallStatus
from taskforce.core.domain.planning.utils import (
    _extract_tool_output,
    _parse_tool_args,
    _persist_active_skill,
)
from taskforce.core.interfaces.logging import LoggerProtocol
from taskforce.core.tools.tool_converter import assistant_tool_calls_to_message

if TYPE_CHECKING:
    from taskforce.core.domain.agent import Agent


def _collect_sub_agent_snapshots(agent: Agent, tool_result: dict[str, Any]) -> None:
    """Extract and register sub-agent context snapshots from tool results.

    Orchestration tools (call_agents_parallel) attach ``_context_snapshot``
    to each sub-agent result entry.  This function collects them and
    registers them on the parent agent's ContextManager before the result
    is serialized (which would lose the snapshot objects).
    """
    results = tool_result.get("results")
    if not isinstance(results, list):
        return
    for entry in results:
        snapshot = entry.pop("_context_snapshot", None)
        if snapshot is None:
            continue
        agent.context.register_sub_agent_context(
            specialist=entry.get("specialist") or "unknown",
            session_id=entry.get("session_id") or "unknown",
            snapshot=snapshot,
        )


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
            tool and getattr(tool, "supports_parallelism", False) and not tool.requires_approval
        )
        if can_parallel and max_p > 1:
            tasks.append((req, asyncio.create_task(run(req.tool_name, req.tool_args))))
        else:
            results[req.tool_call_id] = await agent._execute_tool(
                req.tool_name, req.tool_args, session_id=session_id
            )

    if tasks:
        gathered = await asyncio.gather(*(t for _, t in tasks))
        for (req, _), res in zip(tasks, gathered, strict=True):
            results[req.tool_call_id] = res

    return [(req, results[req.tool_call_id]) for req in requests]


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
    """Handle ask_user tool and save state for resume.

    Supports two modes:

    * **Default** (no ``channel`` in args): Pauses execution and emits an
      ``ASK_USER`` event.  The frontend (CLI, Gateway) shows the question
      and feeds the answer back on the next turn.
    * **Channel-targeted** (``channel`` + ``recipient_id`` in args): The
      question is addressed to a specific person on a specific channel.
      The ``ASK_USER`` event includes channel routing data so the frontend
      can send the question to the right channel and poll for the response.
    """
    q = str(args.get("question", "")).strip()
    missing = args.get("missing") or []
    channel = args.get("channel")
    recipient_id = args.get("recipient_id")

    pending: dict[str, Any] = {"question": q, "missing": missing}
    if channel:
        pending["channel"] = channel
    if recipient_id:
        pending["recipient_id"] = recipient_id

    state["pending_question"] = pending
    state["paused_messages"] = list(agent.context.messages)
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
    _persist_active_skill(agent, state)
    await agent.state_store.save(session_id=session_id, state=state, planner=agent.planner)

    event_data: dict[str, Any] = {"question": q, "missing": missing}
    if channel:
        event_data["channel"] = channel
    if recipient_id:
        event_data["recipient_id"] = recipient_id

    yield StreamEvent(
        event_type=EventType.ASK_USER,
        data=event_data,
    )
    if channel:
        logger.info(
            "paused_for_channel_input",
            session_id=session_id,
            channel=channel,
            recipient_id=recipient_id,
        )
    else:
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
    agent.context.append_message(assistant_tool_calls_to_message(tool_calls))
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
        # Capture sub-agent context snapshots before they're lost to serialization
        _collect_sub_agent_snapshots(agent, res)
        agent.context.append_message(
            await agent.tool_result_message_factory.build_message(
                tool_call_id=req.tool_call_id,
                tool_name=req.tool_name,
                tool_result=res,
                session_id=session_id,
                step=step,
            )
        )
