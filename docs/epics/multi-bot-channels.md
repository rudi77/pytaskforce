# Multi-Bot Channels: Personal + Tenant-Shared Bots per Channel Type

**Status:** Draft / Deferred (post-v0.2.0 feature freeze)
**Created:** 2026-05-12
**Owner:** rudi77
**Classification:** Net-new authoring/scope feature (per `feedback_multitenant_gap_classification`)

---

## Context

The current channel configuration models *one bot per channel type per tenant*. Telegram is a single `bot_token` in the tenant-shared `CHANNELS` settings section; per-user routing within that one bot is handled via the `/link <code>` pairing flow shipped in PR #224. That works well for **team/family/workspace use cases** — one branded bot, many users behind it via pairing.

It does **not** model the equally common case where each user wants their *own* dedicated bot identity:

- Rudi's personal Butler with `@RudisAssistent`
- Anna's reading-tracker bot with `@AnnasLeseClub`
- Same tenant `dittrich_family`, two separate bot identities, no cross-pairing

Per the user's product vision (`Tenant=Workspace, User=Person`), both bot-ownership models need to coexist within the same tenant. A support bot ("everyone in the tenant talks to it") and a personal Butler ("only mine") should live side by side.

The implementation is deferred behind the v0.2.0 feature freeze, but the design and the open trade-offs are pinned here so the work is shovel-ready when the freeze lifts.

---

## Target Model

A tenant has a **channel-bot pool** rather than a single config per channel type:

```yaml
# Settings section "CHANNELS" — new shape
bots:
  - id: "support"
    channel_type: telegram
    bot_token: "...support-token..."
    owner: "tenant"                  # everyone in tenant
    default_agent: support_agent
    pairing: paired                  # users must run /link
    enabled: true

  - id: "rudi-butler"
    channel_type: telegram
    bot_token: "...rudi-token..."
    owner: "user:ca8ed02d-091f-..."  # Rudi only
    default_agent: butler
    pairing: implicit                # bot IS Rudi, no /link
    enabled: true

  - id: "anna-tracker"
    channel_type: telegram
    bot_token: "...anna-token..."
    owner: "user:ed55b870-875e-..."  # Anna only
    default_agent: reading_tracker
    pairing: implicit
    enabled: true
```

Each bot gets its own long-polling loop in the backend; the gateway-registry builds **N inbound adapters**, indexed by `bot_id` not by `channel_type`.

---

## Design Decisions

| # | Decision | Choice | Rationale |
|---|----------|--------|-----------|
| 1 | **Token visibility for tenant admin** | Hidden (admin sees existence + metadata, not token) | Privacy default — a user's personal bot token is their secret, even from tenant admin. Admin needs the *capability* to revoke/disable, not to *read*. |
| 2 | **Per-user bot quota** | Soft 5/user, hard 20/tenant — both configurable in tenant settings | Prevents polling-loop sprawl; soft cap is enforced via UI nag, hard cap is enforced at PUT-time |
| 3 | **Lifecycle: hot-reload vs restart** | **Restart-required** for v1; document "Save and restart backend to activate new bots". Hot add/remove is a follow-up enhancement. | 80% value at 20% complexity. Bots are configured *rarely*. Hot-reload requires careful adapter-lifecycle code (polling-loop start/stop with token-validation race) — defer. |
| 4 | **`default_agent` per bot** | Yes — each bot config carries a `default_agent` field | A personal Butler bot answers as `butler`; a support bot answers as `support_agent`. Replaces user-level default-agent for that bot's interactions. `@agent_name` override in message body still works. |
| 5 | **Pairing modes per bot** | Three: `implicit`, `paired`, `anonymous` | See below |

### Pairing modes detail

| Mode | Meaning | Typical use |
|------|---------|-------------|
| `implicit` | Bot owner is a specific user. Every message → that user. No `/link` needed. | Personal bots (`owner: user:*`) |
| `paired` | Each Telegram chat must run `/link <code>` once to claim its user_id. Until paired, messages are rejected. | Tenant-shared bots where each conversation should be user-specific (workspace assistant) |
| `anonymous` | No per-user routing. All messages go to `default_agent` without user context. | Public FAQ bots, support intake (no user-specific data accessed) |

Default mode is auto-set by `owner`: `user:*` → `implicit`, `tenant` → `paired`. Operator can override.

---

## Implementation Slices

### Slice 1 — Domain model + settings schema (`pytaskforce`)

- `core/domain/settings.py`: new `BotConfig` dataclass + `CHANNELS` section schema becomes `{"bots": list[BotConfig]}`.
- Settings-store migration shim: when reading the **old** flat shape (`{"telegram": {"bot_token": "..."}}`), synthesize a single `bots[0]` entry with `id="legacy-telegram"`, `owner="tenant"`, `pairing="paired"`. Stays read-write-compatible until operators migrate.
- New REST endpoints under `/api/v1/settings/channels/bots`: GET list, POST add, PATCH edit, DELETE remove.
- Permission gate per endpoint:
  - Tenant-shared bots (`owner: tenant`) → `tenant:manage`
  - User-owned bots (`owner: user:<uid>`) → must match the calling user OR `tenant:manage` (admin override)

