---
feature: workflows
status: shipped
since: 2026-03-15
last_verified: 2026-05-16
owner: rudi77
adr: ADR-014
---

# Workflow Runtime — Multi-Step Orchestration with HITL Checkpoints

First-class workflows: YAML/JSON definitions composed of named agent
steps with `depends_on` edges, launched by one of five trigger kinds
(manual, chat, schedule, event, webhook). Independent steps in the
same dependency level run in parallel. Steps can pause for external
input (HITL checkpoint) and resume later, optionally re-entering the
original skill via `activate_skill`. A step may delegate to a remote
ACP peer instead of a local agent. Tenants manage definitions through
a REST + UI CRUD surface; the scheduler integration is automatic.

## Capabilities (what the user can do)

- author a workflow as a graph of agent steps with `depends_on` edges
- pick a trigger kind from `manual | chat | schedule | event | webhook`
- store and edit workflow definitions per tenant via REST or the bundled UI
- run a stored workflow by id and get the per-step results back
- fan out independent steps in parallel within a dependency level, then join before the next level
- pause a step on a checkpoint that declares which inputs are required to resume
- resume a paused workflow with an inbound payload (REST or by re-invoking the originating skill)
- trigger a workflow by HTTP POST to `/api/v1/workflows/webhooks/<path>` with optional HMAC signature verification
- have a `schedule`-triggered workflow auto-register in the scheduler so its cron fires it on time
- delegate any step to a remote ACP peer via `acp_peer` instead of a local agent
- list all definitions, fetch one by id, and delete (which also drops the matching cron job)

## Invariants (what must always be true)

- A workflow with zero steps, duplicate step ids, dangling `depends_on`, or a dependency cycle is rejected at save time with HTTP 400 — invalid definitions never land on disk.
- `schedule`-triggered definitions with a malformed cron expression are rejected at save time before being mirrored to the scheduler.
- Saving a `schedule` workflow registers exactly one scheduler job per `workflow_id`; re-saving with a different cron replaces the prior job atomically (no orphans).
- Deleting a definition also unregisters its scheduled job.
- Changing a definition's trigger away from `schedule` removes any previously registered scheduler job for that workflow.
- Steps within a dependency level run concurrently via `asyncio.gather`; levels are awaited in order so a downstream step always sees every dependency's `final_message` in its mission text.
- A webhook trigger with a configured HMAC secret rejects requests whose signature is missing or wrong with HTTP 401 — the workflow never runs.
- A webhook trigger with no configured secret is an open endpoint by operator choice (`secret` and `secret_env` both absent).
- Webhook path matching is case-insensitive and leading-slash-insensitive on both the definition's `trigger_config.path` and the request URL tail.
- A `resume` on a checkpoint not in status `waiting_external` returns HTTP 400 — re-resuming a completed run cannot mutate it.
- A resume payload that lacks any field listed in `required_inputs.required` is rejected with HTTP 400; the checkpoint stays `waiting_external`.
- Every resume event is appended to the checkpoint's `state.resume_events` history; the latest also lands in `state.latest_resume_event`.
- A step with `acp_peer` set but no ACP runtime wired returns a `failed` step result; it does not fall back to local execution silently.
- A webhook delivery whose path is unknown to the current tenant is re-tried under the owner tenant (via the cross-tenant resolver hook); only a global miss returns 404.

## API surface (the contract clients depend on)

All routes are mounted under `/api/v1/workflows`. The `webhooks/` and
`{run_id}/resume*` subtrees are auth-exempt; the rest require the
documented permission.

- GET    /api/v1/workflows/definitions → 200 with list of definitions (requires `agent:read`)
- POST   /api/v1/workflows/definitions → 200 with `{workflow, scheduled_job_id}` (requires `agent:update`)
- POST   /api/v1/workflows/definitions → 400 on `invalid_workflow` (empty/cyclic/dangling-dep/malformed cron)
- GET    /api/v1/workflows/definitions/{workflow_id} → 200 with definition (requires `agent:read`)
- GET    /api/v1/workflows/definitions/{workflow_id} → 404 if missing
- DELETE /api/v1/workflows/definitions/{workflow_id} → 200 `{deleted: true}` (requires `agent:delete`)
- DELETE /api/v1/workflows/definitions/{workflow_id} → 404 if missing
- POST   /api/v1/workflows/definitions/{workflow_id}/run → 200 with per-step results (requires `agent:execute`)
- POST   /api/v1/workflows/definitions/{workflow_id}/run → 400 on `invalid_workflow`
- POST   /api/v1/workflows/webhooks/{trigger_path:path} → 200 with per-step results
- POST   /api/v1/workflows/webhooks/{trigger_path:path} → 401 on `invalid_webhook_signature`
- POST   /api/v1/workflows/webhooks/{trigger_path:path} → 404 on `webhook_workflow_not_found`
- POST   /api/v1/workflows/wait → 200 with `{run_id, status, node_id, blocking_reason, required_inputs}`
- GET    /api/v1/workflows/{run_id} → 200 with checkpoint
- GET    /api/v1/workflows/{run_id} → 404 if missing
- POST   /api/v1/workflows/{run_id}/resume → 200 with `{run_id, status, node_id, state}`
- POST   /api/v1/workflows/{run_id}/resume → 400 on missing-input or non-waiting checkpoint
- POST   /api/v1/workflows/{run_id}/resume-and-continue → 200 with `{run_id, checkpoint_status, execution}`
- POST   /api/v1/workflows/{run_id}/resume-and-continue → 400 when checkpoint has no `session_id`

