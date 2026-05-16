---
feature: persistent-agent
status: shipped
since: 2026-03-18
last_verified: 2026-05-16
owner: rudi77
adr: ADR-016
---

# Persistent Agent Service — Sessionless Orchestrator

A long-running orchestrator that replaces the legacy "one agent per request"
model: one process, one singleton agent, one global state document, one
serialised request queue. Inbound messages from every channel (Telegram, CLI,
REST, scheduled jobs, internal events) are normalised into `AgentRequest`
objects, enqueued, and processed one-at-a-time so the shared agent state never
races. Callers get an awaitable result back; operators get a live view of
queued/in-flight missions plus the ability to cancel either kind.

## Capabilities (what the operator/embedder can do)

- start the service once at process boot and submit requests from any channel for the rest of the process's life
- await each request's outcome (`RequestResult` with `status`, `reply`, `error`) without managing per-request agent lifecycles
- submit higher-priority requests (lower priority number) and have them jump the queue ahead of normal user messages
- list every queued and in-flight mission with `request_id`, `session_id`, `channel`, `priority`, `conversation_id`, `status`, and a message preview
- cancel a queued mission (Future resolves with `status="cancelled"`, processor skips it) or an in-flight mission (cooperative interrupt forwarded to the running session)
- inspect a live snapshot (`AgentStatus`) with running flag, queue depth, active conversations, start time, last-activity timestamp, and state version
- gracefully stop the service — drains the queue (bounded by `drain_timeout`), cancels the processor, persists state
- tune queue back-pressure via `queue_max_size` and shutdown patience via `drain_timeout`
- run alongside an HTTP server: when an embedder calls `set_persistent_agent_service`, `GET /api/v1/missions` and `POST /api/v1/missions/{id}/cancel` light up automatically

## Invariants (what must always be true)

- Exactly one request is executed at a time — the processor pops sequentially from the queue, so the singleton agent's state cannot be mutated concurrently.
- `submit()` raises `RuntimeError` if the service has not been started (or the processor task has already exited) instead of silently dropping the request.
- `start()` is not re-entrant — a second `start()` on an already-running service raises `RuntimeError` rather than spawning a second processor.
- Cancelling a queued request resolves the caller's Future exactly once with `status="cancelled"`; when the processor later pops it, the executor is never invoked for that request.
- Cancelling an in-flight request never force-kills the agent — it forwards `AgentExecutor.interrupt(session_id)` so the agent pauses at the next ReAct boundary with state persisted.
- `cancel_request` returns `status="not_found"` (translated to 404 at the REST layer) when the `request_id` matches neither a queued nor an in-flight item.
- The queue's priority ordering breaks ties by FIFO insertion order, so two requests with the same `priority` are processed in the order they were submitted.
- The bounded queue applies back-pressure: `enqueue` awaits when `queue_max_size` is reached rather than rejecting.
- An exception inside a single request's execution is caught, reported via `RequestQueue.fail()` (Future resolves with `status="failed"`), and the processor continues with the next request.
- `stop()` is idempotent on a never-started service (returns immediately) and on a drained service (no error).
- `stop()` always attempts to persist agent state after draining, even when the drain itself hit `drain_timeout` — operator gets state continuity over a clean drain.
- Each request reuses its stable `session_id` for executor calls; when `session_id` is `None`, the processor falls back to `request_id` so every execution has a deterministic session key.
- Sub-agents spawned during a request still run with their own ephemeral contexts — the "one at a time" constraint applies only to top-level orchestrator turns, not to nested parallel tools.

## API surface (the contract clients depend on)

These routes are only registered as "live" once an embedder publishes the
service via `set_persistent_agent_service` (the agent daemon does this at
startup; standalone API processes do not).

- GET  /api/v1/missions → 200 with `{missions: [...]}`
- GET  /api/v1/missions → 503 when no service is registered
- POST /api/v1/missions/{request_id}/cancel → 202 with `{request_id, session_id, status}`
- POST /api/v1/missions/{request_id}/cancel → 404 when the request is neither queued nor in-flight
- POST /api/v1/missions/{request_id}/cancel → 503 when no service is registered