**Critical files:**
- `src/taskforce/core/domain/settings.py`
- `src/taskforce/api/routes/settings.py`
- `src/taskforce/application/settings_hydrator.py` (rewrite — no longer flat env-var translation)

### Slice 2 — Gateway multi-bot inbound (`pytaskforce`)

- `core/interfaces/gateway.py::InboundMessage`: add optional `bot_id: str | None` field.
- `infrastructure/communication/gateway_registry.py::build_gateway_components`: iterate bot configs, build N `TelegramInboundAdapter` instances (one per token), key them by `bot_id` in the components map.
- `application/gateway.py::handle_inbound`: route by `bot_id`:
  - If bot owner is `user:X` → message's user_id is X (skip ChannelLinkRegistry)
  - If bot owner is `tenant` and pairing=`paired` → use existing `ChannelLinkRegistry` flow
  - If pairing=`anonymous` → use default_agent without user context

**Critical files:**
- `src/taskforce/core/interfaces/gateway.py`
- `src/taskforce/infrastructure/communication/gateway_registry.py`
- `src/taskforce/infrastructure/communication/inbound_adapters.py` (already keyed by token; minimal change)
- `src/taskforce/application/gateway.py`

### Slice 3 — UI (`pytaskforce/ui`)

- `features/settings/ChannelsTab.tsx`: replace the current Telegram/Teams cards with a **bot list** split into two sections:
  - **My personal bots** — visible only when the user has user-owned bots; user can add/edit own
  - **Tenant-shared bots** — visible to all tenant users, editable only with `tenant:manage`
- Add-bot wizard: name → channel-type → owner radio (`Just me` / `Everyone in the tenant`) → token → default-agent dropdown → pairing-mode dropdown.
- Test-connection button per bot (existing endpoint).
- "Restart required" hint when bots are added/removed.

**Critical files:**
- `ui/src/features/settings/ChannelsTab.tsx` (rewrite)
- `ui/src/api/queries.ts` (new hooks: `useChannelBots`, `useCreateBot`, …)

### Slice 4 — Enterprise plugin: permission + settings-store split (`taskforce-enterprise`)

The current `settings_store_for_current_tenant` returns one store per tenant. Per-user settings sub-sections (`channels.bots.<id>` where owner is a user) need owner-check at the **API** layer — not at the store layer.

- New permission `channel:own:write` granted to all base roles (operator, agent_designer, viewer). Required for user-owned bot CRUD.
- Tenant-shared bot CRUD still gated on `tenant:manage`.
- The settings store stays tenant-scoped; the API route does the per-bot owner check.

**Critical files (enterprise repo):**
- `src/taskforce_enterprise/core/interfaces/identity.py` — new `Permission.CHANNEL_OWN_WRITE`
- Add to all default role permission sets

---

## Out-of-Scope (Explicitly)

- **Per-user LLM provider keys** — stays tenant-shared. Cost-control + admin-managed-credentials reason.
- **Per-user OAuth connections** — those are *already* per-user (Gmail / Calendar / Drive use `TokenStoreProtocol` with user scope). No change.
- **Hot bot add/remove without restart** — deferred, see Decision #3.
- **Channel types other than Telegram** — Teams/Slack get the same model as a parallel slice, but each has its own quirks (Teams = Bot Framework, Slack = events API). Generalize *after* Telegram is solid.

---

## Verification (when implementation lands)

1. **Single-tenant single-user (regression):** Existing single-bot setup keeps working via the legacy-shape migration shim. No restart-loop.
2. **Two users, two personal bots:**
   - Rudi creates `rudi-butler` with his token via UI → restart → message to his bot → Butler responds *to Rudi only*.
   - Anna creates `anna-tracker` with her token → restart → her bot routes to her agent. Cross-bot isolation: Rudi's messages never reach Anna's agent.
3. **Tenant-shared support bot:**
   - Admin creates `support` bot with `pairing=paired`.
   - Both users run `/link <code>` once → both can chat with it → each conversation scoped to its user (existing `ChannelLinkRegistry` path).
4. **Permission isolation:**
   - Non-admin user attempts to edit `support` bot → 403.
   - Non-admin user creates their own personal bot → 200, owner=themselves.
   - Admin can list all bots; user can only list shared + their own.
5. **Token visibility:**
   - Admin GETs the bot list → user-owned tokens are masked (e.g. `tg-bot-***-3456`); only metadata exposed.

---

## Open Questions for Implementation Day

- **Polling-loop teardown on bot disable** — when a bot is disabled via UI, should the polling loop stop immediately (next request rebuilds) or only on next restart? Restart-required keeps it simple.
- **Token rotation flow** — if a user edits an existing bot's token, the running polling loop is stuck on the old token. Same restart-required guidance.
- **Audit log entries** — every bot create/delete/edit should hit `audit_log` with the actor + target bot id. The audit dispatcher already exists; just emit events from the new endpoints.

---

## Related

- PR #224 (`fix(gateway): per-user Telegram pairing via ChannelLinkRegistry + /link (#162)`) — current per-user routing within a shared bot.
- PR #182/#183 (`feat(settings): UI-driven runtime config`) — the settings store this builds on.
- PR #226 (`fix(memory): wiki tool respects per-user store override`) — the per-user-scoping seam pattern this would follow.
- ADR-022 (multi-tenant runtime) — the broader architecture that defines `tenant` and `user` scoping.
