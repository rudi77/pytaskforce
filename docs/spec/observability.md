---
feature: observability
status: shipped
since: 2026-01-02
last_verified: 2026-05-16
owner: rudi77
---

# Observability — Phoenix Tracing + Token Analytics

Two cooperating subsystems give the operator visibility into what every agent
just did and how much it cost. **Phoenix tracing** (optional, opt-in via
`--extra tracing`) auto-instruments LiteLLM so every LLM call, tool call and
agent step shows up as an OpenTelemetry span in Arize Phoenix (or any
OTLP-compatible collector). **Token analytics** (core, always on) records
every completion to a SQLite ledger so the dashboard can show per-session,
per-conversation, per-agent and per-model token + cost roll-ups without
depending on the trace backend.

## Capabilities (what the operator can do)

- enable Phoenix tracing by setting `TRACING_ENABLED=true` (default) and
  starting the API server — auto-instrumentation captures every LLM call
  with no code changes
- point traces at a custom Phoenix or OTLP collector via
  `PHOENIX_COLLECTOR_ENDPOINT` / `PHOENIX_GRPC_ENDPOINT` and group them
  under a custom project name via `PHOENIX_PROJECT_NAME`
- create custom spans inside application code via `get_tracer()` (returns
  `None` cleanly when tracing isn't initialised)
- track per-call token usage + USD cost for every completion without
  configuring anything — the LiteLLM callback installs at server import
- query token usage bucketed by `day` / `hour` / `minute` over an
  arbitrary time range via `GET /api/v1/analytics/token-usage`
- get a today / week / month cost roll-up plus breakdowns by agent and by
  model via `GET /api/v1/analytics/cost-summary`
- drill into one conversation's complete call list via
  `GET /api/v1/analytics/conversations/{id}/usage`
- override the ledger location with `TASKFORCE_ANALYTICS_DB` (defaults to
  `.taskforce/analytics.db`)

## Invariants (what must always be true)

- The token-analytics callback never raises into the LLM call path; any
  callback exception is swallowed and logged, the completion still
  returns normally.
- The SQLite write path catches every `sqlite3.Error` and returns `None`
  instead of propagating — a corrupt or locked ledger never breaks an
  agent run.
- Cost is computed from a pricing table at record time and stored as a
  numeric column; later pricing-table changes do not retroactively
  rewrite historical rows.
- Every recorded call carries its model name; rows without resolvable
  agent metadata fall back to `(unknown)` in aggregations rather than
  being dropped.
- `init_tracing()` is a best-effort no-op when `phoenix.otel` or
  `openinference.instrumentation.litellm` is not installed (warning
  logged, server continues to start).
- `init_tracing()` with `TRACING_ENABLED=false` skips all collector setup
  and returns immediately — no spans are exported and no warning fires.
- `shutdown_tracing()` flushes pending spans before clearing the global
  provider; calling it without a prior init is a no-op.
- Run-context metadata (session_id, conversation_id, agent_id, profile)
  set via `run_context(...)` is attached to every ledger row recorded
  inside that context, including rows produced by LiteLLM callbacks fired
  from background tasks the executor spawned.
- The SQLite ledger uses WAL journaling so analytics aggregations don't
  block the writer on the LLM hot path.
- `cost-summary` always returns the three rollups (`today_usd`,
  `week_usd`, `month_usd`) even on an empty database — zeros, not
  missing keys.

## API surface

- GET /api/v1/analytics/token-usage → 200 with buckets (granularity
  `day` | `hour` | `minute`, optional `from` / `to` ISO timestamps,
  optional `agent`)
- GET /api/v1/analytics/cost-summary → 200 with today / week / month
  rollups + per-agent + per-model breakdowns
- GET /api/v1/analytics/conversations/{conversation_id}/usage → 200 with
  per-conversation totals and per-call list

## Configuration surface

Tracing — environment variables read at `init_tracing()` time:

- `TRACING_ENABLED` (default `true`) — opt-out switch; disables all
  Phoenix setup when `false`
- `PHOENIX_PROJECT_NAME` (default `taskforce`) — Phoenix project under
  which spans are grouped
- `PHOENIX_COLLECTOR_ENDPOINT` (default `http://localhost:6006/v1/traces`)
  — HTTP OTLP endpoint
- `PHOENIX_GRPC_ENDPOINT` (default `http://localhost:4317`) — gRPC OTLP
  endpoint (used in preference to HTTP for performance)

Token analytics — environment variable:

- `TASKFORCE_ANALYTICS_DB` — override SQLite ledger path (default
  `.taskforce/analytics.db`)

Install the tracing dependencies via `uv sync --extra tracing`. Token
analytics ships in core and needs no extra.

## Extension points

- `get_tracer()` in `taskforce.application.tracing_facade` — returns the
  active OTEL tracer (or `None`) so application code can create custom
  spans without importing the infrastructure layer
- `run_context(...)` in `taskforce.application.token_ledger` — context
  manager that stamps session / conversation / agent / profile metadata
  on every ledger row recorded inside the block

## Tests (must exist and pass)

- spec("observability.token_callback_never_raises_into_llm_path")
- spec("observability.token_ledger_swallows_sqlite_errors")
- spec("observability.token_ledger_attaches_run_context")
- spec("observability.cost_summary_returns_zeros_on_empty_db")
- spec("observability.token_usage_buckets_by_granularity")
- spec("observability.tracing_disabled_when_env_false")
- spec("observability.tracing_init_noop_without_phoenix_installed")
- spec("observability.tracing_shutdown_flushes_before_clearing")
- spec("observability.analytics_db_path_honours_env_override")

## Known gaps

- **Tracing init/shutdown are not lock-protected.** `init_tracing()` and
  `shutdown_tracing()` mutate module-globals (`_tracer_provider`,
  `_tracer`) without synchronisation. Concurrent init from two startup
  paths, or a shutdown racing a re-init, can leak the provider or null
  the tracer mid-call. Tracked in #315.
- **Trace export is fire-and-forget.** `init_tracing()` swallows export
  failures with a single warning; downstream collector outages are not
  retried and not surfaced beyond the log line.
- **No `@pytest.mark.spec` markers exist yet** — the Tests section
  asserts the target, not current state. spec-check will report every
  marker as "asserted but missing test" on first run.

## Cross-references

- related_spec: llm-service.md (the LiteLLM service whose every
  completion the token callback observes and Phoenix auto-instruments)
- related_spec: conversations.md (run-context plumbing that stamps
  `conversation_id` onto ledger rows)
- docs: CLAUDE.md → "Infrastructure" → `tracing/phoenix_tracer.py` and
  `llm/token_analytics_callback.py`
