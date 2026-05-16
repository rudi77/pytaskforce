---
feature: multi-tenant
status: enterprise
since: 2026-05-02
last_verified: 2026-05-16
owner: rudi77
adr: ADR-022
---

# Multi-Tenant Runtime — Tenant + User Scoping Seams

The framework itself is single-tenant: every persistence and runtime
adapter that ships with `taskforce` writes to one flat `${WORK_DIR}/...`
tree. Multi-tenancy is realised by `taskforce-enterprise`, a separate
plugin package, which installs per-request `(tenant_id, user_id)`
resolution and replaces ~25 framework store builders with tenant-scoped
implementations through a single registry of override hooks. This spec
documents the **framework contract** — the seams the plugin plugs into,
the path layout it produces, and the invariants the framework promises
to preserve. The enterprise plugin's own surface (admin UI, RBAC
policy, Postgres adapters) is documented in its own repo.

## Capabilities (what the user can do)

- run `taskforce` standalone with no override installed and observe bit-for-bit single-tenant behaviour (`tenant_id = "default"`, no user filter)
- install the enterprise plugin to get per-tenant + per-user scoping of every persistent store without forking framework code
- ask "what tenant/user is this request for?" from any framework call site via `get_current_tenant_id()` / `get_current_user_id()` without importing anything tenant-aware
- run background jobs (scheduler, webhooks) inside a tenant context via the installed tenant-context runner
- partition ACP peers per tenant and gate cross-tenant calls through an installable authorizer
- be warned at startup when a multi-tenant runtime is active but no sandboxed executor is wired

## Invariants (what must always be true)

- The framework's domain protocols (`StateManagerProtocol`, `ConversationManagerProtocol`, `WikiStoreProtocol`, …) carry no `tenant_id` or `user_id` parameter; tenancy is realised by *which instance* of the adapter is returned, never by parameter on the call.
- With no overrides installed, every store builder returns the framework's flat single-tenant default — installing the plugin must be the *only* thing that changes runtime layout.
- `get_current_tenant_id()` returns `"default"` when no resolver is installed; a resolver that raises is caught and falls back to `"default"` (a buggy plugin must not break the framework).
- `get_current_user_id()` returns `None` when no resolver is installed; framework adapters that see `None` must treat it as "no user filter applies", not as an explicit user.
- Per-user file layout (when the plugin routes paths) is `${WORK_DIR}/tenants/${tid}/users/${uid}/...` for per-user buckets and `${WORK_DIR}/tenants/${tid}/{custom,workflows}/...` for tenant-shared buckets; the framework writes nothing under this layout itself.
- Overrides are resolved on every builder call (not cached), so installs and uninstalls take effect immediately without restarting workers.
- The override slots are module-level globals and not thread-safe; the plugin must install them once at bootstrap before worker threads start.
- `clear_infrastructure_overrides()` resets every slot — test teardown can rely on it to prevent leakage across tests.
- The framework never imports `taskforce_enterprise`, `TenantContext`, or `UserContext`; the only types that cross the boundary are the protocol stubs in `core/interfaces/identity_stubs.py`.
- Running multi-tenant without `set_sandboxed_executor(...)` is unsafe but allowed; the framework emits a one-shot `RuntimeWarning` so the unsafe state is visible in logs.

## Extension points (for plugins / enterprise / external use)

All hooks live in `taskforce.application.infrastructure_overrides`. The
plugin calls each `set_*` once at bootstrap; the framework reads via
the matching `get_*` at builder call time. Returning `None` (or never
installing) keeps the framework default.

### Identity resolvers (the root seam)

- `set_tenant_resolver(() -> str)` — answers "what tenant is this request for?". `get_current_tenant_id()` calls this; default returns `"default"`.
- `set_user_resolver(() -> str | None)` — same shape for user; `get_current_user_id()` returns `None` when unset.
- `set_tenant_context_runner(async (tenant_id, async fn) -> Any)` — lets background callbacks (scheduler events, webhook routes) execute work *inside* a tenant context they didn't enter through HTTP auth.
- `set_acp_tenant_id_provider(() -> str)` — separate slot for the ACP runtime (constructor-stored independently from the framework-wide resolver).

### Per-tenant / per-user store overrides

Each accepts a `Callable[[work_dir], <protocol impl>]` (or zero-arg
where noted) and must return an object satisfying the matching
protocol from `core/interfaces/`. Installed once; consulted every
builder call so the plugin can re-resolve per request.

