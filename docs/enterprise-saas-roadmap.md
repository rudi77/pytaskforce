# Enterprise SaaS Roadmap

**Status:** Active
**Last Updated:** 2026-05-02
**Owner:** rudi77
**Reference ADR:** [ADR-022 — Multi-Tenant Enterprise Runtime](adr/adr-022-multi-tenant-enterprise-runtime.md)

This roadmap implements ADR-022 in **value-driven, independently shippable
iterations**. Each iteration gets its own feature branch, must pass tests +
code review, and is merged to `main` before the next iteration starts.

A core architectural principle (locked in by ADR-022): **the framework
stays tenant-unaware**. All multi-tenant behaviour lives in
`taskforce-enterprise` and is injected via `factory_extensions`,
`middleware`, and `routers` entry points. Most iterations therefore ship
work in **two repos in parallel**:

- `pytaskforce/` — minimal, additive seams (framework hooks, new optional
  protocols, new middleware contracts). Tenant vocabulary is forbidden.
- `taskforce-enterprise/` — the real tenant logic, per-tenant adapter
  factories, Postgres adapters, JWT auth, admin stores, recipient
  mapping, sandboxing, etc.

Each iteration's plan therefore has up to two story documents — one per
repo — and a single feature branch in each repo.

---

## North Star

A multi-tenant SaaS where users can create their own agents, talk to them
from chat (web, Telegram, Teams), have those agents collaborate via ACP,
remember things across sessions, run on schedule, and gain new skills
on-the-fly — with enforced authorization on user, agent and tool level.

## Beta Acceptance (the bar for "we have a product")

> **Rudi** logs into `taskforce.cloud`, sees his `accountant` agent, writes
> "wie viel Umsatz hatte ich im April" in the web chat, gets an answer.
> In parallel, **Maria** logs in, sees her own (or empty) agent list, and
> **does not** see Rudi's agent or his data.

Anything not directly required for this is post-Beta.

---

## Iteration Overview

| #   | Iteration                                | Goal                                                       | Effort | Repos        | Status   |
|-----|------------------------------------------|------------------------------------------------------------|--------|--------------|----------|
| 1   | Store-Provider Hook + Per-Tenant Stores  | Late-bind stores in `AgentFactory`; per-tenant file stores in plugin | 4-6d   | both         | Framework: **In Review**, Plugin: Planned |
| 2   | Real Users (Postgres-backed admin)       | JWT login + Postgres-backed users/tenants/roles            | 4-6d   | enterprise   | Planned  |
| 3   | Web-Chat End-to-End                      | Authenticated web chat reaches user's default agent        | 3-5d   | both         | Framework: **In Review**, Plugin: Planned |
| ⭐  | **Beta milestone**                       | The two-user journey runs end-to-end                       | —      | merge → main | Beta     |
| 4   | Telegram per User                        | Per-user Telegram identity → tenant resolution             | 2-3d   | enterprise   | Planned  |
| 5   | Tool Sandboxing (path scoping)           | Tools can't escape the agent workspace                     | 4-5d   | both         | Planned  |
| 6   | Tool Sandboxing (container exec)         | `bash`/`python`/`shell` run in containers per tenant       | 1-2w   | both         | Planned  |
| ⭐  | **Public-Beta milestone**                | Safe to put real external users on the platform            | —      | merge → main | Public Beta |
| 7   | Skills Hot-Reload + Skill Authoring API  | Users create/edit skills from chat or UI, no restart       | 1w     | both         | Planned  |
| 8   | Generalized Scheduler                    | Any agent can register recurring jobs (not just Butler)    | 1w     | both         | Planned  |
| 9   | Tenant-Scoped ACP Peers                  | Intra-tenant ACP discovery + auth                          | 1w     | enterprise   | Planned  |
| 10  | Workflow Definitions                     | YAML-defined multi-agent workflows as first-class entities | 2w     | both         | Planned  |
| 11  | Tool-Level Authorization                 | Per-user/per-agent allow-list of tools, enforced           | 1w     | enterprise   | Planned  |
| 12  | Long-Term Memory Tenant-Scoping          | Wiki + State + Heartbeats per tenant (Pattern A)           | 1w     | enterprise   | Planned  |
| ⭐  | **GA milestone**                         | Full ADR-022 surface, all 7 user requirements              | —      | merge → main | GA       |

**Total estimated effort to Beta:** ~2-3 weeks (Iterations 1-3).
**Total estimated effort to GA:** ~3-4 months (Iterations 1-12).

---

## Repo Workflow per Iteration

For iterations that touch both repos:

1. **Plan**: write a story document in *each* repo
   - `pytaskforce/docs/stories/iteration-NN-<slug>-framework.md`
   - `taskforce-enterprise/docs/stories/iteration-NN-<slug>-plugin.md`
2. **Branch**: in each repo, `git switch -c feat/iter-NN-<slug>` from `main`.
3. **Order**: framework PR first (the additive hook). Plugin PR depends
   on the framework one being merged or pinned via path-dep / git-rev.
4. **Implement**: small commits in both branches in parallel; framework
   commits should *never* mention `tenant`.
5. **Test**: framework tests run in single-tenant mode against the new
   hook (default provider). Plugin tests cover per-tenant behaviour.
6. **Lint/Format/Type-check**: `uv run ruff`, `uv run black`, `uv run mypy`
   green in both repos.
7. **Docs**: update `CLAUDE.md` in each repo as needed; update the
   matching story document's status.
8. **PR**: framework PR first. Plugin PR opens with a link to the merged
   framework PR (or a temporary path-dep for review).
