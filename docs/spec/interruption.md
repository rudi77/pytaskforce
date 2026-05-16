---
feature: interruption
status: shipped
since: 2026-03-15
last_verified: 2026-05-16
owner: rudi77
adr: ADR-019
---

# Cooperative Agent Interruption

Lets a caller cancel a running mission without killing the process, losing
context, or leaving sub-agents and subprocesses running in the background.
The agent finishes its current in-flight step (LLM call + tool calls),
persists its full state, emits an `INTERRUPTED` event, and exits with
`ExecutionStatus.paused` so the same session can be resumed later. Used by
the web Stop button, CLI `Ctrl+C`, the REST `/missions/{id}/cancel` route,
and any in-process caller that holds an `Agent` reference.

## Capabilities (what the user / operator can do)

- request a cooperative interrupt programmatically via `agent.request_interrupt()`
- cancel a queued or in-flight mission over REST via `POST /api/v1/missions/{request_id}/cancel`
- cancel a mission from the CLI via `taskforce missions cancel <request_id>`
- list everything cancellable via `GET /api/v1/missions` (or `taskforce missions running`)
- interrupt a parent mission and have it propagate automatically to every running sub-agent spawned under it
- resume the interrupted session with a new turn — paused state (messages, step, plan) is restored transparently

## Invariants (what must always be true)

- A successful interrupt produces `ExecutionStatus.paused`, never `failed`, so the session remains resumable.
- The interrupt is observed at the next ReAct loop boundary — the in-flight LLM call and any tool calls already started run to completion; partial work is never abandoned mid-call.
- An `INTERRUPTED` event is emitted exactly once on the stream when a pending interrupt is observed, followed by the standard terminal `COMPLETE`.
- After an `INTERRUPTED` event, the persisted session state contains paused-execution keys (messages, step, plan progress, active skill) that a subsequent `execute_stream` call with the same `session_id` uses to resume transparently.
- The interrupt flag is cleared once handled, so a later resume does not immediately re-trigger the pause.
- Requesting an interrupt on a `session_id` that is not running returns `False` (programmatic) / `404` (REST) — never silently succeeds.
- Cancelling a queued (not-yet-started) mission removes it from the queue with `status="cancelled"`; cancelling an in-flight one returns `status="interrupt_requested"`.
- Interrupting a parent agent fires every registered interrupt callback, signalling every sub-agent currently running under the same parent session.
- The CLI / programmatic / REST entry points all converge on the same `AgentExecutor.interrupt(session_id)` path — there is no second cancellation code path with different semantics.

## API surface (the contract clients depend on)

- GET  /api/v1/missions → 200 with list of queued + in-flight missions
- GET  /api/v1/missions → 503 when no `PersistentAgentService` is registered with the API process
- POST /api/v1/missions/{request_id}/cancel → 202 accepted, body carries `status` ∈ `{"cancelled", "interrupt_requested"}`
- POST /api/v1/missions/{request_id}/cancel → 404 when no queued or in-flight request with that id exists
- POST /api/v1/missions/{request_id}/cancel → 503 when no `PersistentAgentService` is registered

## Event stream contract

- `INTERRUPTED` — emitted on cooperative cancel; payload `{reason, timestamp, step}`. The matching terminal `COMPLETE` event that follows carries `status="paused"`.

See `react-loop.md` for where `INTERRUPTED` sits in the full event lifecycle.

## Extension points

- `Agent.add_interrupt_callback(callback)` / `Agent.remove_interrupt_callback(callback)` — register a no-arg hook fired synchronously when `request_interrupt()` is called. Used by `SubAgentSpawner` to forward a parent's interrupt to its children; any orchestration tool that spawns work outside the ReAct loop should do the same.

## Tests (must exist and pass)

- spec("interruption.programmatic_request_sets_paused_status")
- spec("interruption.rest_cancel_inflight_returns_202_interrupt_requested")
- spec("interruption.rest_cancel_queued_returns_202_cancelled")
- spec("interruption.rest_cancel_unknown_returns_404")
- spec("interruption.interrupt_emits_interrupted_event_then_complete")
- spec("interruption.paused_state_persisted_for_resume")
- spec("interruption.resume_after_interrupt_continues_session")
- spec("interruption.interrupt_propagates_to_sub_agents")
- spec("interruption.interrupt_observed_after_inflight_step_finishes")
- spec("interruption.interrupt_flag_cleared_after_handling")

## Known gaps

- **Sub-agent callbacks fail silently.** `Agent.request_interrupt()` wraps each `_on_interrupt_callbacks` invocation in a bare `except Exception` and only emits a warning log. A buggy callback can therefore leave a sub-agent running while the parent thinks the interrupt propagated, with no visible failure on the stream. Tracked in #335.
- **No `@pytest.mark.spec` markers exist yet** — the Tests section above asserts the target, not current state. Spec-check will flag every marker as "asserted but missing test" on first run.
- **No interrupt-acknowledgement timeout.** A pathologically slow tool can block the next loop-boundary check indefinitely; there is no upper bound on how long the agent may take to observe an interrupt request.

## Cross-references

- adr: ADR-019 (Cooperative Agent Interruption)
- related_spec: react-loop.md (INTERRUPTED event in the full event lifecycle)
- related_spec: sub-agents.md (callback propagation to spawned children)
- docs: CLAUDE.md → "Cooperative Agent Interruption" / ADR-019 references
