---
feature: settings-store
status: shipped
since: 2026-04-02
last_verified: 2026-05-16
owner: rudi77
---

# Settings Store — UI-Managed Runtime Config

Operators configure runtime secrets (LLM keys, channel bot tokens, OAuth
metadata, default-agent routing, visible-agent overrides, approval
bypass) through the web UI instead of editing profile YAML or shell
env vars. Each kind of config lives in its own opaque JSON "section",
the whole document is Fernet-encrypted at rest, and writes are
hydrated into process state (env vars, override hooks) immediately so
changes take effect without a restart. Enterprise installs swap the
store for a tenant-scoped backend via an override hook.

## Capabilities (what the user can do)

- list every section currently stored, alongside the catalogue of framework-known section names
- read, replace, and delete any section by name (well-known or plugin-defined)
- store LLM provider credentials (openai, anthropic, azure, google, ollama) and have them hydrated into env vars on the next request
- store communication-channel credentials (Telegram bot token, Teams app id/secret) and have the gateway pick them up on the next request without a restart
- declare a list of approval-bypass tools that skip the approval gate even when the tool defaults to "requires approval"
- override the deployment manifest's visible-agent list at runtime
- manage multiple Telegram bots per tenant (add, list, edit, delete) with per-bot owner, pairing mode, default agent
- probe a stored LLM provider's credentials with a minimal completion before relying on them
- send a real test message via a configured channel (by channel name or by specific bot id) to verify credentials work
- list configured OAuth connections (provider, scopes, expiry) and revoke any one of them

## Invariants (what must always be true)

- The on-disk settings document is encrypted at rest with Fernet; without the master key it is unreadable.
- A partial write cannot corrupt the store — writes are atomic (temp file + rename), so power loss mid-write leaves either the old or the new document intact, never a half-written one.
- The master key resolves from `TASKFORCE_SECRETS_KEY` first, then `<work_dir>/.secrets.key`; the key file is auto-generated on first run when neither source is present.
- Every settings mutation (PUT or DELETE) re-runs the hydrator for the affected section before the response is returned, so the next request sees the new values.
- Writing the `channels` section invalidates the cached gateway and gateway-components so the next inbound/outbound call rebuilds with fresh credentials.
- Settings-store values override env vars when both are present — the UI is authoritative.
- Hydration is additive: env vars the operator set externally are never cleared by a missing settings value.
- Every settings, OAuth, and bot endpoint requires the `tenant:manage` permission; an unauthenticated or under-privileged caller cannot read or mutate any section.
- A non-admin caller never sees another user's private bot in the list endpoint, and never sees an unmasked bot_token for a bot they do not own.
- Creating or modifying a tenant-owned bot requires `tenant:manage`; a regular user can only manage user-owned bots whose `owner_user_id` is their own.
- Bot ids are unique within a tenant; creating a duplicate id returns 409.
- A bot CRUD operation triggers the BotPollerManager to reconcile running pollers; a manager failure is logged but never fails the HTTP write.
- The LLM-provider probe and channel test endpoints re-hydrate from the store first, so they always probe with the latest saved credentials, not stale env values.

## API surface (the contract clients depend on)

- GET    /api/v1/settings → 200 (list of section names + known-sections catalogue)
- GET    /api/v1/settings/{section} → 200
- GET    /api/v1/settings/{section} → 404 if the section was never written
- PUT    /api/v1/settings/{section} → 200 (returns the freshly-stored payload)
- DELETE /api/v1/settings/{section} → 204
- POST   /api/v1/settings/llm-providers/{provider}/test → 200 with `{ok, detail}`
- POST   /api/v1/settings/channels/{channel}/test → 200 with `{ok, detail}`
- GET    /api/v1/settings/channels/bots → 200 (caller-visible bot list, tokens masked unless caller is owner or admin)
- POST   /api/v1/settings/channels/bots → 201 created
- POST   /api/v1/settings/channels/bots → 400 on invalid bot id / payload
- POST   /api/v1/settings/channels/bots → 403 when creating a tenant-owned bot without `tenant:manage`, or a cross-user user-owned bot
- POST   /api/v1/settings/channels/bots → 409 on duplicate bot id
- PATCH  /api/v1/settings/channels/bots/{bot_id} → 200
- PATCH  /api/v1/settings/channels/bots/{bot_id} → 400 on path/payload id mismatch
- PATCH  /api/v1/settings/channels/bots/{bot_id} → 403 when caller is neither owner nor admin
- PATCH  /api/v1/settings/channels/bots/{bot_id} → 404 if the bot does not exist
- DELETE /api/v1/settings/channels/bots/{bot_id} → 204 (idempotent: 204 even if bot is unknown)
- DELETE /api/v1/settings/channels/bots/{bot_id} → 403 when caller is neither owner nor admin
- POST   /api/v1/settings/channels/bots/{bot_id}/test → 200 with `{ok, detail}`
- POST   /api/v1/settings/channels/bots/{bot_id}/test → 403 when caller is neither owner nor admin
- POST   /api/v1/settings/channels/bots/{bot_id}/test → 404 if the bot does not exist
- GET    /api/v1/settings/channels/bot-pollers → 200 (list of bot ids whose poller is running)
- GET    /api/v1/oauth/connections → 200 (list of connections + `auth_manager_available` flag)
- DELETE /api/v1/oauth/connections/{provider} → 204
- DELETE /api/v1/oauth/connections/{provider} → 503 when AuthManager is not configured

