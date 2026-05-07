# ADR-022: Multi-Tenant Enterprise Runtime

**Status:** Accepted — implementation 7/7 framework slices closed after post-review wiring fixes; container sandbox deferred
**Date:** 2026-05-02 · last verified end-to-end 2026-05-04
**Related:** ADR-003 (Enterprise Transformation), ADR-009 (Communication Gateway), ADR-011 (Unified Skills), ADR-016 (Persistent Agent Architecture), ADR-018 (ACP Protocol Support), ADR-020 (Wiki-Style Memory), ADR-021 (UI Plugin System)

## Status (post-iteration)

The original migration plan listed seven slices. Where each one
landed, with the closing commit references. The 2026-05-04 post-review
pass found and corrected additional wiring gaps in gateway/workflow
runtime DI after the first "all gaps closed" pass:

| Slice | Status | Closing commits (pytaskforce / taskforce-enterprise) |
|---|---|---|
| 1 — Tenant plumbing (TenantResolverProtocol + framework-wide `get_current_tenant_id`) | ✅ done | `c0ad93e` / `9f78614` |
| 2 — Postgres adapters (state, conversation, custom agents, admin routes) | ✅ done | iter-2 (`6081ae8`, `2278f82`, …) |
| 3 — Tenant-aware Gateway (`RecipientResolverProtocol`, `@agent_name` routing, per-tenant components, outbound `tenant_id`, `@workflow_name` chat trigger) | ✅ done after post-review wiring fix | `a6ac0e9`, `e316ef0`, `38eb5da` (G1), `9397fb7`, `eb77a8c` (G5) plus post-review fixes / `2cc8642` plus workflow lookup install |
| 4 — Workspace-scoping (`WorkspaceContextProtocol` + `tenants/${tid}/agents/${aid}/workspace/`) | ✅ done | iter-3 (`87ee255`, …) |
| 5 — Sandboxed tool execution (protocol seam + in-process default + multi-tenant warning) | 🟨 seam done, container backend deferred | `f17dcb8` / `d80b2af` (warning trigger) — see G12 below |
| 6 — Generalised scheduler / skills hot-reload / tenant-scoped ACP peers / cross-tenant authorizer / generalised `schedule` tool / skill write moved to enterprise | ✅ done | `87f846e`, `36fada6` (G4 framework) `25a78f6`, `95dd038` (G10) / `649b52d`, `87ee255`, `32c80d0`, `40017b5` |
| 7 — Workflow definitions (YAML + structured triggers + schedule auto-register + EXECUTE_WORKFLOW dispatcher + webhook trigger + HMAC verification + fan-out parallel + ACP-mediated steps) | ✅ done after post-review wiring fix | `f407a4b`, `960120a` (G3 schedule), `976771e` (G3b webhook), `4dd6169` (G3 wiring), `68f4e71` (G4 dispatcher), `29f6522` (G2 framework), `fb0df24` (G6 parallel), `719611d` (G7 ACP) plus post-review fixes / `386de73` (G2 enterprise) |

The full per-gap working file lives at
[`docs/adr-022-followups.md`](../adr-022-followups.md). Slice 5's
container-backed implementation is deliberately out of scope per the
2026-05-04 decision; the framework warns at startup when running
multi-tenant without a sandbox so the unsafe state is visible.

## Context

Today, Taskforce is a single-tenant runtime. The framework already
provides the building blocks for the experience we want — a unified
Communication Gateway (ADR-009), persistent agents (ADR-016), ACP
peer-to-peer messaging (ADR-018), wiki-style long-term memory
(ADR-020), a hot-loadable skills system (ADR-011), a scheduler that
runs jobs on behalf of the Butler, and a `taskforce-enterprise` plugin
that adds RBAC/Authz on top of the host process. But each of these
pieces was designed with the assumption that the runtime serves *one*
user (or one self-hosted operator), and the integration points between
them carry that assumption forward:

* `AgentRegistry`, `ConversationStore`, `WikiStore`, `SchedulerService`
  and the `gateway_sessions` directory are keyed by agent/session/job
  id, not by `(tenant_id, user_id)`. Two users on the same instance
  share state.
* The `CommunicationGateway` resolves an inbound Telegram/Teams
  message to a single agent profile per channel. There is no concept
  of "Tenant A's `accountant` agent" vs. "Tenant B's `accountant`
  agent", and no `@agent_name` routing inside a chat.
