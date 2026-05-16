---
feature: web-ui
status: shipped
since: 2026-04-29
last_verified: 2026-05-16
owner: rudi77
---

# Web UI — Bundled Single-Page App

A React SPA bundled with the framework that gives operators a graphical
front-end for everything the REST API exposes: chat with streaming
agents, project-bound conversations, agent CRUD + wizard, runtime
settings, monitoring, workflow definitions, and federation. It is
served from the same FastAPI process that fronts `/api/v1/*` (see
[api.md](api.md)) under a SPA catch-all, and consumes only the
documented REST surface — there is no privileged backdoor.

## Capabilities (what the user can do)

- chat with any visible agent, streaming tokens over SSE, in a single conversation or many parallel ones
- attach files (`@mention` picker) and follow tool-call output inline
- create, list, open, archive, and remove conversations from a sidebar
- create projects (from scratch or by importing a directory), list them, open per-project conversation detail pages
- bind a new conversation to a project so the agent runs in that project's working directory
- list every agent allowed by the deployment manifest, open the editor, compare two agents side-by-side
- create a brand-new agent via a 5-step wizard (without editing YAML)
- browse the unified Capabilities catalogue (tools + skills) with parameter schemas, approval badges, and source
- list, create, edit, and trigger workflow definitions (schedule / webhook / event / chat / manual triggers)
- monitor runs, token usage, and costs; drill into a single session's trace from the runs list
- view ACP peers and remote agents available over federation
- configure runtime settings via five tabs: General, LLM Providers, Channels, Agents (visibility), Integrations (OAuth)
- probe an LLM provider credential or send a real test message via a channel without restarting the backend
- log in / out (when an auth plugin is installed); single-user installs skip the login screen entirely

## Invariants (what must always be true)

- The SPA only talks to the documented REST surface — there is no privileged or hidden endpoint reserved for the UI.
- The bundled UI is served from the same FastAPI process as the API; the SPA catch-all never shadows `/api/`, `/health`, `/docs`, `/redoc`, or `/openapi.json` (enforced by `api.md`).
- The agent list shown in the UI is the deployment-manifest-filtered list returned by `GET /api/v1/agents` — agents hidden by the manifest are not reachable through any UI affordance.
- Settings tabs read and write only via `GET/PUT/DELETE /api/v1/settings/...`; secret fields are masked client-side on display, but the UI never persists them outside the backend's encrypted store.
- A 401 response from any API call clears the locally-stored API token and redirects to `/login`, except when the user is already on a public route (`/login`, `/signup`, plugin-flagged public routes).
- Plugin routes are registered before the React-Router is built; `registry.register()` calls after `buildRouter()` do NOT add new routes to the running router until a full page reload.
- Plugin routes flagged `public: true` mount at top level (next to `/login`) and skip `RequireAuth`, capability guards, and the plugin's `wrap()`.
- A dynamic-import failure (Vite chunk-hash mismatch after a backend upgrade) triggers exactly one automatic page reload per page-load — if it still fails after reload, the user sees a "Page update required" boundary, not an infinite reload loop.
- Conversations without a `project_id` remain fully usable from the chat sidebar; project binding is opt-in (see [cowork.md](cowork.md)).
- The SSE stream consumed by the chat page handles the documented terminal `error` frame and the `stream_restart` event (content-filter recovery) without losing the user-visible message thread.

## API surface (the contract clients depend on)

The UI has no REST surface of its own — it is a pure client of the
documented API. The cross-cutting transport guarantees it depends on
are owned by [api.md](api.md). Per-feature contracts the UI consumes:

- conversations + streaming chat → [conversations.md](conversations.md)
- projects + per-project routing → [cowork.md](cowork.md)
- runtime settings (5 tabs) → [settings-store.md](settings-store.md)
- OAuth connections (Integrations tab) → [auth.md](auth.md)
- channel credentials + bot management → [gateway.md](gateway.md), [settings-store.md](settings-store.md)
- workflow definitions → [workflows.md](workflows.md)
- agent listing + editor → [profiles.md](profiles.md)
- capabilities catalogue → [tools.md](tools.md), [skills.md](skills.md)
- ACP federation → [acp.md](acp.md)

## Configuration surface (what operators set)

- `TASKFORCE_UI_DIR` — explicit path to a built UI bundle; otherwise resolved from `<package>/api/_ui` (production wheel) or `<repo>/ui/dist` (dev install)
- `CORS_ORIGINS` — when the UI is served from a separate origin, must explicitly list it (see [api.md](api.md))
- General-tab settings (API base URL, theme) live in browser-local zustand state (`useSettings`), not on the server