- `set_agent_registry_override` — custom-agent registry (tenant-shared bucket).
- `set_deployment_manifest_override` — per-tenant visible-agents allowlist; beats both `VISIBLE_AGENTS` settings and `deployment.yaml`.
- `set_settings_store_override` — replace the file-based Fernet-encrypted store with a tenant-scoped backend (see `settings-store.md`).
- `set_project_store_override` — tenant-scope the CoWork project registry (see `cowork.md`).
- `set_state_manager_override` — per-user session state.
- `set_conversation_store_override` — per-user conversation history.
- `set_agent_state_override` — per-user singleton agent state (ADR-016).
- `set_wiki_store_override` — per-user wiki memory (ADR-020).
- `set_token_store_override` — per-user OAuth token store (zero-arg; per-user resolution lives inside the plugin's factory).
- `set_workflow_definition_store_override` / `set_workflow_checkpoint_store_override` — tenant-shared workflow definitions, per-user checkpoints (ADR-014-hitl).
- `set_experience_store_override` — per-user session experience traces (issue #196).
- `set_standing_goal_store_override` — per-user standing goals (ADR-024); sharing across users would fire someone else's weekly summary.
- `set_runtime_checkpoint_store_override` — per-session checkpoint store inside `build_runtime_tracker`.
- `set_pending_channel_question_store_override` — per-user outstanding `ask_user` questions.
- `set_tool_result_store_override` — per-user tool result cache; caching A's `python` output and serving it to B is a privacy leak even if args match.
- `set_butler_state_dir_override` — per-user butler tool state directory (gmail seen ids, calendar last-check); consulted at write time so a process-shared tool can still route per-user.
- `set_sub_agent_result_dir_override` — per-user `ParallelAgentTool` result directory; consulted at write time.
- `set_upload_storage_dir_override` — per-user `FileStorage` root (each scope gets its own SQLite index).

### Gateway hooks (channel layer; see also `gateway.md`)

- `set_gateway_components_override` — replace the whole gateway components bundle.
- `set_recipient_resolver_override` — channel identity → `(tenant_id, user_id)` mapping.
- `set_agent_lookup_override` — `@agent_name` mention resolution inside the resolved tenant.
- `set_workflow_lookup_override` — `@workflow_name` chat trigger.
- `set_channel_link_registry_override` — back the `/link <code>` pairing registry with a tenant-scoped store (issue #162).
- `set_webhook_workflow_resolver(async path → tenant_id)` — for the auth-exempt webhook route, lets it discover which tenant owns a workflow path on a local miss.

### Policy / runtime hooks

- `set_cross_tenant_acp_authorizer((caller_tid, peer_tid, peer) -> bool)` — ADR-022 §6 gate; default allows when `allow_cross_tenant=True` on the peer.
- `set_sandboxed_executor(SandboxedExecutorProtocol)` — container-backed executor for `bash` / `shell` / `python`; absent means in-process (unsafe in multi-tenant; the framework warns via `warn_if_multi_tenant_without_sandbox()`).
- `set_mission_lifecycle_hook(MissionLifecycleHookProtocol)` — observe mission start / complete (typically wired to AuditEvents in the plugin).
- `set_approval_service(ApprovalServiceProtocol)` — gate `requires_approval` tools (see `approval-gating.md`).
- `set_approval_bypass_override(list[str])` — tenant-level approval bypass; UNION-merged with per-agent `agent.approval_bypass_tools`.
- `set_workspace_context_provider(() -> WorkspaceContextProtocol | None)` — per-call workspace root for path-aware tools (`file_read`, `file_write`, `edit`); rejects `..` traversal at the tool layer.

### Identity protocol stubs (`core/interfaces/identity_stubs.py`)

- `TenantContextProtocol`, `UserContextProtocol`, `IdentityProviderProtocol`, `PolicyEngineProtocol`, `TenantResolverProtocol` — runtime-checkable minimal shapes the framework uses for type annotations without importing the enterprise plugin. `AnonymousUser` and `DefaultTenant` are the fallback singletons when no plugin is installed.

## Tests (must exist and pass)

- spec("multi-tenant.no_overrides_returns_default_tenant")
- spec("multi-tenant.no_overrides_returns_none_user")
- spec("multi-tenant.tenant_resolver_exception_falls_back_to_default")
- spec("multi-tenant.user_resolver_exception_falls_back_to_none")
- spec("multi-tenant.clear_infrastructure_overrides_resets_every_slot")
- spec("multi-tenant.override_resolved_per_call_not_cached")
- spec("multi-tenant.multi_tenant_without_sandbox_warns_once")
- spec("multi-tenant.framework_has_no_taskforce_enterprise_import")
- spec("multi-tenant.identity_stubs_are_runtime_checkable")

## Known gaps

- **`HTTPException.detail` is serialised as-is** by `taskforce_http_exception_handler` when `X-Taskforce-Error: 1` is set. In a multi-tenant deployment a route that builds a `detail` dict with stack traces, internal paths, or other tenant data leaks it to the client. Tracked in #289.
- **Slice 5 container sandbox is deferred.** The framework ships only the in-process default + startup warning; running multi-tenant SaaS today requires the operator to either accept host-level tool visibility or wire their own `SandboxedExecutorProtocol`.
- **Override slots are not thread-safe.** Installing a hook after worker threads start is undefined behaviour. The framework documents this but does not enforce it.
- **The framework cannot detect "multi-tenant runtime"** beyond "tenant resolver is installed". An operator who installs a resolver returning `"default"` is treated as single-tenant by the sandbox warning, even if they intend otherwise.
- **Multi-tenant gap reclassification.** A shipped multi-tenant feature that still behaves single-tenant is a *bug* against this spec (e.g. #226 wiki tool ignoring `set_wiki_store_override`, #228 multi-bot per user), not a new feature. The v0.2.0 feature freeze does not cover these gaps.
- **No backend `@pytest.mark.spec` markers exist yet** — Tests section above asserts the target, not current state.

## Cross-references

- adr: ADR-022 (Multi-Tenant Enterprise Runtime — primary design)
- adr: ADR-003 (Enterprise Transformation — predecessor)
- related_spec: settings-store.md (uses `set_settings_store_override`)
- related_spec: cowork.md (uses `set_project_store_override`)
- related_spec: gateway.md (uses recipient / agent / workflow / channel-link override hooks)
- related_spec: standing-goals.md (uses `set_standing_goal_store_override`)
- related_spec: wiki-memory.md (uses `set_wiki_store_override`)
- related_spec: workflows.md (uses workflow store + webhook resolver hooks)
- related_spec: approval-gating.md (uses `set_approval_service` + bypass override)
- related_spec: auth.md (uses `set_token_store_override`)
- docs: docs/features/enterprise.md (integration surface overview)
- docs: docs/adr-022-followups.md (per-gap working file)