* The default `persistence.work_dir` is one shared `.taskforce/`
  folder on the host. Tools like `bash`, `python`, `shell`,
  `file_read`, `file_write` execute in the host process with full
  filesystem visibility — a malicious or misconfigured agent in
  tenant A can read tenant B's files (and the host's secrets).
* The `SchedulerService` and `FileJobStore` are wired into the Butler
  daemon. Other agent types cannot register their own scheduled jobs
  through a stable, tenant-scoped API.
* `SkillService` discovers skills from the filesystem at startup and
  on explicit refresh calls, but skill creation has no tenant scope
  and no live-reload contract.
* ACP peer registries are per-process. A peer is "reachable" to every
  agent in the runtime, regardless of tenant.
* `taskforce-enterprise` provides identity, JWT/API-key auth and a
  `PolicyEngine`, but its admin routes (`_users`, `_roles`,
  `_tenants`) are in-memory placeholders, and it does not yet carry
  `tenant_id` into the persistence/runtime layer of the host process.

The user has stated the target experience explicitly:

1. Multi-user / multi-tenant SaaS with self-service agent creation
   and chat-based interaction with one's own agents.
2. Agents communicate with each other via ACP — within a tenant, and
   (optionally) across tenants under explicit policy.
3. Each agent has its own workspace.
4. Agents learn over time (long-term memory).
5. Skills can be defined on-the-fly and become available without a
   restart.
6. Agents can run scheduled, recurring tasks.
7. Users can talk to their agents from external channels (Telegram,
   Teams, …).
8. Workflows can be defined where one or more agents collaborate on a
   task.

These are deliberately *user requirements*, not implementation
choices. They must be satisfied without breaking the single-tenant,
self-hosted use case that the framework supports today.

## Decision

Introduce **tenant** as a runtime concept *outside* the framework's
core, satisfied entirely by `taskforce-enterprise` via composition,
and reshape the seams so the requirements above can be satisfied
without leaking enterprise concerns into the OSS framework.

The guiding principle is explicit: **the framework's domain model and
its persistence/registry protocols must remain tenant-unaware.** The
core code shipped with `taskforce` does not know what a tenant is and
does not need to. The enterprise plugin makes a multi-tenant runtime
real by *composing* per-tenant instances of those protocols and
injecting them into the framework's existing seams.

The decision has five parts:

### 1. Tenant Concerns Stay Out of Core

