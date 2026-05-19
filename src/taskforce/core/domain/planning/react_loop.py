"""Core ReAct loop and LLM call processing for planning strategies."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from pathlib import Path
from typing import TYPE_CHECKING, Any

from taskforce.core.domain.enums import (
    EventType,
    ExecutionStatus,
    LLMStreamEventType,
    MessageRole,
)
from taskforce.core.domain.models import ExecutionResult, StreamEvent, TokenUsage
from taskforce.core.domain.planning.deliverable_check import (
    build_nudge as _build_deliverable_nudge,
    build_pivot_nudge as _build_pivot_nudge,
    extract_candidate_dirs as _extract_candidate_dirs,
    extract_deliverables as _extract_deliverables,
    find_missing as _find_missing_deliverables,
)
from taskforce.core.domain.planning.interrupt import _handle_interrupt, is_interrupt_requested
from taskforce.core.domain.planning.llm_interactions import _salvage_answer
from taskforce.core.domain.planning.tool_execution import _process_tool_calls
from taskforce.core.domain.planning.utils import (
    _build_pre_stall_nudge,
    _build_retry_nudge,
    _ensure_event_type,
    _is_no_progress_tool_output,
)
from taskforce.core.interfaces.logging import LoggerProtocol

if TYPE_CHECKING:
    from taskforce.core.domain.agent import Agent


def build_user_message_for_error(error_kind: str, raw_error: str) -> str:
    """Translate a structured agent failure into a user-facing message.

    The gateway's ``_sanitize_reply`` swaps any blank or status-string
    reply for a generic "something went wrong" line, which made
    content-filter aborts look identical to outages and gave the user no
    actionable hint. By branching on ``error_kind`` here we surface the
    real cause once and let the gateway pass the message through
    untouched.

    Args:
        error_kind: Structured failure category from the LLM stream
            (``"content_filter"``, ``"non_retryable"``, ``""`` ...).
        raw_error: Free-form error text, used for non-categorized failures.
    """
    if error_kind == "content_filter":
        return (
            "Der Inhaltsfilter des LLM-Anbieters hat den Prompt blockiert "
            "und auch alle Recovery-Versuche (History-Trimm, ohne Tools, "
            "Neutral-Rephrase) sind durchgekommen.\n\n"
            "Was meistens hilft, in dieser Reihenfolge:\n"
            "• **`/compact`** im Chat aufrufen — staucht die bisherige "
            "Conversation zu einer Zusammenfassung; danach läuft die "
            "nächste Anfrage in derselben Conversation, aber mit weniger "
            "Trigger-Material.\n"
            "• Neue Conversation für die Aufgabe starten, um den "
            "angesammelten Recherche-Kontext loszuwerden.\n"
            "• Wenn der Filter direkt am Anfang zuschlägt: liegt's am "
            "Inhalt deiner Daten (Kundendaten, Mails, PII), greift "
            "Azures Prompt-Shield. Filter in Azure AI Foundry unter "
            "*Deployment → Content filter* niedriger stellen oder ein "
            "Deployment ohne Shield verwenden."
        )
    if raw_error:
        return (
            f"Ich konnte die Aufgabe leider nicht abschließen: {raw_error}\n"
            "Bitte versuche es noch einmal oder formuliere die Anfrage anders."
        )
    return "Ich konnte leider keine Antwort generieren. Bitte versuche es noch einmal."


async def _collect_result(session_id: str, events: AsyncIterator[StreamEvent]) -> ExecutionResult:
    """Collect events into ExecutionResult."""
    history: list[dict[str, Any]] = []
    final_msg, error = "", ""
    error_kind = ""
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

    salvaged = False
    salvage_reason = ""

    async for e in events:
        event_type = _ensure_event_type(e)
        if event_type in track:
            history.append({"type": event_type.value, **e.data})
        if event_type == EventType.FINAL_ANSWER:
            final_msg = e.data.get("content", "")
            # Mission-level failure marker (#407). The salvage paths
            # (stall, max_steps, ignored-deliverable-nudge) wrap a final
            # answer to keep downstream consumers from crashing, but the
            # mission did not succeed — propagate that distinction.
            if e.data.get("salvaged"):
                salvaged = True
                salvage_reason = str(
                    e.data.get("salvage_reason") or salvage_reason or "salvaged"
                )
        elif event_type == EventType.ASK_USER:
            pending = dict(e.data)
            final_msg = final_msg or e.data.get("question", "Waiting for input")
        elif event_type == EventType.INTERRUPTED:
            interrupted = True
            final_msg = final_msg or "Execution paused by user."
        elif event_type == EventType.ERROR:
            error = e.data.get("message", "")
            kind = e.data.get("error_kind")
            if isinstance(kind, str) and kind:
                error_kind = kind
        elif event_type == EventType.TOKEN_USAGE:
            usage.prompt_tokens += e.data.get("prompt_tokens", 0)
            usage.completion_tokens += e.data.get("completion_tokens", 0)
            usage.total_tokens += e.data.get("total_tokens", 0)

    if pending or interrupted:
        status = ExecutionStatus.PAUSED
    elif error or not final_msg or salvaged:
        status = ExecutionStatus.FAILED
    else:
        status = ExecutionStatus.COMPLETED

    # Surface the salvage reason as an error string when no harder error
    # was captured. Lets dashboards / eval scorers distinguish a clean
    # mid-run abort from a generic FAILED.
    if salvaged and not error:
        error = f"salvaged: {salvage_reason}"

    # Build a user-facing message: prefer final answer, then a
    # category-specific message (content filter etc.), then the wrapped
    # error string, then a generic fallback. Never send raw error
    # strings or empty messages to users.
    if final_msg:
        message = final_msg
    else:
        message = build_user_message_for_error(error_kind, error)

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

    # Stall-detection thresholds — read from the agent (configurable per
    # profile) with class-level defaults as fallback. Workloads that
    # legitimately need many low-progress steps (browser DOM exploration,
    # multi-stage RAG) raise these in their config. Defensive isinstance
    # check is necessary because test fixtures often substitute a
    # MagicMock for ``agent``; ``int(MagicMock())`` silently returns 1
    # and would lock the loop into kill-on-first-failure.
    def _read_threshold(attr: str, default: int) -> int:
        value = getattr(agent, attr, None)
        return value if isinstance(value, int) and value > 0 else default

    no_progress_threshold = _read_threshold("react_no_progress_threshold", 2)
    signature_repeat_threshold = _read_threshold("react_signature_repeat_threshold", 3)
    # Track whether we've already injected the pre-stall escalation
    # nudge so we don't spam it every step.
    pre_stall_nudge_injected = False

    # Pre-finalize deliverable check (#405). Extract once, reuse each
    # step. Search roots: the workspace context (project root) plus any
    # backtick-quoted absolute dirs in the prompt (pinchbench per-mission
    # temp workspace). The check fires at most once per mission so the
    # loop still terminates if the LLM ignores the nudge.
    deliverables = _extract_deliverables(mission)
    deliverable_search_roots: list[Path] = []
    if deliverables:
        try:
            from taskforce.core.interfaces.workspace import get_workspace_context

            ws_ctx = get_workspace_context()
            if ws_ctx is not None:
                deliverable_search_roots.append(Path(ws_ctx.root()))
        except Exception:  # noqa: BLE001 — never break the loop over a workspace lookup
            pass
        deliverable_search_roots.extend(_extract_candidate_dirs(mission))
    # #408 / QW4: escalate the deliverable nudge up to N times instead
    # of the single-shot QW1 baseline. After ``_DELIVERABLE_MAX_NUDGES``
    # the loop still terminates (final answer flagged ``salvaged=True``
    # so the executor maps it to FAILED) — the goal is to give the LLM
    # multiple visible chances to break out of an analysis loop, not
    # to spin forever.
    deliverable_nudge_count = 0
    _DELIVERABLE_MAX_NUDGES = 3

    # #411 / QW7 (post-mortem-sharpened): mid-loop pivot nudge.
    #
    # Original heuristic was "write_tool_calls_seen == 0 at step>=30"
    # but it missed two cases:
    # 1. Agents that write via ``python`` with ``open(path, 'w')`` —
    #    the file exists but the counter doesn't increment.
    # 2. Research-heavy loops where the agent makes 30+ web_search /
    #    web_fetch calls inside a single ReAct step (parallel tools)
    #    so step count stays low while research bloats unchecked.
    #
    # Replaced with two combined signals:
    # * Disk-check via ``find_missing(...)`` — directly asks "is the
    #   declared deliverable on disk?", catches python-writes too.
    # * Research-call counter — categorises each tool, fires the
    #   pivot when research-style calls accumulate without a write.
    #
    # Tool categories are inlined (5 names) rather than carried as
    # a BaseTool property so this fix is fully contained — adding the
    # property to ~30 BaseTool subclasses is a separate refactor.
    _RESEARCH_TOOL_NAMES = frozenset({"web_search", "web_fetch", "browser"})
    _WRITE_TOOL_NAMES = frozenset({"file_write", "edit"})
    # Tools that should be IGNORED by both counters (overhead /
    # bookkeeping calls that don't reflect real work-without-write).
    _PIVOT_IGNORE_TOOL_NAMES = frozenset({"planner", "ask_user", "fetch_result"})

    research_calls_since_check = 0
    # Broader counter: any tool call that isn't a write or pure overhead.
    # Catches analysis-heavy meeting/log loops where the agent does
    # python/grep/file_read without producing the deliverable.
    nonwrite_calls_since_check = 0
    pivot_nudge_count = 0
    _PIVOT_RESEARCH_THRESHOLD = 8  # fire after 8 research calls w/o write
    _PIVOT_NONWRITE_THRESHOLD = 15  # also fire after 15 non-write calls (covers analysis)
    _PIVOT_STEP_FALLBACK = 25  # final fallback on step count
    _PIVOT_INTERVAL = 8  # subsequent checks every 8 calls
    _PIVOT_MAX = 3  # 3 escalating attempts before salvage

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

        # #411 / QW7 (sharpened): pivot-nudge — fire when the declared
        # deliverable is missing on disk AND the agent has either burned
        # a research budget (8 research calls between writes) or many
        # ReAct steps without writing. Disk-check via find_missing()
        # is the source of truth; the counters only decide WHEN to run
        # the check (avoids stat-ing the workspace every step).
        if deliverables and pivot_nudge_count < _PIVOT_MAX:
            offset = pivot_nudge_count * _PIVOT_INTERVAL
            research_trigger = research_calls_since_check >= (
                _PIVOT_RESEARCH_THRESHOLD + offset
            )
            nonwrite_trigger = nonwrite_calls_since_check >= (
                _PIVOT_NONWRITE_THRESHOLD + offset
            )
            step_trigger = step >= (_PIVOT_STEP_FALLBACK + offset)
            if research_trigger or nonwrite_trigger or step_trigger:
                if _find_missing_deliverables(
                    deliverables, deliverable_search_roots
                ):
                    pivot_nudge_count += 1
                    agent.context.append_message(
                        {
                            "role": MessageRole.USER.value,
                            "content": _build_pivot_nudge(
                                deliverables,
                                step,
                                attempt=pivot_nudge_count,
                                research_calls=research_calls_since_check
                                or nonwrite_calls_since_check,
                            ),
                        }
                    )
                    if research_trigger:
                        trigger = "research"
                    elif nonwrite_trigger:
                        trigger = "nonwrite"
                    else:
                        trigger = "step"
                    logger.info(
                        "react_loop.pivot_nudge_injected",
                        session_id=session_id,
                        step=step,
                        deliverables=deliverables,
                        nudge_count=pivot_nudge_count,
                        research_calls=research_calls_since_check,
                        nonwrite_calls=nonwrite_calls_since_check,
                        trigger=trigger,
                    )
                    # Reset counters so the next nudge fires only after
                    # another burst, not on the very next step.
                    research_calls_since_check = 0
                    nonwrite_calls_since_check = 0
                else:
                    # Deliverable exists — disable further pivot nudges
                    # for the rest of the mission.
                    pivot_nudge_count = _PIVOT_MAX

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
                    elif t == LLMStreamEventType.STREAM_RESTART.value:
                        # Content-filter (or other) recovery is about to
                        # re-stream. Drop anything accumulated from the
                        # aborted attempt so the final assistant message
                        # only carries clean retry output, and signal
                        # downstream consumers (UI) to do the same.
                        content_acc = ""
                        tc_acc = {}
                        yield StreamEvent(
                            event_type=EventType.LLM_STREAM_RESTART,
                            data={
                                "reason": chunk.get("reason", "unknown"),
                                "stage": chunk.get("stage", ""),
                            },
                        )
                    elif t == LLMStreamEventType.TOOL_CALL_START.value:
                        idx = chunk.get("index", 0)
                        existing = tc_acc.get(idx)
                        if existing is None:
                            tc_acc[idx] = {
                                "id": chunk.get("id", ""),
                                "name": chunk.get("name", ""),
                                "arguments": "",
                            }
                        else:
                            # A late ``tool_call_start`` (after we already
                            # lazy-initialised the entry from a delta — see
                            # below) may carry the previously-missing id /
                            # name. Don't blow away accumulated arguments.
                            if chunk.get("id"):
                                existing["id"] = chunk["id"]
                            if chunk.get("name"):
                                existing["name"] = chunk["name"]
                    elif t == LLMStreamEventType.TOOL_CALL_DELTA.value:
                        # Issue #155 — Telegram action gap: be tolerant of
                        # providers / wrappers that emit ``tool_call_delta``
                        # before any ``tool_call_start`` (or skip start
                        # entirely when id/name are still empty). Lazy-init
                        # the accumulator so later metadata or the
                        # ``tool_call_end`` event still wires up a real
                        # tool call.
                        idx = chunk.get("index", 0)
                        if idx not in tc_acc:
                            tc_acc[idx] = {
                                "id": chunk.get("id", "") or "",
                                "name": "",
                                "arguments": "",
                            }
                        elif chunk.get("id") and not tc_acc[idx]["id"]:
                            tc_acc[idx]["id"] = chunk["id"]
                        tc_acc[idx]["arguments"] += chunk.get("arguments_delta", "")
                    elif t == LLMStreamEventType.TOOL_CALL_END.value:
                        idx = chunk.get("index", 0)
                        if idx not in tc_acc:
                            # End without start — keep the call instead of
                            # dropping it (issue #155). Without this the
                            # agent would say "I will do X" in chat but
                            # the matching tool would never execute.
                            tc_acc[idx] = {
                                "id": chunk.get("id", "") or "",
                                "name": chunk.get("name", "") or "",
                                "arguments": "",
                            }
                        else:
                            if chunk.get("id") and not tc_acc[idx]["id"]:
                                tc_acc[idx]["id"] = chunk["id"]
                            if chunk.get("name") and not tc_acc[idx]["name"]:
                                tc_acc[idx]["name"] = chunk["name"]
                        tc_acc[idx]["arguments"] = chunk.get(
                            "arguments",
                            tc_acc[idx]["arguments"],
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
                        # Non-retryable provider rejections (e.g. Azure
                        # content filter) should abort the loop after the
                        # first failure rather than burning the full
                        # consecutive-error budget on the same blocked
                        # request.
                        if chunk.get("non_retryable"):
                            error_kind = chunk.get("error_kind") or "non_retryable"
                            yield StreamEvent(
                                event_type=EventType.ERROR,
                                data={
                                    "message": (
                                        f"LLM call rejected ({error_kind}): "
                                        f"{stream_error_msg}. Aborting to "
                                        "avoid retrying the same blocked request."
                                    ),
                                    "error_kind": error_kind,
                                    "non_retryable": True,
                                },
                            )
                            return
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
            failure_error_kinds: dict[str, str] = {}
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
                        kind = evt.data.get("error_kind")
                        if isinstance(kind, str):
                            failure_error_kinds[tool_name] = kind
                    else:
                        tool_failure_counts[tool_name] = 0  # reset on success
                        if _is_no_progress_tool_output(output):
                            no_progress_tool_results += 1
                        # Tool-category bookkeeping for the pivot-nudge
                        # (#411 / QW7 sharpened). Write-style tools
                        # reset the research counter; research-style
                        # tools accumulate it. The disk-check uses
                        # find_missing() as the source of truth — this
                        # counter only decides WHEN to run the check.
                        if tool_name in _WRITE_TOOL_NAMES:
                            research_calls_since_check = 0
                            nonwrite_calls_since_check = 0
                        else:
                            if tool_name in _RESEARCH_TOOL_NAMES:
                                research_calls_since_check += 1
                            if tool_name not in _PIVOT_IGNORE_TOOL_NAMES:
                                nonwrite_calls_since_check += 1
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

            # Pre-stall nudge: one step before we'd kill the loop,
            # inject a system message pointing the agent at its
            # escalation options. Gives the agent one last chance to
            # call browser(action=restart_headed) or otherwise pivot
            # before the salvage path kicks in.
            approaching_no_progress_kill = (
                consecutive_no_progress_steps == max(no_progress_threshold - 1, 1)
            )
            approaching_signature_kill = (
                repeated_signature_count == max(signature_repeat_threshold - 1, 1)
            )
            if (
                not pre_stall_nudge_injected
                and (approaching_no_progress_kill or approaching_signature_kill)
            ):
                pre_stall_nudge_injected = True
                has_browser_tool = "browser" in getattr(agent, "tools", {})
                agent.context.append_message(
                    _build_pre_stall_nudge(
                        has_browser_tool=has_browser_tool,
                        consecutive_no_progress_steps=consecutive_no_progress_steps,
                        repeated_signature_count=repeated_signature_count,
                    )
                )
                logger.info(
                    "react_loop_pre_stall_nudge",
                    consecutive_no_progress_steps=consecutive_no_progress_steps,
                    repeated_signature_count=repeated_signature_count,
                    has_browser_tool=has_browser_tool,
                    session_id=session_id,
                )

            if (
                consecutive_no_progress_steps >= no_progress_threshold
                or repeated_signature_count >= signature_repeat_threshold
            ):
                # Pre-salvage force-write: when the loop is about to give
                # up but the user requested a file we haven't written
                # yet, inject the strongest pivot nudge and let the loop
                # run ONE more step. Catches the apache-error-summary
                # case where the agent gathered all data in memory and
                # only needed file_write to finish — the stall detector
                # was killing it before the LLM produced a content reply
                # so QW1/QW4 finalize-nudges never fired.
                if (
                    deliverables
                    and pivot_nudge_count < _PIVOT_MAX
                    and _find_missing_deliverables(
                        deliverables, deliverable_search_roots
                    )
                ):
                    pivot_nudge_count = _PIVOT_MAX  # last chance — burn the budget
                    consecutive_no_progress_steps = 0
                    repeated_signature_count = 0
                    agent.context.append_message(
                        {
                            "role": MessageRole.USER.value,
                            "content": _build_pivot_nudge(
                                deliverables,
                                step,
                                attempt=3,  # force-write language
                                research_calls=research_calls_since_check,
                            ),
                        }
                    )
                    logger.info(
                        "react_loop.pre_salvage_force_write",
                        session_id=session_id,
                        step=step,
                        deliverables=deliverables,
                        consecutive_no_progress_steps=(
                            consecutive_no_progress_steps
                        ),
                    )
                    step += 1
                    continue
                logger.warning(
                    "react_loop_stalled",
                    consecutive_no_progress_steps=consecutive_no_progress_steps,
                    repeated_signature_count=repeated_signature_count,
                    no_progress_threshold=no_progress_threshold,
                    signature_repeat_threshold=signature_repeat_threshold,
                    session_id=session_id,
                )
                # Salvage: force a final answer from the LLM with available context
                salvage, content_filter_blocked = await _salvage_answer(
                    agent, messages, logger
                )
                if salvage:
                    agent.context.append_message(
                        {"role": MessageRole.ASSISTANT.value, "content": salvage},
                    )
                    yield StreamEvent(
                        event_type=EventType.FINAL_ANSWER,
                        data={
                            "content": salvage,
                            # #407: salvage path → mission-level failure even
                            # though we produced a user-facing reply.
                            "salvaged": True,
                            "salvage_reason": "stall",
                        },
                    )
                else:
                    error_data: dict[str, Any] = {
                        "message": (
                            "Execution stalled due to repeated no-progress tool calls. "
                            "Please refine scope, path, or constraints and retry."
                        )
                    }
                    if content_filter_blocked:
                        error_data["error_kind"] = "content_filter"
                    yield StreamEvent(
                        event_type=EventType.ERROR,
                        data=error_data,
                    )
                return

            # Nudge the LLM to retry with alternative tools after failures
            if failed_tool_names:
                agent.context.append_message(
                    _build_retry_nudge(
                        failed_tool_names,
                        attempt=consecutive_no_progress_steps,
                        error_kinds=failure_error_kinds,
                    )
                )

            step += 1
        elif content:
            step += 1
            # Pre-finalize deliverable check (#405 → #408). The user
            # named output files in the mission and at least one is
            # still missing on disk → escalate the nudge up to
            # ``_DELIVERABLE_MAX_NUDGES`` times instead of accepting
            # this as the final answer.
            if (
                deliverables
                and deliverable_nudge_count < _DELIVERABLE_MAX_NUDGES
            ):
                missing = _find_missing_deliverables(
                    deliverables, deliverable_search_roots
                )
                if missing:
                    deliverable_nudge_count += 1
                    agent.context.append_message(
                        {"role": MessageRole.ASSISTANT.value, "content": content},
                    )
                    agent.context.append_message(
                        {
                            "role": MessageRole.USER.value,
                            "content": _build_deliverable_nudge(
                                missing, attempt=deliverable_nudge_count
                            ),
                        },
                    )
                    logger.info(
                        "react_loop.deliverable_nudge_injected",
                        session_id=session_id,
                        step=step,
                        missing=missing,
                        attempt=deliverable_nudge_count,
                        max_nudges=_DELIVERABLE_MAX_NUDGES,
                    )
                    continue

            # #407 / #408: if we already nudged AND the deliverable is
            # STILL missing, accept the LLM's final answer but mark the
            # mission as salvaged so the executor reports a FAILED
            # status. The ``salvage_reason`` carries the nudge count so
            # analysis tooling can distinguish "ignored 1 nudge" from
            # "exhausted 3 nudges" — the latter is the hard-block path.
            answer_data: dict[str, Any] = {"content": content}
            if deliverable_nudge_count > 0 and deliverables:
                still_missing = _find_missing_deliverables(
                    deliverables, deliverable_search_roots
                )
                if still_missing:
                    answer_data["salvaged"] = True
                    exhausted = deliverable_nudge_count >= _DELIVERABLE_MAX_NUDGES
                    answer_data["salvage_reason"] = (
                        f"deliverable_missing_after_{deliverable_nudge_count}_nudges"
                        if exhausted
                        else "deliverable_missing"
                    )
                    answer_data["missing_deliverables"] = still_missing
                    log = logger.warning if exhausted else logger.info
                    log(
                        "react_loop.deliverable_still_missing_after_nudge",
                        session_id=session_id,
                        step=step,
                        missing=still_missing,
                        nudge_count=deliverable_nudge_count,
                        nudges_exhausted=exhausted,
                    )

            final = content
            agent.context.append_message(
                {"role": MessageRole.ASSISTANT.value, "content": content},
            )
            yield StreamEvent(
                event_type=EventType.FINAL_ANSWER,
                data=answer_data,
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
        salvage, content_filter_blocked = await _salvage_answer(agent, messages, logger)
        if salvage:
            agent.context.append_message(
                {"role": MessageRole.ASSISTANT.value, "content": salvage},
            )
            yield StreamEvent(
                event_type=EventType.FINAL_ANSWER,
                data={
                    "content": salvage,
                    # #407: max_steps salvage → mission-level failure.
                    "salvaged": True,
                    "salvage_reason": "max_steps",
                },
            )
        else:
            error_data: dict[str, Any] = {
                "message": f"Exceeded max steps ({agent.max_steps})"
            }
            if content_filter_blocked:
                error_data["error_kind"] = "content_filter"
            yield StreamEvent(
                event_type=EventType.ERROR,
                data=error_data,
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
        failure_error_kinds: dict[str, str] = {}
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
                    kind = e.data.get("error_kind")
                    if isinstance(kind, str):
                        failure_error_kinds[tool_name] = kind
                else:
                    tool_failure_counts[tool_name] = 0  # reset on success
            events.append(e)
        if not paused and failed_tool_names:
            agent.context.append_message(
                _build_retry_nudge(
                    failed_tool_names, error_kinds=failure_error_kinds
                )
            )
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
