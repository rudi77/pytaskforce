---
feature: standing-goals
status: shipped
since: 2026-05-06
last_verified: 2026-05-16
owner: rudi77
adr: ADR-024
---

# Standing Goals — Proactive Recurring Intentions

A standing goal is a declarative "thing the agent should be working towards
on its own time" — for example *"every Monday 9am, prepare a weekly summary
of last week's work"*. The user adds a goal once (REST, CLI, or butler
profile YAML); a heartbeat task in the running daemon revisits every enabled
goal on its cron schedule, asks the LLM whether to act now, and on a positive
answer submits a mission to the agent. Goals are framework-core and opt-in —
without the `proactive:` block the daemon stays purely reactive.

## Capabilities (what the user can do)

- add a standing goal with description, evaluation prompt, cron frequency, and priority
- list every standing goal (enabled and disabled), with last-evaluated timestamp
- look up a single goal by id
- update any field of a goal in place (description, prompt, frequency, priority, enabled, metadata)
- disable a goal without losing its configuration, and re-enable it later
- permanently remove a goal
- force an immediate LLM evaluation of one goal regardless of cron schedule
- seed initial goals from the agent profile YAML so a fresh install starts proactive

## Invariants (what must always be true)

- A goal is evaluated only when both `enabled` is true AND its cron expression has fired since the last evaluation. Disabled goals are silently skipped.
- The cron pre-filter runs before any LLM call, so heartbeat frequency does not multiply LLM cost; a weekly goal incurs at most one LLM call per week, not one per heartbeat tick.
- On first run (`last_evaluated_at is None`) every enabled goal is considered due so proactive behaviour starts immediately, not on the next cron boundary.
- A malformed cron expression falls back to "always due" so the misconfiguration surfaces in `last_action_taken` rather than silently disabling the goal.
- `mark_evaluated` updates are serialised process-wide; concurrent ticks (heartbeat + forced `evaluate-now`) cannot lose an update.
- Standing-goal store writes are atomic — a crashed write never leaves a corrupted `standing_goals.json`; a corrupted file is logged and treated as empty rather than crashing the daemon.
- A failed LLM decision or failed mission submission never marks the goal as evaluated, so the next tick will retry.
- Submitted missions carry `channel="standing_goal"` and `metadata.standing_goal_id` so downstream consumers can attribute the mission back to its goal.
- The REST CRUD endpoints work without a running daemon (lazy file-backed default store); only `evaluate-now` requires a daemon (returns 503 otherwise).
- Removing the `proactive:` block from the profile reproduces the pre-ADR-024 reactive behaviour bit-for-bit.

## API surface (the contract clients depend on)

- GET    /api/v1/standing-goals → 200 (list, every goal)
- POST   /api/v1/standing-goals → 201 created
- GET    /api/v1/standing-goals/{goal_id} → 200
- GET    /api/v1/standing-goals/{goal_id} → 404 if missing
- PATCH  /api/v1/standing-goals/{goal_id} → 200 (partial update)
- PATCH  /api/v1/standing-goals/{goal_id} → 404 if missing
- DELETE /api/v1/standing-goals/{goal_id} → 204
- DELETE /api/v1/standing-goals/{goal_id} → 404 if missing
- POST   /api/v1/standing-goals/{goal_id}/evaluate-now → 202 (forced evaluation result)
- POST   /api/v1/standing-goals/{goal_id}/evaluate-now → 404 if missing
- POST   /api/v1/standing-goals/{goal_id}/evaluate-now → 503 when no daemon is running

## Configuration surface (the profile keys / env vars operators rely on)

The proactive layer is configured in the agent profile YAML under `proactive:`.
Missing block ⇒ disabled. Standing-goal data persists under `<work_dir>/standing_goals.json`.

