# ADR-022 Follow-Up Backlog

**Source:** [`docs/adr/adr-022-multi-tenant-enterprise-runtime.md`](adr/adr-022-multi-tenant-enterprise-runtime.md)
**Last verified end-to-end:** 2026-05-04 (browser login + admin nav + tenant tables)
**Status legend:** ☐ open · ☑ done · ⊘ explicitly out of scope

This file tracks the gaps that remain between the framework slots
ADR-022 specified and a real end-to-end story for each slice. Items
that exist as protocols/seams but are not yet wired through to
working behaviour live here. Closing an item means: implementation +
code review + tests + commit. Tick the checkbox in the same commit
and move on.

---

## Critical wiring gaps (block end-to-end stories)

### ☑ G1 — Gateway singleton captures only the first tenant's components

**Closed in:** `feat(adr-022/G1): re-read gateway components per outbound call` — gateway now accepts an optional `components_provider`; outbound + broadcast pull recipient registry and senders fresh from the provider on every call. Single-tenant builds with no provider see bit-for-bit prior behaviour. Provider failure falls back to constructor defaults.

**Where:** `src/taskforce/api/dependencies.py:115` (`@lru_cache(maxsize=1)`)

**Problem:** `get_gateway()` builds the `CommunicationGateway` exactly once per process, capturing whatever the override provider returned on the first call. Pattern A wires per-tenant components (`TenantScopedStoreFactory.gateway_components_for_current_tenant`), but the LRU cache means the SECOND tenant's request still sees the FIRST tenant's recipient registry, conversation store, outbound senders. Result: tenant-isolated outbound + broadcast is incomplete.

**Target:** Either re-instantiate the gateway per request (FastAPI scope), or reach into the gateway's components via an indirection that re-reads the override provider on every send.

**Touches:** `dependencies.py`, `gateway.py` (constructor → property), tests in `tests/unit/application/test_gateway.py` and possibly `tests/integration/`.

**Acceptance:** A test that flips `set_tenant_resolver` between two tenants and runs `send_notification` for each must hit two distinct recipient registries.

---

### ☑ G2 — Webhook trigger blocked by AuthMiddleware

**Closed in:** `feat(adr-022/G2): exempt webhook prefix + verify HMAC signature` (pytaskforce + taskforce-enterprise). The enterprise auth middleware now supports `exempt_path_prefixes` (default `/api/v1/workflows/webhooks/`) and the framework's webhook route reads the raw body, verifies an HMAC signature carried in a configurable header against a per-workflow secret (inline or via `secret_env`), and supports both plain-hex and GitHub-style `<algo>=<hex>` formats. With no secret configured the webhook is intentionally open — that is the operator's choice.

**Where:** `taskforce-enterprise/src/taskforce_enterprise/api/middleware/auth.py:54-63` (`exempt_paths` default), `pytaskforce/src/taskforce/api/routes/workflows.py` (`/webhooks/{path}`)

**Problem:** `POST /api/v1/workflows/webhooks/{path}` runs through the enterprise auth middleware and gets 401 — webhooks (GitHub, Stripe, Slack, etc.) carry their own signature, not a Bearer JWT. As shipped today the route exists but is unreachable from any third-party webhook source.

**Target:** Add a configurable webhook-exempt path prefix to the auth middleware, plus a per-workflow signature-verification hook that the webhook endpoint applies BEFORE running the workflow. Default: deny (require signature) so opening exempt_paths doesn't expose the endpoint to anonymous callers.

**Touches:** `taskforce-enterprise/api/middleware/auth.py`, `pytaskforce/src/taskforce/api/routes/workflows.py`, `pytaskforce/src/taskforce/core/domain/workflow_definition.py` (signature config in trigger_config?).

**Acceptance:** A workflow with `trigger: webhook, trigger_config: {path: hooks/x, signature: ...}` is reachable from a non-authenticated POST that carries a valid signature; an invalid/missing signature returns 401.

---

### ☑ G3 — Workflow schedule trigger doesn't auto-register

**Closed in:** `feat(adr-022/G3): auto-register workflow schedules on save` — `dependencies.py` now wires a shared `SchedulerService` into the workflow runtime service; the API server's lifespan handler starts/stops it; `POST /workflows/definitions` and `DELETE /workflows/definitions/{id}` are now async and call `register_schedule_for` / `unregister_schedule_for` so schedule-triggered workflows actually register cron jobs.

**Where:** `src/taskforce/application/workflow_runtime_service.py` (`save_definition` is sync, `register_schedule_for` is async + opt-in), `src/taskforce/api/dependencies.py` (`get_workflow_runtime_service` does not pass a SchedulerProtocol).

**Problem:** A user POSTs a definition with `trigger: schedule, trigger_config.cron`. The framework persists it; nothing schedules anything. The async `register_schedule_for` helper exists but no API call site invokes it. Plus the runtime service is built without a scheduler in the default DI graph.

**Target:** (a) Build the runtime service with the framework's `SchedulerService` injected. (b) The save endpoint awaits `register_schedule_for(definition)` after persistence; the delete endpoint awaits `unregister_schedule_for(workflow_id)`. (c) When trigger changes from `schedule` to anything else, old scheduled job is removed.

