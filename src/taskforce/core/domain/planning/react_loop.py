"""Core ReAct loop and LLM call processing for planning strategies."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from typing import TYPE_CHECKING, Any

from taskforce.core.domain.enums import (
    EventType,
    ExecutionStatus,
    LLMStreamEventType,
    MessageRole,
)
from taskforce.core.domain.models import ExecutionResult, StreamEvent, TokenUsage
from taskforce.core.domain.planning.interrupt import _handle_interrupt, is_interrupt_requested
from taskforce.core.domain.planning.llm_interactions import _salvage_answer
from taskforce.core.domain.planning.tool_execution import _process_tool_calls
from taskforce.core.domain.planning.utils import (
    _build_retry_nudge,
    _ensure_event_type,
    _is_no_progress_tool_output,
)
from taskforce.core.interfaces.logging import LoggerProtocol

if TYPE_CHECKING:
    from taskforce.core.domain.agent import Agent


async def _collect_result(session_id: str, events: AsyncIterator[StreamEvent]) -> ExecutionResult:
    """Collect events into ExecutionResult."""
    history: list[dict[str, Any]] = []
    final_msg, error = "", ""
    pending: dict[str, Any] | None = None
    interrupted = False
    usage = TokenUsage()
    track = {
        EventType.TOOL_CALL,
        EventType.TOOL_RESULT,
        EventType.ASK_USER,
        EventType.PLAN_UPDATED,
        EventType.FINAL_ANSWER,
        EventType.ERROR,
        EventType.INTERRUPTED,
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
        elif event_type == EventType.INTERRUPTED:
            interrupted = True
            final_msg = final_msg or "Execution paused by user."
        elif event_type == EventType.ERROR:
            error = e.data.get("message", "")
        elif event_type == EventType.TOKEN_USAGE:
            usage.prompt_tokens += e.data.get("prompt_tokens", 0)
            usage.completion_tokens += e.data.get("completion_tokens", 0)
            usage.total_tokens += e.data.get("total_tokens", 0)

    if pending or interrupted:
        status = ExecutionStatus.PAUSED
    elif error or not final_msg:
        status = ExecutionStatus.FAILED
    else:
        status = ExecutionStatus.COMPLETED

    # Build a user-facing message: prefer final answer, then wrap error,
    # then provide a generic fallback.  Never send raw error strings or
    # empty messages to users.
    if final_msg:
        message = final_msg
    elif error:
        message = (
            f"Ich konnte die Aufgabe leider nicht abschließen: {error}\n"
            "Bitte versuche es noch einmal oder formuliere die Anfrage anders."
        )
    else:
        message = "Ich konnte leider keine Antwort generieren. " "Bitte versuche es noch einmal."

    return ExecutionResult(
        session_id=session_id,
        status=status,
        final_message=message,
        execution_history=history,
        pending_question=pending,
        token_usage=usage,
    )


async def _react_loop(
    agent: Agent,
    mission: str,
    session_id: str,
    messages: list[dict[str, Any]],
    state: dict[str, Any],
    start_step: int,
    logger: LoggerProtocol,
    model_hint: str = "reasoning",
) -> AsyncIterator[StreamEvent]:
    """Shared ReAct loop used by NativeReActStrategy.

    Runs the Thought-Action-Observation cycle up to ``agent.max_steps``,
    yielding ``StreamEvent`` objects.  Supports both streaming
    (``complete_stream``) and non-streaming (``complete``) LLM providers.

    Args:
        agent: The agent instance.
        mission: The mission string.
        session_id: Current session identifier.
        messages: Mutable message list (modified in-place).
        state: Mutable state dict.
        start_step: Step counter to start from.
        logger: Logger instance.
        model_hint: Model hint string for LLMRouter routing.
    """
    use_stream = hasattr(agent.llm_provider, "complete_stream")
    step = start_step
    final = ""
    consecutive_no_progress_steps = 0
    last_tool_signature: str | None = None
    repeated_signature_count = 0
    tool_failure_counts: dict[str, int] = {}  # per-tool circuit breaker
    consecutive_llm_errors = 0  # abort after N hard LLM failures in a row
    _MAX_CONSECUTIVE_LLM_ERRORS = 3

    while step < agent.max_steps:
        # Yield to the event loop once per iteration so that signal handlers
        # (SIGINT/SIGBREAK) and other async tasks always get a chance to run,
        # even if every branch below errors out synchronously before any await.
        await asyncio.sleep(0)

        # Cooperative interrupt: if a Ctrl+C (CLI) or POST /cancel (API)
        # has requested a pause, persist state and return.  The existing
        # _resume_from_pause path picks execution back up on the next turn.
        if is_interrupt_requested(agent):
            async for evt in _handle_interrupt(
                agent,
                session_id,
                state,
                logger,
                step=step,
                paused_phase="react",
            ):
                yield evt
            return

        await agent.record_heartbeat(session_id, ExecutionStatus.PENDING.value, {"step": step})

        # Inject circuit breaker info for tools that have failed too many times
        broken_tools = [name for name, count in tool_failure_counts.items() if count >= 3]
        if broken_tools:
            agent.context.append_message(
                {
                    "role": MessageRole.USER.value,
                    "content": (
                        "[System: The following tools are currently unavailable due to "
                        f"repeated failures: {', '.join(broken_tools)}. Do NOT call "
                        "these tools. Use alternative tools or provide your best "
                        "answer without them.]"
                    ),
                }
            )

        await agent.context.prepare_for_llm(mission=mission, state=state)

        tool_calls: list[dict[str, Any]] = []
        content = ""

        if use_stream:
            tc_acc: dict[int, dict[str, str]] = {}
            content_acc = ""
            stream_error_msg: str | None = None
            try:
                async for chunk in agent.llm_provider.complete_stream(
                    messages=messages,
                    model=model_hint,
                    tools=agent._openai_tools,
                    tool_choice="auto",
                    temperature=0.2,
                    metadata={"step_number": step, "phase": model_hint},
                ):
                    t = chunk.get("type")
                    if t == LLMStreamEventType.TOKEN.value and chunk.get("content"):
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
                        tc_acc[chunk["index"]]["arguments"] += chunk.get("arguments_delta", "")
                    elif (
                        t == LLMStreamEventType.TOOL_CALL_END.value
                        and chunk.get("index", 0) in tc_acc
                    ):
                        tc_acc[chunk["index"]]["arguments"] = chunk.get(
                            "arguments",
                            tc_acc[chunk["index"]]["arguments"],
                        )
                    elif t == LLMStreamEventType.DONE.value and chunk.get("usage"):
                        yield StreamEvent(
                            event_type=EventType.TOKEN_USAGE,
                            data=chunk["usage"],
                        )
                    elif t == "error":
                        # The LLM provider yields errors as chunks (not
                        # raises) — capture so the consecutive-error
                        # counter below sees them, otherwise a
                        # deterministic API rejection (e.g. malformed
                        # tool-call history) loops to max_steps wasting
                        # tokens and time.
                        stream_error_msg = str(chunk.get("message", "Error"))
                        yield StreamEvent(
                            event_type=EventType.ERROR,
                            data={"message": stream_error_msg},
                        )
            except Exception as e:
                consecutive_llm_errors += 1
                logger.error(
                    "react_loop.llm_stream_failed",
                    error=str(e),
                    consecutive_errors=consecutive_llm_errors,
                    step=step,
                    session_id=session_id,
                )
                yield StreamEvent(
                    event_type=EventType.ERROR,
                    data={"message": str(e)},
                )
                step += 1
                if consecutive_llm_errors >= _MAX_CONSECUTIVE_LLM_ERRORS:
                    yield StreamEvent(
                        event_type=EventType.ERROR,
                        data={
                            "message": (
                                f"LLM call failed {consecutive_llm_errors} times "
                                f"in a row (last error: {e}). Aborting to avoid "
                                "an infinite retry loop."
                            )
                        },
                    )
                    return
                continue

            # If the stream yielded an in-band error chunk (no exception
            # raised but the LLM call effectively failed), treat it as a
            # consecutive failure too.
            if stream_error_msg is not None and not tc_acc and not content_acc:
                consecutive_llm_errors += 1
                logger.error(
                    "react_loop.llm_stream_error_chunk",
                    error=stream_error_msg,
                    consecutive_errors=consecutive_llm_errors,
                    step=step,
                    session_id=session_id,
                )
                step += 1
                if consecutive_llm_errors >= _MAX_CONSECUTIVE_LLM_ERRORS:
                    yield StreamEvent(
                        event_type=EventType.ERROR,
                        data={
                            "message": (
                                f"LLM call failed {consecutive_llm_errors} "
                                f"times in a row (last error: "
                                f"{stream_error_msg}). Aborting to avoid "
                                "an infinite retry loop."
                            )
                        },
                    )
                    return
                continue

            # Reset the counter only after a fully successful stream consumption.
            consecutive_llm_errors = 0

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
                model=model_hint,
                tools=agent._openai_tools,
                tool_choice="auto",
                temperature=0.2,
                metadata={"step_number": step, "phase": model_hint},
            )
            if result.get("usage"):
                yield StreamEvent(
                    event_type=EventType.TOKEN_USAGE,
                    data=result["usage"],
                )
            if not result.get("success"):
                consecutive_llm_errors += 1
                err = result.get("error")
                logger.error(
                    "react_loop.llm_complete_failed",
                    error=err,
                    consecutive_errors=consecutive_llm_errors,
                    step=step,
                    session_id=session_id,
                )
                agent.context.append_message(
                    {
                        "role": MessageRole.USER.value,
                        "content": (f"[System Error: {err}. " "Try again.]"),
                    }
                )
                step += 1
                if consecutive_llm_errors >= _MAX_CONSECUTIVE_LLM_ERRORS:
                    yield StreamEvent(
                        event_type=EventType.ERROR,
                        data={
                            "message": (
                                f"LLM call failed {consecutive_llm_errors} times "
                                f"in a row (last error: {err}). Aborting to avoid "
                                "an infinite retry loop."
                            )
                        },
                    )
                    return
                continue
            consecutive_llm_errors = 0
            tool_calls = result.get("tool_calls") or []
            content = result.get("content", "")

        if tool_calls:
            paused = False
            tool_result_events = 0
            no_progress_tool_results = 0
            failed_tool_names: list[str] = []
            tool_signature = "|".join(
                f"{tc.get('function', {}).get('name', '')}:{tc.get('function', {}).get('arguments', '')}"
                for tc in tool_calls
            )
            async for evt in _process_tool_calls(
                agent,
                tool_calls,
                session_id,
                step + 1,
                state,
                messages,
                logger,
            ):
                event_type = _ensure_event_type(evt)
                if event_type == EventType.ASK_USER:
                    paused = True
                elif event_type == EventType.TOOL_RESULT:
                    tool_result_events += 1
                    tool_name = str(evt.data.get("tool", "unknown"))
                    output = str(evt.data.get("output", ""))
                    if not evt.data.get("success", False):
                        no_progress_tool_results += 1
                        failed_tool_names.append(tool_name)
                        tool_failure_counts[tool_name] = tool_failure_counts.get(tool_name, 0) + 1
                    else:
                        tool_failure_counts[tool_name] = 0  # reset on success
                        if _is_no_progress_tool_output(output):
                            no_progress_tool_results += 1
                yield evt
            if paused:
                return

            if tool_result_events > 0 and no_progress_tool_results == tool_result_events:
                consecutive_no_progress_steps += 1
            else:
                consecutive_no_progress_steps = 0

            if tool_signature and tool_signature == last_tool_signature:
                repeated_signature_count += 1
            else:
                repeated_signature_count = 0
            last_tool_signature = tool_signature or None

            if consecutive_no_progress_steps >= 2 or repeated_signature_count >= 3:
                logger.warning(
                    "react_loop_stalled",
                    consecutive_no_progress_steps=consecutive_no_progress_steps,
                    repeated_signature_count=repeated_signature_count,
                    session_id=session_id,
                )
                # Salvage: force a final answer from the LLM with available context
                salvage = await _salvage_answer(agent, messages, logger)
                if salvage:
                    agent.context.append_message(
                        {"role": MessageRole.ASSISTANT.value, "content": salvage},
                    )
                    yield StreamEvent(
                        event_type=EventType.FINAL_ANSWER,
                        data={"content": salvage},
                    )
                else:
                    yield StreamEvent(
                        event_type=EventType.ERROR,
                        data={
                            "message": (
                                "Execution stalled due to repeated no-progress tool calls. "
                                "Please refine scope, path, or constraints and retry."
                            )
                        },
                    )
                return

            # Nudge the LLM to retry with alternative tools after failures
            if failed_tool_names:
                agent.context.append_message(
                    _build_retry_nudge(
                        failed_tool_names,
                        attempt=consecutive_no_progress_steps,
                    )
                )

            step += 1
        elif content:
            step += 1
            final = content
            agent.context.append_message(
                {"role": MessageRole.ASSISTANT.value, "content": content},
            )
            yield StreamEvent(
                event_type=EventType.FINAL_ANSWER,
                data={"content": content},
            )
            break
        else:
            # Empty response: LLM succeeded but produced neither tool calls
            # nor text. Nudge it and count the attempt so max_steps applies.
            agent.context.append_message(
                {
                    "role": MessageRole.USER.value,
                    "content": ("[System: Empty response. " "Provide answer or use tool.]"),
                }
            )
            step += 1

    if step >= agent.max_steps and not final:
        # Salvage: force a final answer before giving up
        salvage = await _salvage_answer(agent, messages, logger)
        if salvage:
            agent.context.append_message(
                {"role": MessageRole.ASSISTANT.value, "content": salvage},
            )
            yield StreamEvent(
                event_type=EventType.FINAL_ANSWER,
                data={"content": salvage},
            )
        else:
            yield StreamEvent(
                event_type=EventType.ERROR,
                data={"message": f"Exceeded max steps ({agent.max_steps})"},
            )


async def _llm_call_and_process(
    agent: Agent,
    messages: list[dict[str, Any]],
    session_id: str,
    step: int,
    state: dict[str, Any],
    logger: LoggerProtocol,
    model_hint: str = "acting",
    plan: list[str] | None = None,
    plan_step_idx: int | None = None,
    plan_iteration: int | None = None,
    paused_phase: str | None = None,
    tool_failure_counts: dict[str, int] | None = None,
) -> AsyncIterator[tuple[str, list[StreamEvent]]]:
    """Single non-streaming LLM call with tool processing.

    Yields exactly one ``(outcome, events)`` tuple where *outcome* is one
    of ``"tool_calls"``, ``"content"``, ``"empty"``, ``"error"``, or
    ``"paused"``.

    This consolidates the repeated pattern shared by
    PlanAndExecuteStrategy and SparStrategy's action phase.

    Args:
        tool_failure_counts: Optional shared per-tool failure counter for
            circuit breaker logic.  When a tool has failed >= 3 times a
            system message is injected telling the LLM to avoid it.
    """
    if tool_failure_counts is None:
        tool_failure_counts = {}

    # Inject circuit breaker info for tools that have failed too many times
    broken_tools = [name for name, count in tool_failure_counts.items() if count >= 3]
    if broken_tools:
        agent.context.append_message(
            {
                "role": MessageRole.USER.value,
                "content": (
                    "[System: The following tools are currently unavailable due to "
                    f"repeated failures: {', '.join(broken_tools)}. Do NOT call "
                    "these tools. Use alternative tools or provide your best "
                    "answer without them.]"
                ),
            }
        )

    events: list[StreamEvent] = []
    result = await agent.llm_provider.complete(
        messages=messages,
        model=model_hint,
        tools=agent._openai_tools,
        tool_choice="auto",
        temperature=0.2,
        metadata={"step_number": step, "phase": model_hint},
    )
    if result.get("usage"):
        events.append(StreamEvent(event_type=EventType.TOKEN_USAGE, data=result["usage"]))

    if not result.get("success"):
        agent.context.append_message(
            {
                "role": MessageRole.USER.value,
                "content": f"[Error: {result.get('error')}. Try again.]",
            }
        )
        yield ("error", events)
        return

    if result.get("tool_calls"):
        paused = False
        failed_tool_names: list[str] = []
        async for e in _process_tool_calls(
            agent,
            result["tool_calls"],
            session_id,
            step,
            state,
            messages,
            logger,
            plan=plan,
            plan_step_idx=plan_step_idx,
            plan_iteration=plan_iteration,
            paused_phase=paused_phase,
        ):
            event_type = _ensure_event_type(e)
            if event_type == EventType.ASK_USER:
                paused = True
            elif event_type == EventType.TOOL_RESULT:
                tool_name = str(e.data.get("tool", "unknown"))
                if not e.data.get("success", False):
                    failed_tool_names.append(tool_name)
                    tool_failure_counts[tool_name] = tool_failure_counts.get(tool_name, 0) + 1
                else:
                    tool_failure_counts[tool_name] = 0  # reset on success
            events.append(e)
        if not paused and failed_tool_names:
            agent.context.append_message(_build_retry_nudge(failed_tool_names))
        yield ("paused" if paused else "tool_calls", events)
        return

    if result.get("content"):
        agent.context.append_message(
            {"role": MessageRole.ASSISTANT.value, "content": result["content"]},
        )
        yield ("content", events)
        return

    agent.context.append_message(
        {
            "role": MessageRole.USER.value,
            "content": "[Empty response. Provide answer or use tool.]",
        }
    )
    yield ("empty", events)
