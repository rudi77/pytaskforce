# ADR 019: Cooperative Agent Interruption

**Status:** Accepted
**Date:** 2026-04-19

## Context

Users had no way to pause a running agent.  In the CLI, Ctrl+C killed the
process and lost all intermediate state (messages, plan progress, step
counter).  The REST API had no cancel endpoint at all, so an in-flight
mission had to run to completion or timeout.

Two requirements drove this work:

1. **Pause & resume** — long missions that go the wrong direction (tool
   stuck, LLM looping, wrong plan) should be stoppable *without* losing
   the prior work; the user's next message continues the session.
2. **Uniform behaviour** across CLI (Ctrl+C) and REST (`POST
   /execute/{id}/cancel`).

## Decision

Implement a **cooperative interrupt flag** on the agent, checked at
well-defined loop boundaries, that re-uses the existing `ask_user`
pause/resume infrastructure.

- **`asyncio.Event`** on `LeanAgent` (`request_interrupt()`,
  `clear_interrupt()`, `is_interrupt_requested()`).
- **Check points** at the top of every ReAct/plan iteration: the current
  in-flight step (LLM call + tool calls) finishes normally, and the
  flag is observed before the next step starts.
- **`_handle_interrupt`** (parallel to `_handle_ask_user`) persists the
  full state snapshot using the same `paused_*` state keys, then emits
  a new `EventType.INTERRUPTED` stream event.
- **Resume** via the existing `_resume_from_pause` path; it now also
  triggers on `pending_interrupt` state and appends the new user turn
  as a regular message.
- **`AgentExecutor._active_agents: dict[str, Agent]`** registers the
  agent while a mission is streaming.  `executor.interrupt(session_id)`
  looks it up and calls `agent.request_interrupt()`.
- **CLI** — first Ctrl+C triggers the soft interrupt (via a
  `_CtrlCGuard.set_soft_handler` hook).  A second Ctrl+C within the
  force-exit window still calls `os._exit(130)` so a stuck process can
  always be killed.
- **REST** — `POST /api/v1/execute/{session_id}/cancel` returns `202
  Accepted` with `{"status": "interrupt_requested"}`, or `404` when no
  execution is active for the session.

A final COMPLETE event with `status=paused` is emitted after the
INTERRUPTED event, keeping stream consumers that already special-case
`ExecutionStatus.PAUSED` working unchanged.

## Alternatives Considered

- **Hard cancellation via `asyncio.Task.cancel`** — would interrupt
  mid-LLM-stream.  Discarded because state persistence during a
  partially consumed stream is fragile; the user's priority was a clean
  resume, not an instant abort.
- **New dedicated `pending_cancel` state keys** — would duplicate the
  existing `paused_*` keys already written by `ask_user`.  Sharing the
  keys means `_resume_from_pause` handles both triggers with a single
  branch.
- **Per-request executor instance** — would lose the shared
  `_active_agents` registry.  The executor is a singleton (`lru_cache`
  in `api/dependencies.py`), which matches the existing
  CLI/REST wiring.

## Consequences

- Stream consumers see a new `interrupted` event type; existing code
  that switches on `EventType` defaults to ignoring unknown types, so
  the change is backward-compatible.
- `ExecutionResult.status` can now be `"paused"` for reasons other than
  `ask_user`; callers should not assume a `pending_question` is always
  present when status is paused.
- The `ContextManager.messages` list is snapshotted (copied) into
  `state["paused_messages"]` at interrupt time — same contract as
  `ask_user`.

## References

- CLI wiring: `src/taskforce/api/cli/simple_chat.py`
- REST endpoint: `src/taskforce/api/routes/execution.py`
  (`POST /execute/{session_id}/cancel`)
- Executor registry: `src/taskforce/application/executor.py`
  (`_active_agents`, `interrupt`, `has_active_session`)
- Interrupt handler: `src/taskforce/core/domain/planning/interrupt.py`
- Resume path: `src/taskforce/core/domain/planning/state.py`
  (`_resume_from_pause`)