The protocols in `src/taskforce/core/interfaces/` (`ConversationManagerProtocol`,
`StateManagerProtocol`, `WikiStoreProtocol`, `SkillRegistryProtocol`,
`AgentStateProtocol`, the scheduler's job store, …) keep their current
signatures. They do **not** gain a `tenant_id` parameter. The file-based
adapters that ship with the framework (`FileConversationStore`,
`FileStateManager`, `FileAgentRegistry`, …) keep their current behaviour
and current single-tenant file layout.

Multi-tenancy is realised by two patterns, both implemented entirely in
`taskforce-enterprise`:

**Pattern A — Per-Tenant Adapter Instances** (used for file-based stores)

The plugin instantiates one `FileConversationStore`, one `FileStateManager`,
one `FileWikiStore`, etc. *per tenant*, each rooted at
`${WORK_DIR}/tenants/${tenant_id}/...`. A tiny per-tenant cache
(`TenantScopedStoreFactory.for_tenant(tenant_id)`) returns the right
instance. Each instance is a plain `ConversationManagerProtocol` from the
framework's perspective — there is no new protocol surface.

**Iter-2 addendum — per-user buckets within a tenant.**
Iter-1 made tenants disjoint. Iter-2 splits the per-tenant directory
into a *shared* part and a *per-user* part:

| Bucket | Scope | Path |
|---|---|---|
| State, conversations, gateway sessions, agent state, wiki memory, scheduler jobs, writable skill root | per-user | `${WORK_DIR}/tenants/${tid}/users/${uid}/...` |
| Custom agent definitions | tenant-shared | `${WORK_DIR}/tenants/${tid}/custom/...` |
| Workflow definitions + checkpoints | tenant-shared | `${WORK_DIR}/tenants/${tid}/workflows/...` |

The user_id is resolved by a parallel `UserResolverProtocol`
(`ContextVarUserResolver` reads the same auth ContextVar that
`UserContext` is written to). When no user is in scope (single-user
CLI, butler daemon, system jobs), the resolver returns `_default` and
stores land at `${WORK_DIR}/tenants/${tid}/users/_default/...`.

`migrate_legacy_layout` runs in two passes: pre-tenancy directories
are first moved under `tenants/default/`, then any per-user buckets
sitting tenant-flat are moved into `users/_default/`. Both passes are
idempotent.

**Caveat — Postgres mode.** Postgres runtime stores currently filter
by `tenant_id` only. Until per-user filtering is added (separate
follow-up tracked in `docs/adr-022-followups.md`), users within a
tenant on a Postgres deployment share their runtime data. The factory
emits a one-shot warning (`enterprise.persistence.postgres_per_user_unsupported`)
so operators are not caught off guard.

**Pattern B — Tenant-Filtered Multi-Tenant Adapter** (used for SQL/Postgres stores)

For row-level-secure stores (Postgres in Iter ≥ 2), the plugin ships a
single adapter that implements `ConversationManagerProtocol` and reads
the current tenant from a request-scoped `ContextVar` set by
`AuthMiddleware`. Every query carries a `WHERE tenant_id = …` clause.
The framework still sees a plain protocol implementation.

Both patterns share one prerequisite from the framework: **the
`AgentFactory` must allow late binding of stores per agent build**, not
just at construction time. We add a thin **store-provider hook** to
`AgentFactory` (a `Callable[[], ConversationManagerProtocol]` instead
of a stored instance, see Section 3 below). The framework's default
provider returns a plain singleton — exactly today's behaviour. The
enterprise plugin replaces it with a provider that consults the
current tenant.

`TenantContext`, `UserContext`, `TenantResolverProtocol` and
`AuthMiddleware` all live in `taskforce-enterprise`. The framework
does **not** import any of them.

### 2. `tenant_id` as a first-class key (in the enterprise plugin)

Within `taskforce-enterprise`, tenant is a first-class concept:

* `TenantContext` is the request-scoped carrier (already exists today,
  hung off `ContextVar`s set by `AuthMiddleware`).
* The plugin's per-tenant adapter factories key on `tenant_id`.
* Postgres adapters use `tenant_id` as a mandatory column with a
  composite index and row-level-security policies.
* The plugin's admin routes, audit log, policy engine and gateway
  recipient resolver all know about tenants.

This is by design: tenancy *is* an enterprise feature; it should be
visible and explicit *inside* the enterprise plugin and invisible
*outside* it.

### 3. Late-Bound Store Providers in `AgentFactory`

The single, minimal change in the framework is in `application/factory.py`.
Today the factory holds direct store instances:

```python
self._conversation_store: ConversationManagerProtocol = ...
self._state_manager: StateManagerProtocol = ...
```

These become provider callables:

```python
self._conversation_store_provider: Callable[[], ConversationManagerProtocol] = ...
self._state_manager_provider: Callable[[], StateManagerProtocol] = ...
```

The framework's default providers return a plain singleton — semantically
identical to today. The enterprise plugin's
`taskforce.factory_extensions.enterprise` entry point overwrites the
providers with closures that resolve the current tenant from
`TenantContext` and return the per-tenant instance.

This is the only framework-side change needed for multi-tenancy. It is
purely additive, breaks no callers, and adds no `tenant` vocabulary to
the framework. Single-tenant builds (`taskforce` without
`taskforce-enterprise`) are bit-for-bit identical to today.

### 4. Tenant-aware Communication Gateway

The Gateway gains two new responsibilities:

* **Recipient → tenant/user mapping.** A `RecipientResolverProtocol`
  takes a channel-specific identity (Telegram `user_id`, Teams `aad
  oid`, REST `Authorization` header, …) and returns a
  `(tenant_id, user_id)` pair. Unmapped recipients are rejected with
  an audited deny. This subsumes the current `RecipientRegistry` and
  is the single seam where channel auth meets the enterprise identity
  provider.
* **`@agent_name` routing inside a tenant.** Inbound messages can
  address one of several agents owned by the resolved user (`@accountant
  please file last month`). Routing falls back to a per-user *default
  agent* if no `@` prefix is present. Cross-tenant `@` routing is
  rejected at the gateway layer.

Outbound senders, the proactive `send_notification` tool, and the
broadcast endpoint all receive `tenant_id` and use it for both
recipient lookup and audit.

### 5. Per-agent isolated workspace

Each agent has a workspace at
`${WORK_DIR}/tenants/${tenant_id}/agents/${agent_id}/workspace/`.
This is the only path the agent's filesystem and shell tools see.
Two separate concerns are addressed:

* **Path scoping** is enforced by passing the workspace root to
  `BaseTool` subclasses through a new `WorkspaceContextProtocol`.
  Tools that take a path argument resolve it relative to that root
  and reject `..` traversal. This is cheap to implement and covers
  the cooperative case (well-behaved tools, misconfiguration).
* **Process/syscall isolation** is *not* enforced by path scoping. A
  new `SandboxedExecutorProtocol` defines a contract for executing
  the dangerous tools (`bash`, `shell`, `powershell`, `python`) in a
  sandbox. The framework ships an in-process executor (today's
  behaviour, fail-open warning when the enterprise plugin is not
  installed); the enterprise add-on ships a container-backed
  implementation that mounts only the agent's workspace, drops
  network capabilities by default, and applies CPU/memory/wall-clock
  limits. The two contracts are intentionally separated: a
  self-hosted operator can opt into path scoping without paying the
  container cost, and an enterprise operator can require both.

This split is the security-critical point of this ADR. We make the
unsafe default *visibly* unsafe (a startup warning when no
sandboxed executor is wired and the runtime is configured for
multi-tenant mode) rather than silently inheriting today's "trust
the host" behaviour.

### 6. Tenant-scoped runtime services

Three runtime services are generalised so any agent (not just the
Butler) can use them, and so the resulting state is tenant-scoped:

* **Scheduler.** `SchedulerProtocol`'s job-store contract grows
  `tenant_id` and `agent_id`. A new `agent.scheduler` view (or a
  `schedule` tool generalised beyond Butler) lets any agent register
  recurring jobs that run as that agent, in that tenant. Policy
  decides who is allowed to schedule what (`schedule:create`).
* **Skills hot-reload.** `SkillService` grows a filesystem watcher
  (in addition to the existing manual-refresh path) so that a skill
  written into the tenant's skills directory becomes available
  without restart. A new admin/API path
  `POST /api/v1/skills` accepts a `SKILL.md` payload, persists it
  under the caller's tenant, and triggers the watcher. Skill
  resolution at agent runtime first searches the tenant's skills,
  then falls back to bundled skills.
* **ACP peers.** The peer registry is partitioned by tenant.
  Cross-tenant ACP calls require an explicit `acp:peer:cross_tenant`
  permission and are routed through a gateway that re-authenticates
  on every call. Within a tenant, peer discovery is automatic for
  agents that opt in via their profile.

### 7. Workflows as first-class definitions

Today, "multiple agents collaborating" is expressed via the
`call_agents_parallel` tool, sub-agent spawning, or ACP — each as
*code/tool calls* inside a single agent's reasoning loop. We add a
top-level `WorkflowDefinition` (YAML, persisted per tenant) that
names the participating agents, the trigger (chat, schedule, event,
webhook), and the orchestration topology (sequence / fan-out + join /
ACP-mediated). The existing `workflow_runtime_service` (ADR-014 HITL)
is extended to execute these definitions; the existing tool-based
patterns continue to work and are the implementation primitive that
the workflow runtime composes.

### Boundary between `taskforce` and `taskforce-enterprise`

The framework remains tenant-unaware. The enterprise plugin owns the
tenant concept end-to-end and injects per-tenant behaviour through
existing seams.

| Concern | `taskforce` (framework) | `taskforce-enterprise` (plugin) |
|---|---|---|
| Tenant model | None — framework has no `tenant` vocabulary | `TenantContext`, `UserContext`, `TenantResolverProtocol`, ContextVars |
| Persistence protocols | Unchanged signatures; existing protocols, existing file adapters | Per-tenant adapter factory (Pattern A) + multi-tenant Postgres adapters with RLS (Pattern B) |
| `AgentFactory` | New: store-provider hook (callables instead of stored instances) — purely additive | Replaces providers with tenant-resolving closures via `factory_extensions` entry point |
| Authorization | `PolicyEngineProtocol` interface only | `PolicyEngine` (local) or `AuthzPolicyEngine` (remote) |
| Tool execution | `SandboxedExecutorProtocol`, in-process default + warning | Container-backed sandboxed executor (Docker/gVisor) |
| Gateway | Channel adapters, `RecipientResolverProtocol` interface only | Channel auth glue, recipient ↔ user/tenant mapping, `@agent` routing, broadcast policy |
| Skills/Scheduler/ACP | Hot-reload watcher + per-instance scoping (existing protocols), peer registry interface | Per-tenant skill/job/peer instances, cross-tenant policy, admin UI, audit |
| Workflows | `WorkflowDefinition` runtime, REST CRUD, run/webhook endpoints, **authoring UI** (list, editor, run, webhook/schedule surfacing) | Tenant-scoping over the same UI, RBAC on CRUD/run, role-gated approval steps, audit |

The plugin does not fork the framework's domain model; it composes
per-tenant instances of the framework's existing protocols (Pattern A)
or implements multi-tenant variants of those same protocols (Pattern B).
The framework remains usable standalone in single-tenant / self-hosted
mode and is bit-for-bit identical to today when the enterprise plugin is
not installed.

## Consequences

**Positive**

* All seven user requirements have a clear home in the architecture
  and a clear delineation between OSS framework and enterprise
  plugin.
* `tenant_id` becomes a load-bearing key everywhere it matters; the
  current "everyone shares `.taskforce/`" failure mode goes away by
  construction once the file adapters use the new layout.
* Sandboxed tool execution gets a real interface, which is the only
  way the multi-tenant SaaS use case can be operated safely. The
  in-process default keeps the OSS experience simple.
* The Butler's event-source / scheduler / rule-engine machinery
  (ADR-010) becomes the *general* runtime substrate for any agent,
  not Butler-only.
* Skills become a SaaS feature: a user can create a skill from chat
  or UI and immediately use it, without operator intervention.

**Negative / risks**

* This is a wide, cross-cutting refactor. Every persistence-layer
  Protocol gains a parameter; every adapter and call site needs an
  update. We mitigate by (a) introducing a `default` tenant resolver
  so the change is mechanically backward-compatible for the
  framework-only build, and (b) sequencing the work as additive
  slices (see "Migration plan" below).
* The split between path-scoped and container-sandboxed tool
  execution is subtle; misconfiguration ("I'm multi-tenant but I
  forgot to install the sandbox") would be unsafe. We mitigate by
  emitting a hard startup warning and by failing closed when the
  enterprise plugin advertises multi-tenant mode without a sandboxed
  executor.
* Workflows-as-data is a new authoring surface; it competes with
  "just write Python" and with the existing `call_agents_parallel`
  /sub-agent pattern. We keep both: workflows are the SaaS-friendly
  surface, sub-agent tools remain the implementation primitive.
* Cross-tenant ACP introduces a new attack surface. We default it
  off and require an explicit permission + per-call re-auth.

**Neutral / explicitly out of scope**

* This ADR does *not* prescribe a billing model, a UI design, or a
  specific container runtime. Those are implementation choices for
  the enterprise plugin.
* This ADR does *not* change the existing single-tenant CLI / API
  user experience. `taskforce run mission "..."` keeps working
  against the `default` tenant.
* Memory remains wiki-style per ADR-020; we only add tenant scoping
  to the wiki store.

## Migration plan (sketch)

The work is sequenced so each slice is independently shippable and
backward-compatible:

1. **Tenant plumbing.** Add `TenantContext` resolution to the
   framework, plumb `tenant_id` through the persistence Protocols
   with a `default` tenant fallback. No behaviour change for
   existing users.
2. **Postgres adapters in `taskforce-enterprise`.** Implement
   tenant-isolated adapters for `ConversationStore`,
   `AgentRegistry`, `AgentStateStore`, `WikiStore`,
   `SkillRegistry`. Replace the in-memory admin-route stores with
   these.
3. **Tenant-aware Gateway.** `RecipientResolverProtocol`,
   `@agent_name` routing, recipient ↔ user mapping in the enterprise
   plugin.
4. **Per-agent workspace + path scoping.** New layout under
   `tenants/${tenant_id}/agents/${agent_id}/workspace/`,
   `WorkspaceContextProtocol` enforced by `BaseTool`.
5. **Sandboxed tool execution.** `SandboxedExecutorProtocol` in
   framework, container-backed implementation in enterprise.
6. **Generalised scheduler + skills hot-reload + tenant-scoped ACP
   peers.** Each builds on (1) and is independently shippable.
7. **Workflow definitions.** Last, because it composes everything
   above.

Each slice gets its own follow-up ADR if it introduces non-obvious
design decisions; this ADR is the umbrella.

## Open questions

* Where exactly does the `TenantResolverProtocol` live —
  `core/interfaces/identity.py` (new) or extending the existing
  `core/interfaces/identity_stubs.py`? Decision deferred to slice 1.
* For the sandboxed executor: do we standardise on a single backend
  (Docker) or define a backend-agnostic contract that gVisor /
  Firecracker / Kata can plug into? Likely the latter; decision
  deferred to slice 5.
* Cross-tenant ACP: is it a feature we ship at all, or do we keep
  ACP strictly intra-tenant in v1 and revisit? Decision deferred;
  default-off in any case.