**Touches:** `dependencies.py`, `routes/workflows.py` (POST/DELETE handlers must `await`), tests around the route.

**Acceptance:** `POST /workflows/definitions` with a schedule trigger results in a `ScheduleJob` in the scheduler's job store; `DELETE` removes it; updating the cron replaces it.

---

### ☑ G4 — `EXECUTE_WORKFLOW` schedule action has no dispatcher

**Closed in:** `feat(adr-022/G4): dispatch EXECUTE_WORKFLOW schedule events to runtime` — added `WorkflowRuntimeService.run_workflow_id` and `application/scheduler_dispatcher.make_scheduler_event_callback`. The API server's lifespan now installs the callback on the shared `SchedulerService`, so cron-fired `EXECUTE_WORKFLOW` jobs actually run their workflow. Defensive: malformed payloads, unknown workflow ids and dispatcher exceptions don't kill the scheduler event loop.

**Where:** `src/taskforce/infrastructure/scheduler/scheduler_service.py` (fires `SCHEDULE_TRIGGERED` event with action payload), nothing listens for `execute_workflow` action.

**Problem:** A scheduled `EXECUTE_WORKFLOW` job fires and emits an `AgentEvent` carrying the workflow_id. There is no built-in handler that maps that event to `WorkflowRuntimeService.ordered_steps + executor.execute_mission`. Consequence: G3 alone is not enough — even after the Schedule is registered, the workflow never actually runs on the cron tick.

**Target:** Add a default scheduler-event-callback (registered alongside the runtime service in `dependencies.py`) that, on `EXECUTE_WORKFLOW`, looks up the definition and runs the same step sequence the explicit `/run` endpoint does. Audit-log on success/failure.

**Touches:** `application/workflow_runtime_service.py` (add `run_workflow_id(...)` helper), `application/scheduler_dispatcher.py` (new), `dependencies.py` (wire the callback into `SchedulerService(event_callback=...)`).

**Acceptance:** End-to-end test: register schedule with 1-second-from-now one-shot trigger of `EXECUTE_WORKFLOW`; sleep 2s; assert `executor.execute_mission` was called with the workflow's first step.

---

### ☑ G5 — Chat-trigger workflows not addressable by `@workflow_name`

**Closed in:** `feat(adr-022/G5): resolve @workflow_name mentions in gateway` — added `WorkflowLookupProtocol` + `set_workflow_lookup_override` framework slot. Gateway tries agent lookup first; on miss it consults the workflow lookup. A hit returns a `workflow_dispatched` response carrying `workflow_id` and the stripped message in `metadata` so the channel handler can drive `WorkflowRuntimeService.run_workflow_id`. Service helper `find_chat_workflow(name)` matches against `trigger_config.match` or workflow_id, case-insensitive.

**Where:** `src/taskforce/application/gateway.py` (`_extract_agent_mention` + `agent_lookup`), `WorkflowRuntimeService` (no chat resolver).

**Problem:** ADR-022 §7 lists `chat` as a trigger kind. Today an `@<word>` mention only resolves to a tenant-scoped agent via `AgentLookupProtocol`. There is no symmetric workflow lookup, so a definition with `trigger: chat, trigger_config.match: my-workflow` cannot be invoked from a chat message.

**Target:** Define `WorkflowLookupProtocol` (`find_by_chat_match(recipient, name) -> WorkflowDefinition | None`) and let the gateway consult it after the agent lookup misses. On hit, run the workflow steps through the executor and return the final assistant message as the channel reply.

**Touches:** `core/interfaces/gateway.py`, `application/gateway.py`, `application/workflow_runtime_service.py`, integration tests in `tests/integration/`.

**Acceptance:** A workflow named `daily-report` with `trigger: chat` is invoked when a user types `@daily-report` in a Telegram chat and the agent's reply lands back in the same chat.

---

## Workflow runtime gaps (ADR-022 §7 topology)

### ☑ G6 — Fan-out + Join executes sequentially

**Closed in:** `feat(adr-022/G6): execute independent workflow steps in parallel` — workflow steps now run in Kahn-style dependency levels via `asyncio.gather`. Two independent slow steps now overlap (verified by wallclock test) instead of running serially. Definition order within a level is preserved so the result list matches what callers used to see.

**Where:** `src/taskforce/api/routes/workflows.py:_execute_workflow_steps`

**Problem:** Steps are topologically ordered then run **strictly sequentially** in a `for` loop. Two independent steps of a fan-out cannot run in parallel. ADR-022 §7 specifies "fan-out + join" as a real topology.