## Configuration surface

- `PersistentAgentService(queue_max_size=...)` (default 100) — bounded `asyncio.PriorityQueue` capacity; once full, `enqueue` awaits a free slot
- `PersistentAgentService(drain_timeout=...)` (default 30.0 s) — wall-clock budget `stop()` gives the queue before logging a drain warning and forcing processor cancel
- `request_queue.max_size: int` / `request_queue.drain_timeout: float` in profile YAML — what the agent daemon reads to build the service (see `agent-daemon.md`)
- `AgentRequest.priority: int` (default 10) — lower wins; the conventional levels are 0 (urgent events), 5 (scheduled tasks), 10 (normal user messages)

## Extension points

- `AgentStateProtocol` in `taskforce.core.interfaces.agent_state` — implement to back the singleton state document with something other than the default file store
- `taskforce.api.dependencies.set_persistent_agent_service(service)` — embedders publish their service here so REST routes (and any module calling `get_persistent_agent_service`) find the canonical instance; resolved per-request, not cached
- `RequestProcessor(queue, executor, conversation_manager=...)` — replaceable consumer; the service wires the default one, but an embedder can subclass to add tracing/metrics around `_process_request`

## Tests (must exist and pass)

- spec("persistent-agent.start_rejects_double_start")
- spec("persistent-agent.submit_before_start_raises")
- spec("persistent-agent.requests_processed_sequentially")
- spec("persistent-agent.higher_priority_jumps_queue")
- spec("persistent-agent.same_priority_preserves_fifo")
- spec("persistent-agent.exception_in_one_request_does_not_stop_processor")
- spec("persistent-agent.cancel_queued_resolves_future_and_skips_execution")
- spec("persistent-agent.cancel_in_flight_calls_executor_interrupt")
- spec("persistent-agent.cancel_unknown_returns_not_found")
- spec("persistent-agent.stop_drains_queue_then_saves_state")
- spec("persistent-agent.stop_saves_state_even_when_drain_times_out")
- spec("persistent-agent.session_id_falls_back_to_request_id")
- spec("persistent-agent.list_missions_marks_in_flight_vs_queued")
- spec("persistent-agent.bounded_queue_applies_backpressure")

## Known gaps

- **`RequestQueue.complete` and `RequestQueue.cancel` can race on the same `request_id`** — if a cancel arrives between the processor's `_execute` and `complete`, the cancelled Future is resolved first and `complete` becomes a no-op, but the in-flight executor still runs to completion. Tracked in issue #317.
- **`PersistentAgentService.stop()` has no graceful processor shutdown** — after the (possibly timed-out) drain it unconditionally `cancel()`s the processor task, so a request that started executing during the drain window is aborted via `CancelledError` rather than allowed to finish. Tracked in issue #337.
- **No global crash cap on the processor.** `_run_processor` re-raises on uncaught exceptions; the embedder (typically the agent daemon supervisor) is responsible for restart — the service itself does not self-heal.
- **`AgentStatus.state_version` is a snapshot of what was loaded at `start()`** — it does not increment on every successful request, so two callers can compare versions without ever observing a change.
- **No tenant/ownership check on mission routes.** Any authenticated caller with access to `GET /api/v1/missions` sees every other tenant's queued work; cancel is similarly unscoped.
- **No backend `@pytest.mark.spec` markers exist yet** — Tests section above asserts the target, not current state.

## Cross-references

- adr: ADR-016 (Persistent agent architecture)
- adr: ADR-019 (Cooperative agent interruption — what `cancel_in_flight` forwards to)
- related_spec: agent-daemon.md (the daemon owns the service's lifecycle and republishes its API hooks)
- related_spec: conversations.md (`ConversationManager` is wired into the processor so user/assistant messages persist around each request)
- related_spec: interruption.md (the executor-level interrupt contract that in-flight cancel relies on)
- docs: CLAUDE.md → "Application" section (`persistent_agent_service.py`, `request_queue.py`)
- commit: 23a9c4d (introduced 2026-03-18)
- commit: b6d1bc5 (cancel-request wiring, 2026-05-06)