9. **Review**: independent code review per repo. Run `/ultrareview` on
   each PR.
10. **Merge**: framework first, then plugin.
11. **Roll forward**: update this roadmap (status → Done, link to both
    PRs), then start the next iteration.

For iterations that touch a single repo: same workflow without the
cross-repo coordination steps.

---

## Iteration 1 — Store-Provider Hook + Per-Tenant Stores

**Why first?** Without late-bound store providers in `AgentFactory`,
the enterprise plugin cannot inject per-tenant store instances. This
iteration delivers the *only* framework change that's needed for the
entire multi-tenant project. After this, almost everything else lives
in the enterprise plugin.

**Framework side (additive, tenant-vocabulary-free):**
- `AgentFactory` switches from holding store instances to holding
  store-provider callables (`Callable[[], Protocol]`).
- A new optional `factory_extensions` API lets a plugin replace
  individual providers without forking the factory.
- Default providers preserve current behaviour exactly.
- Story: [`docs/stories/iteration-01-store-provider-hook-framework.md`](stories/iteration-01-store-provider-hook-framework.md)

**Plugin side (the actual tenant logic):**
- New `TenantScopedStoreFactory` that builds per-tenant
  `FileConversationStore` / `FileAgentRegistry` instances rooted at
  `${WORK_DIR}/tenants/${tenant_id}/...`.
- New `factory_extensions.tenant_aware_providers` entry point that
  installs tenant-resolving providers into the framework's
  `AgentFactory`.
- A `TenantResolverProtocol` (lives entirely in the plugin) backed by
  `TenantContext` ContextVars from the existing `AuthMiddleware`.
- Story: lives in `taskforce-enterprise/docs/stories/iteration-01-tenant-scoped-stores-plugin.md`

**Acceptance:**
- Existing single-tenant tests in `pytaskforce` pass without change.
- New plugin test: two tenants, both call `get_or_create("web", "user-1")`,
  end up with disjoint conversations on disk under `tenants/A/` and
  `tenants/B/`.
- Plugin smoke test confirms the framework's `AgentFactory` happily
  uses the injected providers without knowing they're tenant-aware.

---

## Iteration 2 — Real Users (Postgres-backed admin)

**Repo:** `taskforce-enterprise` only.
**Why?** The plugin's existing `_users`/`_tenants`/`_roles` in-memory
dicts are placeholders. We can't have two real users until that's a
real store. JWT login is the missing user-facing piece.

**Plugin work:**
- Postgres adapter for users/tenants/roles (Alembic migration).
- `POST /api/v1/auth/login` endpoint issuing JWTs with
  `tenant_id`, `user_id`, `roles` claims.
- `taskforce-enterprise admin bootstrap` CLI that seeds a `default`
  tenant + admin user from env vars.
- AuthMiddleware integration tests against real Postgres.

**Acceptance:**
- A user authenticated as `tenant_a:rudi` can hit a protected route;
  a `tenant_b:maria` JWT to a `tenant_a` resource is denied with audit.
- Story: `taskforce-enterprise/docs/stories/iteration-02-postgres-auth.md`

---

## Iteration 3 — Web-Chat End-to-End

**Repos:** both.
**Why?** This iteration finally proves the user journey end-to-end.
Iter 1 + 2 have no user-visible effect on their own.

**Framework side:**
- A `RecipientResolverProtocol` interface in the gateway. Default
  implementation: pass-through (assumes the channel id *is* the user
  id). Story: `pytaskforce/docs/stories/iteration-03-recipient-resolver-framework.md`
- A `default_agent_id` concept on the gateway routing path
  (still tenant-unaware — the per-user mapping is enterprise-side).

**Plugin side:**
- Real `RecipientResolver` that consumes the JWT auth context and
  resolves `(tenant_id, user_id)` from the request.
- `users.default_agent_id` column + admin endpoints to set it.
- Web-UI wiring: login page, agent picker, chat screen.
- E2E test: Playwright drives the two-user journey.
- Story: `taskforce-enterprise/docs/stories/iteration-03-web-chat-plugin.md`

**Acceptance:** the Beta user journey runs end-to-end.

---

## Iterations 4-12 — design-first, plan just-in-time

Detailed plans for these will be written **just before** the iteration
starts, following the same dual-repo pattern. Writing them all now would
be premature — what we learn in Iter 1-3 will reshape later iterations.
The roadmap row for each iteration above is a placeholder that will be
expanded into a story document at iteration-start time.

---

## Out-of-Scope Decisions (locked in by ADR-022, restated here)

- **Framework stays tenant-unaware.** Reviewers must reject any framework
  PR that introduces `tenant_id`, `tenant`, or any tenant vocabulary into
  `pytaskforce/src/taskforce/`. The only exception is *interface*
  protocols that the enterprise plugin needs as an extension point, and
  these are introduced one at a time, each with explicit ADR
  justification.
- **No big-bang migration.** Every iteration must keep single-tenant
  self-hosted operation working with no user-visible change.
- **No silent fail-open on missing sandbox.** When a multi-tenant
  deployment is configured without a sandboxed tool executor, the
  enterprise plugin's bootstrap emits a hard startup warning and refuses
  to serve dangerous tools. (Iter 5+6.)
- **Cross-tenant ACP is default-off.** Even at GA, intra-tenant only
  unless explicit policy allows it.

---

## Status Tracking

This file is the source of truth for iteration progress. Each iteration's
table row gets updated as it transitions: `Planned` → `In Progress` →
`In Review` → `Done` (with PR links to both repos when applicable).