## Configuration surface (the profile keys / env vars operators rely on)

- `TASKFORCE_SECRETS_KEY` — Fernet master key (base64-encoded 32-byte secret). Strongly preferred for production so the key lives outside `work_dir`.
- `<work_dir>/.secrets.key` — fallback master key, auto-generated on first run. Chmod 0o600 on POSIX; Windows ACL hardening is the operator's responsibility.
- `<work_dir>/settings.json.enc` — the encrypted settings document itself.

## Extension points (for plugins / enterprise / external use)

- `set_settings_store_override` in `taskforce.application.infrastructure_overrides` — replace the file-based store with a tenant-scoped backend (e.g. Postgres). Resolved by `InfrastructureBuilder.build_settings_store`; every settings route, hydrator call, and connection-test probe goes through the override.

## Tests (must exist and pass)

- spec("settings-store.put_then_get_round_trips_payload")
- spec("settings-store.get_unknown_section_returns_404")
- spec("settings-store.delete_unknown_section_is_204")
- spec("settings-store.document_is_fernet_encrypted_at_rest")
- spec("settings-store.write_is_atomic_under_simulated_crash")
- spec("settings-store.env_key_overrides_work_dir_key_file")
- spec("settings-store.put_llm_providers_hydrates_env")
- spec("settings-store.put_channels_clears_gateway_cache")
- spec("settings-store.hydration_does_not_clear_external_env_vars")
- spec("settings-store.all_routes_require_tenant_manage")
- spec("settings-store.bot_list_masks_other_users_tokens_for_non_admin")
- spec("settings-store.bot_create_duplicate_id_returns_409")
- spec("settings-store.bot_create_tenant_owned_without_admin_returns_403")
- spec("settings-store.bot_crud_triggers_poller_reconcile")
- spec("settings-store.oauth_revoke_without_auth_manager_returns_503")

## Known gaps

- **GET on any section returns the payload as-is** — secret fields (api keys, bot tokens, OAuth refresh tokens) are not server-side redacted. Any caller with `tenant:manage` can read every credential in plaintext. UI masks fields client-side, but the contract leaks them. Tracked in #281.
- **`.secrets.key` is not chmod-restricted on Windows.** The 0o600 fallback is POSIX-only; on Windows the auto-generated key file inherits default ACLs and may be world-readable. Tracked in #282.
- **`TASKFORCE_SECRETS_KEY` lives in the process env**, where any subprocess (tool execution, MCP server, native shell calls) inherits it. A compromised tool can exfiltrate the master key trivially. Tracked in #283.
- **No path-traversal protection on `{section}`** — the route accepts any string and forwards it to the store. The file-based store treats sections as JSON-dict keys (no filesystem traversal), but an alternative store backend that maps section → file path would be vulnerable. Tracked in #291.
- **Bot-token masking on list-endpoint is partial** — only the `bot_token` field is masked; future channel types whose secret lives under a different key (e.g. Teams `app_password`) will currently return unmasked. Tracked in #294.
- **The store is not multi-process-safe.** Two backend workers writing concurrently can clobber each other's writes (last-writer-wins). Acceptable today because admin paths are infrequent and single-tenant, but a hosted multi-tenant deployment would need a database-backed store.
- **No backend `@pytest.mark.spec` markers exist yet** — Tests section above asserts the target, not current state.

## Cross-references

- related_spec: gateway.md (consumes the `channels` section)
- related_spec: multi-tenant.md (uses `set_settings_store_override` for tenant scoping)
- related_spec: auth.md (OAuth connections route shares this spec's auth surface)
- related_spec: approval-gating.md (consumes the `approval` section's `bypass_tools` list)
- docs: CLAUDE.md → "Settings Store" section