**Target:** Group steps into "levels" of mutual independence (Kahn's-algorithm bands) and run each level via `asyncio.gather`. Single-thread pure async, no thread pool. Aggregate results across the level for downstream `depends_on` lookups.

**Touches:** `application/workflow_runtime_service.py` (move `_execute_workflow_steps` here as `run_definition_steps`), unit tests, route handler shrinks to a thin call.

**Acceptance:** A workflow with two parallel branches running 1-second mock missions completes in ~1s, not ~2s.

---

### ☑ G7 — ACP-mediated workflow steps not supported

**Closed in:** `feat(adr-022/G7): support ACP-mediated workflow steps` — `WorkflowStep` gains optional `acp_peer`. When set the runtime calls `AcpRuntime.call(peer, mission)` instead of the local executor; cross-tenant authorization (G4 chain) still gates the call. Fallback to local execution when no AcpRuntime is wired so single-tenant builds load mixed definitions without crashing. YAML round-trip preserves the field; omitted when unset to keep existing definitions byte-identical.

**Where:** `core/domain/workflow_definition.py` (`WorkflowStep.agent` is just a profile name).

**Problem:** A step can only run a local agent. Calling out to an ACP peer mid-workflow is impossible without writing it as a tool inside an agent.

**Target:** Add `WorkflowStep.acp_peer: str | None`. When set, the step runs `AcpRuntime.call(peer, mission)` instead of `executor.execute_mission`. Cross-tenant rules from `acp:peer:cross_tenant` apply automatically because the existing AcpRuntime guard fires.

**Touches:** `core/domain/workflow_definition.py`, `application/workflow_runtime_service.py` (or its successor), tests.

**Acceptance:** A workflow whose second step has `acp_peer: remote-butler` calls the remote peer with the first step's `final_message` as input and uses the result as `final_message` for the third step.

---

## Self-service product gaps

### ☐ G8 — No "Create Agent" UX in the management UI

**Where:** `taskforce-enterprise/web/src/pages/` (no agent creation page).

**Problem:** Backend has `PostgresAgentRegistry.create_agent()` and Custom-Agent persistence. Operators can drop YAML by hand or via API; end-users cannot.

**Target:** A page under `/admin/agents/new` (capability `agents.catalog`?) that guides through the YAML required-fields and POSTs to a new `/api/v1/admin/agents` route, then redirects to the catalog. Edit page for existing agents follows.

**Touches:** Enterprise web package + a new backend route in `taskforce-enterprise`.

**Acceptance:** Logged-in admin can create an agent via UI and see it in the catalog and chat with it in the same session.

---

### ☐ G9 — No tenant self-signup flow

**Where:** Enterprise-only. Today bootstrap is via `taskforce_enterprise.cli.admin_bootstrap` or `POST /admin/tenants` with `tenant:manage` perm.

**Problem:** A new prospective customer cannot register themselves. They need an operator to create their tenant and admin user.

**Target:** `/signup` route (no auth required) → creates tenant + first admin user + sends verification email. Email/Verification system is its own thing — could be deferred behind a feature flag.

**Touches:** Enterprise (signup route, email sender), web shell (signup page).

**Acceptance:** Anonymous user submits the signup form, receives a verification link, becomes the admin of a fresh tenant.

---

## Hygiene / smaller items

### ☐ G10 — `POST /api/v1/skills` lives in framework, should live in enterprise

**Where:** `pytaskforce/src/taskforce/api/routes/skills.py`

**Problem:** The endpoint tenant-scopes via the writable-skill-root provider (which the enterprise plugin sets), but its module-of-residence is the framework repo. ADR-022 §6 puts skill-write in the enterprise admin surface.

**Target:** Move the POST handler to `taskforce-enterprise/src/taskforce_enterprise/api/routes/admin/skills.py`. Framework keeps `GET /skills` for read-only listing. Permission `skill:create` (new).

**Touches:** Both repos, registry.

**Acceptance:** POST is gated by permission; framework single-tenant build no longer exposes the write endpoint.

---

### ☐ G11 — Update ADR-022 with implementation status

**Where:** `docs/adr/adr-022-multi-tenant-enterprise-runtime.md`

**Problem:** ADR is dated "Iteration 1 framework hook merged" but slices 1, 3, 5 (seam), 6, 7 are now substantially closed. New readers can't tell what's done.

**Target:** Add a "Status (post-iteration)" section at the top and check off each slice with the commit refs.

**Touches:** ADR file only.

**Acceptance:** A reader can tell what's working without reading 8 commits.

---

## Out of scope (per explicit user direction)

### ⊘ G12 — Container-backed `SandboxedExecutorProtocol` implementation

ADR-022 §5 enterprise side. Out of scope for this MVP push per
2026-05-04 user direction. The framework seam exists; the enterprise
container backend (Docker/gVisor mounting only the workspace, dropping
network capabilities, applying CPU/memory/wall-clock limits) is
deferred. Until then `warn_if_multi_tenant_without_sandbox()` fires
on startup so the unsafe state is visible.

---

## Working method

For each ☐ item:

1. Pick the highest-priority open item.
2. Mark it ☐→ in-progress in this file.
3. Implement.
4. Self-review the diff (security, error paths, public API stability).
5. Run the affected test files; add new ones where logic is new.
6. Commit with a Conventional-Commit-style message that references the gap id (e.g. `feat(adr-022/G3): auto-register workflow schedule on save`).
7. Tick ☐→ ☑ in the same commit; the file is the single source of truth for "what's left".
