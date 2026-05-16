"""Tool call processing functions for planning strategies."""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from taskforce.core.domain.enums import EventType, MessageRole
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


@dataclass
class _ToolCallBatchResults:
    """Per-tool results from a batch tool execution.

    Yielded as the *final* item of ``_stream_tool_calls_with_event_pump``
    after all sub-agent stream events have been emitted live.
    """

    tool_results: list[tuple[ToolCallRequest, dict[str, Any]]] = field(default_factory=list)


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
        snapshot = entry.pop("context_snapshot", None)
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


async def _stream_tool_calls_with_event_pump(
    agent: Agent,
    requests: list[ToolCallRequest],
    session_id: str | None,
    sub_event_sink: asyncio.Queue[StreamEvent] | None,
) -> AsyncIterator[StreamEvent | _ToolCallBatchResults]:
    """Execute tool calls, yielding sub-agent events live as they arrive.

    Yields ``StreamEvent`` instances forwarded by sub-agent tools (annotated
    with ``agent_path``) while the parent's tool tasks are running.  Once
    all tool tasks finish and the sink is drained, yields a final
    ``_ToolCallBatchResults`` carrying the per-tool result tuples.

    When ``sub_event_sink`` is ``None`` (nested call), no live pumping
    happens — sub-agent events flow up to the root sink — and only the
    final ``_ToolCallBatchResults`` is yielded.
    """
    if sub_event_sink is None:
        tool_results = await _execute_tool_calls(agent, requests, session_id)
        yield _ToolCallBatchResults(tool_results=tool_results)
        return

    tools_task: asyncio.Task[list[tuple[ToolCallRequest, dict[str, Any]]]] = asyncio.create_task(
        _execute_tool_calls(agent, requests, session_id)
    )

    # Race the tool task against the queue; emit events as they arrive.
    while True:
        sink_get: asyncio.Task[StreamEvent] = asyncio.create_task(sub_event_sink.get())
        done, _pending = await asyncio.wait(
            [tools_task, sink_get],
            return_when=asyncio.FIRST_COMPLETED,
        )
        if sink_get in done:
            yield sink_get.result()
        else:
            sink_get.cancel()
        if tools_task in done:
            break

    # Drain anything queued after the tool task signaled done.
    while not sub_event_sink.empty():
        try:
            yield sub_event_sink.get_nowait()
        except asyncio.QueueEmpty:
            break

    yield _ToolCallBatchResults(tool_results=tools_task.result())


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
    data: dict[str, Any] = {
        "tool": req.tool_name,
        "id": req.tool_call_id,
        "success": result.get("success", False),
        "output": agent._truncate_output(_extract_tool_output(result)),
        "args": req.tool_args,
    }
    # Propagate the structured failure classifier so the react loop /
    # downstream UI can distinguish "approval denied" from "tool
    # crashed" and pick the right user-facing message. Approval-denied
    # / approval-timeout failures are TERMINAL — the LLM must not be
    # nudged into retrying them.
    error_kind = result.get("error_kind")
    if error_kind:
        data["error_kind"] = error_kind
    if result.get("terminal_failure"):
        data["terminal_failure"] = True
    yield StreamEvent(
        event_type=EventType.TOOL_RESULT,
        data=data,
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

    for idx, tc in enumerate(tool_calls):
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
            # The OpenAI / Azure tool-call protocol requires every
            # ``assistant.tool_calls`` entry to be answered by a matching
            # ``tool`` message. We're about to pause for user input and
            # return early — any other tool_calls in this same batch
            # (already-queued in ``requests`` AND not-yet-seen at
            # ``tool_calls[idx+1:]``) would otherwise leave dangling
            # tool_call_ids in the conversation history. The next LLM
            # call would then crash with
            #   "An assistant message with 'tool_calls' must be followed
            #    by tool messages responding"
            # and retry forever (real Tina-pilot bug).
            #
            # Append a synthetic "skipped" tool result for each so the
            # contract is satisfied. The LLM can decide on resume
            # whether to re-issue them.
            skipped_ids: list[str] = [r.tool_call_id for r in requests] + [
                t["id"] for t in tool_calls[idx + 1 :]
            ]
            for sid in skipped_ids:
                agent.context.append_message(
                    {
                        "role": MessageRole.TOOL.value,
                        "tool_call_id": sid,
                        "content": json.dumps(
                            {
                                "skipped": True,
                                "reason": (
                                    "Skipped because ask_user paused execution; "
                                    "re-issue if still needed after the user replies."
                                ),
                            }
                        ),
                    }
                )
            if skipped_ids:
                logger.info(
                    "tool_calls.skipped_for_ask_user",
                    skipped_count=len(skipped_ids),
                    ask_user_id=tc_id,
                )

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

    # Set up an event sink so sub-agent tools can stream their inner
    # tool_call/tool_result events back to this stream while their tool
    # call is in flight.  The sink is owned by the *root* call only;
    # nested ``_process_tool_calls`` invocations inherit it but do not
    # pump it (the root pump drains everything).
    inherited_sink = getattr(agent, "_sub_agent_event_sink", None)
    owns_sink = inherited_sink is None
    if owns_sink:
        sub_event_sink: asyncio.Queue[StreamEvent] = asyncio.Queue()
        agent._sub_agent_event_sink = sub_event_sink
    else:
        sub_event_sink = inherited_sink

    try:
        batch_results: _ToolCallBatchResults | None = None
        async for item in _stream_tool_calls_with_event_pump(
            agent,
            requests,
            session_id,
            sub_event_sink if owns_sink else None,
        ):
            if isinstance(item, _ToolCallBatchResults):
                batch_results = item
            else:
                # Sub-agent StreamEvent forwarded live.
                yield item

        if batch_results is None:
            # Defensive: the pump always yields exactly one batch result as
            # its final item.  A None here means the contract was violated
            # (e.g. someone refactored the pump and forgot the final yield).
            raise RuntimeError("tool-call event pump did not yield a _ToolCallBatchResults")
        for req, res in batch_results.tool_results:
            async for e in _emit_tool_result(agent, req, res):
                yield e
            # Capture sub-agent context snapshots before they're lost to serialization
            _collect_sub_agent_snapshots(agent, res)
            # build_messages returns [tool_msg, *multimodal_followups] so
            # tools that produce images (multimedia, future audio/video)
            # reach vision-capable LLMs as proper image_url content blocks.
            for msg in await agent.tool_result_message_factory.build_messages(
                tool_call_id=req.tool_call_id,
                tool_name=req.tool_name,
                tool_result=res,
                session_id=session_id,
                step=step,
            ):
                agent.context.append_message(msg)
    finally:
        if owns_sink:
            agent._sub_agent_event_sink = None
