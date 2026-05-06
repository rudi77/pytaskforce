# Stabilization Log (post v0.2.0)

After v0.2.0 ships ADR-022, the project is in a stabilization phase: bug
fixes, hardening, and test coverage only. **No new features.** This log
tracks the systematic feature-by-feature audit and the findings + fixes.

## How this log works

For each feature we run a focused test session — golden path + the edge
cases the implementation should already handle — and record what we
find. Findings are split into:

- **🟥 Bug** — wrong/broken behavior that a fix must address.
- **🟨 Rough edge** — works but is confusing, inconsistent, or
  under-documented. Fix or document.
- **🟩 OK** — verified working as designed.

Each finding gets a stable id (e.g. `WF-01`) so commit messages can
reference it. When fixed, add a `Fixed in: <commit>` line and tick the
checkbox.

## Priority order

Based on the user's daily use (reliable Telegram-driven Butler) and the
fact that v0.2.0 just shipped a lot of new surface area:

### P0 — Core daily-use paths

1. **Workflows runtime + UI** (just shipped, broad surface)
2. **send_notification → Telegram outbound** (we touched it twice today)
3. **Butler daemon lifecycle + Telegram long-polling inbound**
4. **Scheduler / cron tool** (drives Butler's daily routine)
5. **Persistent conversations** (ADR-016) — message round-trip durability

### P1 — Feature breadth

6. **Skills hot-reload + prompt/agent slash invocation**
7. **Tools used by Butler** (gmail, calendar, wiki, ask_user, web_fetch)
8. **Custom agents CRUD + chat picker**
9. **REST execution API** (`/api/v1/execute`, streaming, cancel)
10. **CLI surface** (`run mission`, `chat`, `tools list`, `skills list`)

### P2 — Enterprise + supporting

11. **JWT auth flow** (login, 401 redirect, signup)
12. **Multi-tenant gateway** (`browser_tenant`, tenant-scoped stores)
13. **RBAC / policy engine + admin routes**
14. **ACP peers + cross-tenant authorizer**
15. **UI: Dashboard, Monitoring, Capabilities, Evals, Settings**
16. **Long-term memory wiki tool**
17. **Sub-agent spawning + parallel execution**
18. **Token analytics + cost tracking**

We work top-down. A feature can be partially deferred if a hit on a
lower-priority item is uncovered along the way — log it, move on.

---

## Open findings

| Id     | Severity | Area      | Summary                                                                 |
|--------|----------|-----------|-------------------------------------------------------------------------|
| INT-02 | 🟨 Rough  | tests     | 6× `tests/integration/test_llm_service_integration.py` fail with `litellm.AuthenticationError` because the OpenAI API key in `.env` is invalid. Pre-existing; needs either a mock harness or a CI-specific test key. |
| INT-03 | 🟨 Rough  | tests     | `tests/integration/test_ui_manifest_integration.py::test_manifest_endpoint_response_validates_with_extra_fields` fails because the enterprise plugin is loaded into the registry via INT-01's reset, while the test expects only its own `_Verbose` fixture plugin. The `isolated_registry` fixture isn't actually isolated from the enterprise plugin discovery. Pre-existing; the fixture needs a tighter scope. |

## Resolved findings

| Id    | Fix commit | Notes                                                                       |
|-------|-----------|------------------------------------------------------------------------------|
| WF-01 | c9cf60e   | Cron validated at save via `_next_cron_occurrence`; bad expressions return 400 |
| WF-02 | c9cf60e   | Dangling `depends_on` rejected at save (was: only at run)                   |
| WF-03 | c9cf60e   | Dependency cycles rejected at save (was: only at run)                       |
| WF-04 | c9cf60e   | Empty `steps` rejected at save                                              |
| WF-06 | c982749   | **Misdiagnosed.** The dispatcher in `application/scheduler_dispatcher.py` already routes to the right tenant via `get_tenant_context_runner()` — installed by `taskforce-enterprise.factory_extensions`. The user's `daily-orf-news` had no scheduler entry not because the framework was broken, but because the original save predated the v0.2.0 Windows-colon-in-job-id fix. Re-saving via the API now correctly persists the schedule job under `${WORK_DIR}/scheduler/jobs/workflow__daily-orf-news.json` with `tenant_id: browser_tenant`, and the dispatcher will resolve to the right tenant on cron tick. Cleaned up two leftover artefacts: the 0-byte NTFS-stream orphan in `browser-test-runtime/scheduler/jobs/` and the manually-written job in `tenants/browser_tenant/scheduler/jobs/` from my earlier python repro. |
| WF-05 | 194562b (framework) + enterprise 5fecc42 | New `set_webhook_workflow_resolver` override slot in the framework. On a local-tenant miss the auth-exempt webhook route asks the resolver "which tenant owns this path?", then re-runs lookup + signature verification + execute under that tenant's context via the existing `tenant_context_runner`. The enterprise plugin installs `FilesystemWebhookResolver`, which walks `${base_work_dir}/tenants/*/workflows/definitions/*.yaml`. Six new resolver tests on the enterprise side, three on the framework override-slot side. |
| INT-01 | (this session) | Wider scope than originally captured: 64 of 72 failing integration tests when enterprise is installed all share the same root cause — the auth middleware is loaded into the process-global plugin registry once with `auth.enabled=true` defaults, and stays there for every subsequent `create_app()` call regardless of plugin_config. New `tests/integration/conftest.py` patches `_load_plugin_config` to return an auth-disabled test config and resets the global plugin registry between tests so middleware doesn't accumulate. Also exposes an `enterprise_auth_token` fixture for tests that explicitly want to exercise the auth path. The remaining 8 failures (logged separately as INT-02 + INT-03) are unrelated to plugin/auth state. |

---

## Session log

Each session below = one feature audit. Append, don't rewrite.

### 2026-05-06 — Workflows runtime + UI (P0 #1)

**Scope:** API endpoints under `/api/v1/workflows/definitions` and
`/api/v1/workflows/webhooks/{path}`. Targeted CRUD, validation,
trigger types, tenant isolation, run-time semantics. UI surface not
re-exercised in this session — covered earlier when shipping v0.2.0.

**Setup:** Running enterprise browser-test API at 127.0.0.1:8070
(`browser_tenant`). Fresh JWT minted per session, 24h TTL.

**OK:**
- 🟩 GET list / get / 404 paths
- 🟩 422 on missing required fields
- 🟩 Tenant isolation: a token for `demo` tenant cannot list/get/delete
  workflows owned by `browser_tenant` (T19, T20, T21)
- 🟩 Re-saving with the same `workflow_id` overwrites idempotently (T11)
- 🟩 DELETE removes the YAML file from disk (T22 sequence)
- 🟩 Run-time validation catches dangling `depends_on` (400) and
  dependency cycles (400) (T10, T10b)
- 🟩 Schedule-job filename uses Windows-safe `workflow__<id>` (post-fix
  in v0.2.0), no NTFS alternate-data-stream crash

**Findings:** WF-01 through WF-06 (see table above). Detail:

- **WF-01** — Cron expression `"this is not cron"` accepted; route
  returned `scheduled_job_id` and persisted the job. The scheduler's
  cron parser will choke on its first tick. Should validate at
  save-time so the failure is immediate and visible.
- **WF-02 / WF-03** — Save path doesn't run the dependency-graph
  validation that the run path does. Same data flowing through different
  validation depths. Move the validation into `save_definition` (or a
  shared helper) so a broken graph never makes it onto disk.
- **WF-04** — Zero-step workflows are accepted and "run" with an empty
  step list. Probably best to reject at save with a 400 (a workflow
  with no steps has no semantics).
- **WF-05** — `POST /api/v1/workflows/webhooks/qa/open` returns 404
  even though the workflow exists. Webhooks are auth-exempt
  (`exempt_path_prefixes` includes `/api/v1/workflows/webhooks`), so
  the request has no tenant context. `find_webhook_workflow` queries
  `WorkflowRuntimeService`'s `_definition_store`, which under
  enterprise multi-tenancy is built per-call against the *current*
  tenant — for an auth-exempt request that's "default", which has no
  workflows. **Webhooks for non-default tenants are unreachable.**
- **WF-06** — Definitions land in
  `${WORK_DIR}/tenants/<tid>/workflows/definitions/...`, but the
  scheduler is a process-wide singleton constructed once with
  `work_dir=os.getenv("TASKFORCE_WORK_DIR", ".taskforce")`, so its
  jobs persist to `${WORK_DIR}/scheduler/jobs/...` (not tenant-scoped).
  Saving a schedule-triggered workflow as `browser_tenant` writes the
  YAML to the tenant subdir but the scheduler job to the framework
  root, and the loaded scheduler at startup only looks at the framework
  root. **Schedule-triggered workflows for non-default tenants never
  fire after an API restart.** Even within a single process the
  cron-tick dispatcher must propagate `tenant_id` from `ScheduleJob`
  into `WorkflowRuntimeService` before lookup, or it'll hit the wrong
  definition store.

**Fixes applied this session (WF-01…WF-04):**
- `WorkflowRuntimeService.save_definition` now calls a new
  `_validate_definition` helper that reuses the run-path's
  `_order_steps` for graph validation and the scheduler's
  `_next_cron_occurrence` for cron validation. Empty step lists are
  rejected. The route layer maps the resulting `ValueError` to a 400.
- Added 5 unit tests covering the new save-time validation paths.
- Older test cases that relied on the lax behaviour (empty `steps`
  for webhook-lookup tests, etc.) were updated with placeholder
  steps.

**Deferred to next session:** WF-05 and WF-06 both stem from the
same root cause — auth-exempt or process-wide entry points (webhook
URL, scheduler tick) lacking tenant context. They need a small
design decision (carry tenant in the webhook URL? per-tenant
schedulers? scheduler dispatcher sets tenant from `ScheduleJob`?)
before implementation. Capture the decision before writing the fix.