## Configuration surface (the trigger_config keys operators rely on)

Trigger kind selectors on the `WorkflowDefinition`:

- `trigger: manual` — no config; ran only via the explicit `/run` endpoint or UI button
- `trigger: chat` — `trigger_config.match: <name>` (defaults to `workflow_id`); the gateway resolves `@name` mentions to this workflow (case-insensitive)
- `trigger: schedule` — `trigger_config.cron: "<5-field>"` (required); mirrored into the scheduler as `ScheduleActionType.EXECUTE_WORKFLOW` job `workflow__<workflow_id>`
- `trigger: webhook` — `trigger_config.path: "<url-tail>"`, optional `secret` or `secret_env` (HMAC secret), optional `signature_header` (default `X-Signature`), optional `signature_algo` in `{sha1, sha256, sha512}` (default `sha256`)
- `trigger: event` — `trigger_config.event_type: <name>`; event-bus dispatch (consumed by event source integrations)

Per-step:

- `step_id` (unique), `agent` (profile name), `task` (mission text)
- `depends_on: [step_id, ...]` — defines the dependency graph
- `acp_peer: <peer_id>` — when set, the runtime calls the named ACP peer instead of executing locally

Storage location: `${work_dir}/workflows/definitions/*.yaml`
(checkpoints under `${work_dir}/workflows/checkpoints/*.json`).
New writes are YAML; legacy JSON files continue to load.

## Extension points

- `WorkflowRuntimeService(acp_runtime=...)` — wiring an ACP runtime enables `acp_peer` steps; without it those steps return a `failed` result.
- `get_webhook_workflow_resolver` / `get_tenant_context_runner` in `taskforce.application.infrastructure_overrides` — enterprise plugins install these to resolve a webhook path's owning tenant when the request arrives with no tenant context.
- `FileWorkflowDefinitionStore` / `FileWorkflowCheckpointStore` — both swappable per tenant via the infrastructure builder; default implementations are file-backed under `work_dir/workflows/`.

## Tests (must exist and pass)

- spec("workflows.save_rejects_empty_steps_400")
- spec("workflows.save_rejects_cyclic_depends_on_400")
- spec("workflows.save_rejects_dangling_depends_on_400")
- spec("workflows.save_rejects_malformed_cron_400")
- spec("workflows.save_schedule_trigger_registers_cron_job")
- spec("workflows.resave_schedule_replaces_prior_job")
- spec("workflows.delete_definition_unregisters_cron_job")
- spec("workflows.change_trigger_away_from_schedule_removes_job")
- spec("workflows.run_executes_levels_in_parallel")
- spec("workflows.run_passes_dependency_final_message_to_downstream")
- spec("workflows.webhook_unknown_path_returns_404")
- spec("workflows.webhook_invalid_signature_returns_401")
- spec("workflows.webhook_no_secret_accepts_open")
- spec("workflows.resume_non_waiting_returns_400")
- spec("workflows.resume_missing_required_input_returns_400")
- spec("workflows.resume_appends_to_state_history")
- spec("workflows.resume_and_continue_requires_session_id")
- spec("workflows.acp_peer_step_without_runtime_returns_failed")
- spec("workflows.webhook_cross_tenant_resolver_runs_under_owner")

## Known gaps

- **`asyncio.gather` runs sibling steps without `return_exceptions=True`** — if one step in a parallel level raises, gather propagates immediately while the other sibling tasks keep running to completion. Checkpoints can land in inconsistent states (some steps `completed`, some never finalised). Tracked in #329.
- **Webhook HMAC verification has no replay protection** — a captured legitimate delivery can be replayed indefinitely (same root cause as gateway #285).
- **Webhook secret is opt-in.** With no `secret` / `secret_env` configured, the route accepts any payload. This is an operator choice but easy to overlook.
- **`event`-triggered workflows have no documented dispatch glue in framework core.** Operators can author the definition, but wiring an event source to actually invoke it is currently a custom integration.
- **No top-level mission timeout per step.** A hung step (LLM stall, tool deadlock) blocks the dependency level indefinitely. Related: #369.
- **Checkpoint store is not version-locked.** Concurrent `resume` calls on the same `run_id` race; the last writer wins.
- **No `@pytest.mark.spec` markers exist yet** — Tests section asserts the target, not current state. Spec-check will flag every marker as "asserted but missing test" on first run.
- **`resume-and-continue` re-creates a fresh agent** via `factory.create_agent(profile=request.profile)` and looks up `activate_skill` on it; if the original workflow ran under a different profile or used a custom agent, the resume profile must be supplied by the caller (default `butler`).

## Cross-references

- adr: ADR-014 (Resumable human-in-the-loop workflows + generative dreaming)
- related_spec: events-scheduler.md (cron jobs that drive `schedule`-triggered workflows; generic webhook endpoint contrasts with this spec's per-workflow webhooks)
- related_spec: gateway.md (`@workflow_name` chat mention resolution → `find_chat_workflow`)
- related_spec: acp.md (`acp_peer` step delegation, cross-tenant authorizer)
- docs: docs/features/generative-dreaming.md (dreaming subsystem co-shipped under ADR-014)
- commit: 1da3d29 (Workflow Definitions UI, 2026-05-06)
