# ADR-024: Standing Goals — proactive long-running objectives

**Status:** Accepted
**Date:** 2026-05-06

## Context

Until phase 3 of the event-driven branch the framework was purely
reactive: every mission started in response to a user message, an
external event (calendar, webhook), or a scheduled job firing a fixed
action. There was no concept of "things the agent should be working
towards on its own time" — no way to say *"every Monday 9am, prepare a
weekly summary of last week's work"* without writing a custom rule
that bypasses the agent's reasoning.

Two requirements drove this work:

1. **Proactive recurring intentions** — declarative goals the user
   adds once and the agent revisits on its own schedule.
2. **Cost-bounded evaluation** — the heartbeat cannot fire an LLM call
   per minute per goal; cron filtering must come *before* any model
   round-trip.

ADR-013 (Memory Consolidation) and ADR-014 (Generative Dreaming)
sketch a heavier autonomous-loop architecture, but those remain
unimplemented and we did not want to block proactive behavior on
those larger pieces.

## Decision

Add a small, framework-core proactive layer composed of:

* **`StandingGoal`** (`core/domain/standing_goal.py`) — a dataclass
  with `description`, `evaluation_prompt`, `frequency` (cron
  expression), `priority`, `enabled`, plus bookkeeping fields
  (`last_evaluated_at`, `last_action_taken`).
* **`StandingGoalStoreProtocol`** + file-backed implementation
  (`infrastructure/persistence/file_standing_goal_store.py`) — atomic
  JSON writes under `<work_dir>/standing_goals.json`, an `asyncio.Lock`
  serializes concurrent `mark_evaluated` calls.
* **`GoalEvaluatorService`** (`application/goal_evaluator_service.py`)
  — pulls due goals through a cheap cron pre-filter that re-uses
  `_next_cron_occurrence` from the SchedulerService, asks an injected
  decision callback, and submits a mission (priority taken from the
  goal) to the persistent agent on a positive answer.
* **REST + CLI surface** — `GET/POST/PATCH/DELETE /api/v1/standing-goals`,
  `POST /api/v1/standing-goals/{id}/evaluate-now`, and
  `taskforce goals list/show/add/disable/enable/remove/run-now`.
* **Heartbeat task** in the butler daemon — when the profile contains
  `proactive: { enabled: true, heartbeat_minutes: 15, standing_goals: [...] }`
  the daemon spawns a background `asyncio.Task` that calls
  `evaluate_due_goals` on every tick.

The decision callback defaults to *"act, send the goal's evaluation
prompt as the mission"* so the agent itself decides whether action is
warranted using its full memory + conversation context. Adopters who
want a dedicated cheap decision LLM can replace the callback before
`daemon.start()`.

Standing goals live in **the framework core**, not the butler
package, so coding-agent / rag-agent profiles can opt in by enabling
the same `proactive` block.

## Alternatives Considered

* **Schedule-job per goal.** Add one `ScheduleJob` per goal and let
  the existing scheduler dispatch a fixed mission on every firing.
  Discarded: it removes the "should we act now" reasoning step and
  forces every cron firing to start a mission, defeating cost control
  for goals like "monthly review if there's anything noteworthy".
* **Memory consolidation pipeline (ADR-013).** Bigger design, longer
  scope. Not needed for the basic *"proactive recurring objective"*
  use case and can be layered on later.
* **Module-level globals for the registry.** Adopted for the API
  surface (`set_goal_evaluator`, `set_standing_goal_store`) — same
  pattern as `set_persistent_agent_service`. The actual store is owned
  by the daemon; the API layer delegates to it.

## Consequences

* The persistent agent queue now sees a new request channel
  (`channel="standing_goal"`); the request metadata carries
  `standing_goal_id` so the agent can write follow-up state back to
  the goal in future iterations (not yet implemented).
* The butler profile YAML grows a `proactive:` section; missing it
  preserves the pre-Phase-3 reactive behavior bit-for-bit.
* When two clients (daemon + REST) operate on the same store the
  filesystem lock is the only consistency guarantee — adequate for
  single-host deployments, insufficient for multi-host. A multi-host
  deployment would need a `PostgresStandingGoalStore` implementing
  the same protocol; left as future work.

## References

- Domain: `src/taskforce/core/domain/standing_goal.py`
- Protocol: `src/taskforce/core/interfaces/standing_goals.py`
- Store: `src/taskforce/infrastructure/persistence/file_standing_goal_store.py`
- Evaluator: `src/taskforce/application/goal_evaluator_service.py`
- REST: `src/taskforce/api/routes/standing_goals.py`
- CLI: `src/taskforce/api/cli/commands/goals.py`
- Daemon wiring: `agents/butler/src/taskforce_butler/daemon.py`
  (`_setup_proactive_layer`, `_heartbeat_loop`)