- `proactive.enabled: bool` (default `false`) — master switch; when `false` no heartbeat task is started and the REST CRUD still works against the lazy default store
- `proactive.heartbeat_minutes: float` (default `15`) — upper bound on goal-evaluation latency; minimum effective sleep is 1 second
- `proactive.standing_goals: list` (default `[]`) — seed goals loaded on daemon startup; entries that already exist by `goal_id` are skipped (idempotent)
- each seed entry: `description`, `evaluation_prompt` (supports `$NOW` / `$LAST_EVALUATED_AT` substitution), `frequency` (5-field cron), `priority` (int, default 5, lower runs first), `enabled` (default true), optional `goal_id` and `metadata`
- `TASKFORCE_WORK_DIR` — root for the default file store (used by the lazy REST default when no daemon registered a store)
- `TASKFORCE_API_URL` — base URL the `taskforce goals` CLI talks to (default `http://127.0.0.1:8000`)

## Extension points

- `set_standing_goal_store_override(provider)` in `taskforce.application.infrastructure_overrides` — enterprise plugins use this to route the store per `(tenant, user)`. Provider receives the work dir and returns a `StandingGoalStoreProtocol`. Resolved by `InfrastructureBuilder.build_standing_goal_store`, not cached.
- `set_standing_goal_store(store)` / `set_goal_evaluator(evaluator)` in `taskforce.api.dependencies` — daemon-side registration so REST routes find the canonical store and evaluator owned by the running daemon. Both are cleared on daemon shutdown.
- `StandingGoalStoreProtocol` in `taskforce.core.interfaces.standing_goals` — alternative store implementations (e.g. a future `PostgresStandingGoalStore`) implement this and are wired through the override hook.
- `GoalEvaluatorService.decide` callback — adopters wanting a cheap dedicated decision LLM replace the default "always act" callback before `daemon.start()`.

## Tests (must exist and pass)

- spec("standing-goals.cron_prefilter_skips_when_not_due")
- spec("standing-goals.first_run_evaluates_even_without_history")
- spec("standing-goals.disabled_goal_is_skipped")
- spec("standing-goals.bad_cron_falls_back_to_always_due")
- spec("standing-goals.decision_failure_does_not_mark_evaluated")
- spec("standing-goals.submit_failure_does_not_mark_evaluated")
- spec("standing-goals.submitted_mission_carries_goal_id_metadata")
- spec("standing-goals.store_writes_are_atomic")
- spec("standing-goals.store_concurrent_mark_evaluated_serialized")
- spec("standing-goals.rest_crud_roundtrip")
- spec("standing-goals.evaluate_now_returns_503_without_daemon")
- spec("standing-goals.daemon_seeds_yaml_goals_idempotent")

## Known gaps

- **`evaluate-now` returns 202 Accepted but the response body is the synchronous result.** The HTTP semantics suggest queued/async, but the call blocks on the LLM decision and mission submission. Either the status code should change to 200 or the route should genuinely be made async.
- **Per-user override is wired but not yet exercised by enterprise routing.** Issue #196 added `set_standing_goal_store_override`; the enterprise plugin's per-user store factory still needs to call it for true per-user isolation (today goals leak across users of the same daemon).
- **No multi-host consistency.** Two daemons sharing the same `work_dir` will both evaluate every goal — the filesystem lock prevents corruption but not duplicate execution. A `PostgresStandingGoalStore` is the planned multi-host path; not yet implemented.
- **Goal-update REST PATCH does not validate the cron expression** — an invalid `frequency` is accepted and only surfaces at the next evaluation tick (which then falls back to "always due"). Cron validation happens nowhere in the write path.
- **No goal-history endpoint.** Only `last_evaluated_at` + `last_action_taken` are stored; the agent cannot ask "how often did this goal fire this month" without a separate audit log.
- **`taskforce goals` CLI has no `update`/`patch` subcommand** — only `enable` and `disable` are exposed; changing the prompt or cron requires curl or editing the JSON file directly.
- **No backend `@pytest.mark.spec` markers exist yet** — Tests section asserts the target, not current state. `tests/unit/application/test_goal_evaluator_service.py` exists but is unmarked.

## Cross-references

- adr: ADR-024 (Standing Goals — design and rationale)
- related_spec: events-scheduler.md (re-uses `_next_cron_occurrence` from the scheduler)
- related_spec: conversations.md (submitted missions flow through the persistent agent queue)
- related_spec: multi-tenant.md (per-user override hook for tenant scoping)
- docs: CLAUDE.md → "Proactive Layer — Standing Goals (ADR-024)" section
- commit: ADR-024 introduced 2026-05-06