## Extension points (for plugins / enterprise / external use)

- `bootstrapPlugins()` + `registry.register(plugin)` (in `ui/src/plugins/`) — UI plugins contribute routes, sidebar nav items, capability guards, and route wrappers. Routes can be `public: true` to mount pre-auth.
- `CapabilityGuard` / `RequireRole` — plugin routes opt into capability and role gates honored at render time.
- `plugin.wrap(node)` — plugin authors mount providers (e.g. `UserRolesProvider`) around their routes; the wrap sits outside guards but inside `RequireAuth` for non-public routes.
- `@taskforce/enterprise-ui` (optional package) — pulled in as an optional dependency of the host UI; when present its routes (`/admin/llm-providers`, `/admin/channels`, `/admin/deployment`, ...) extend the same Settings surfaces with per-tenant scoping.

## Tests (must exist and pass)

The UI ships frontend tests under `ui/src/pages/*.test.tsx` and
`ui/src/app/router.test.tsx`. Backend `spec()` markers are NOT used
for UI tests — coverage is asserted by file presence + Vitest runs.

- `ChatPage.test.tsx` — chat page renders + handles streaming events
- `ProjectDetailPage.test.tsx` — project detail page renders bound conversations
- `WorkflowsPage.test.tsx` — workflow list + trigger
- `AgentsListPage.test.tsx`, `AgentEditorPage.test.tsx` — agent CRUD UI
- `router.test.tsx` — router wiring, dynamic-import-reload guard, plugin route mounting

## Known gaps

- **Test coverage on the UI is minimal** — only a handful of page-level smoke tests exist (`ChatPage`, `ProjectDetailPage`, `WorkflowsPage`, `AgentsListPage`, `AgentEditorPage`, `router`). Most pages have no test at all, and there are no E2E specs beyond the Playwright scaffolding in `package.json`.
- **Stale-chunk fallback is a workaround, not a fix** — after a backend or dev-server upgrade, browsers cached on old chunk hashes hit a "Page update required" boundary and require a manual reload. `dev.ps1` fingerprints `enterprise-ui/dist/index.js` and wipes `node_modules/.vite` to mitigate this in dev; production has no equivalent guard. See `CLAUDE.md` → *Local Dev Launcher* and `router.tsx` → `tryScheduleAutoReload`.
- **Settings GETs return secret fields unredacted** — UI masks them client-side, but the contract leaks them ([settings-store.md](settings-store.md) #281).
- **The Capabilities page collapses tools + skills into a single catalogue**, replacing earlier `/tools` and `/skills` pages (both now redirect to `/capabilities`). Power users who memorised the old paths are silently redirected; there is no inline notice.
- **No conversation-archive UI** — the chat sidebar lists active conversations only; archived conversations are reachable only via REST.
- **No project-archive UI** — project removal in the UI calls `DELETE /api/v1/projects/{id}`, which only unregisters; on-disk files are preserved per [cowork.md](cowork.md) but the UI does not surface that distinction clearly.
- **Plugin route registration is build-time only** — a plugin loaded after `buildRouter()` returned will not be reachable until a full page reload. Acceptable today because `bootstrapPlugins()` runs once at startup.
- **No global request-id surfaced in the UI** for debugging errors back to backend logs — operators must match by timestamp.
- **The General-tab settings (API base URL, theme) are browser-local**, not synced to the backend, so they don't follow the user across devices.

## Cross-references

- related_spec: api.md (transport, error envelope, SSE infrastructure, SPA mount)
- related_spec: conversations.md (chat streaming contract)
- related_spec: cowork.md (projects + per-project conversation routing)
- related_spec: settings-store.md (5 settings tabs)
- related_spec: auth.md (Integrations tab — OAuth read/revoke)
- related_spec: gateway.md (Channels tab — bot CRUD, test send)
- related_spec: workflows.md (Workflows page)
- related_spec: profiles.md (Agents list/editor)
- related_spec: tools.md, skills.md (Capabilities page)
- related_spec: acp.md (ACP page)
- related_spec: multi-tenant.md (enterprise UI overlay via `@taskforce/enterprise-ui`)
- docs: docs/cowork-comparison.md (vision and gap analysis vs Claude Cowork)
- commit: 4ec9b07 (initial UI, 2026-04-29)
- commit: a7f1c5c (workflows UI, 2026-05-06)
- commit: a034789 (ProjectDetailPage fix + tests, 2026-05-15)
