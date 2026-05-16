---
feature: auth
status: shipped
since: 2026-03-21
last_verified: 2026-05-16
owner: rudi77
---

# OAuth2 + Auth Manager — Centralised Authentication

A single subsystem that lets agents and tools authenticate against
external providers (Google, Microsoft, GitHub, custom) over OAuth2
without each tool re-inventing token storage, refresh, or the
interactive consent dance. The `AuthManager` orchestrates two flows
(device authorization grant for headless / chat-driven contexts,
authorization code for local CLI with a browser) plus a fallback
username/password "credential" flow, persists tokens Fernet-encrypted
on disk, refreshes them transparently when callers request a token,
and exposes a minimal REST surface for the UI to list and revoke
connections.

## Capabilities (what the user can do)

- authenticate against a configured provider (`google`, `microsoft`, `github`, custom) from chat by invoking the `authenticate` tool
- pick the auth flow per call: OAuth2 device grant (default — headless / Telegram / Teams), OAuth2 authorization code (CLI with browser), or `credential` (username/password)
- receive the verification URL + user code on the same channel the agent is talking on, via the Communication Gateway
- have access tokens refreshed automatically the next time a downstream tool asks for a valid token — no re-prompt while a refresh token is on file
- override the default scopes per call, or fall back to the provider's configured `default_scopes`
- list every provider currently connected, with status, scopes, expiry, and whether a refresh token is on file, via REST
- revoke and delete a provider's tokens via REST so the next call falls back to a fresh flow
- store custom-provider endpoints (`device_auth_url`, `token_url`, `auth_url`) per provider through the auth flow's `metadata` so providers not in the built-in catalogue still work

## Invariants (what must always be true)

- Tokens on disk are Fernet-encrypted; without the master key the store is unreadable.
- Token writes are atomic — a power loss mid-write leaves either the old token or the new one on disk, never a half-written file. Per-provider `asyncio.Lock` serialises concurrent in-process writes.
- The master key resolves from `TASKFORCE_AUTH_KEY` first, then from `<store_dir>/.key` (auto-generated on first use). A warning is logged when the file fallback is used.
- `get_token(provider)` returns a token whose `is_expired` is false: an expired token with a refresh token triggers a transparent refresh before returning.
- A refresh attempt that fails persists `status=failed` on the existing token row so callers can distinguish "never authenticated" from "token revoked / refresh broken".
- `revoke(provider)` always deletes the on-disk token even when the provider is unknown to the local store (idempotent — never raises on missing).
- The OAuth2 auth-code flow generates a fresh CSRF `state` per call (32-byte URL-safe) and rejects callbacks whose `state` does not match.
- The local callback server in the auth-code flow binds only to `127.0.0.1` on an ephemeral port and is torn down after a single callback or a 5-minute timeout.
- The device flow honours the provider's `interval` / `expires_in` from the device-code response and surfaces a timeout instead of polling forever.
- `authenticate` is gated as a high-risk tool — the approval system prompts the user before any OAuth flow runs.
- The REST connections routes require the `tenant:manage` permission; an unauthenticated or under-privileged caller cannot list or revoke connections.
- `GET /oauth/connections` returns `auth_manager_available=false` (with an empty list) instead of 500 when the framework couldn't initialise an `AuthManager` (e.g. missing `cryptography`); the UI uses this to hide OAuth controls.
- A corrupt token row in the store is reported with `status="unreadable"` in the list response, never crashes the listing.

## API surface (the contract clients depend on)

- GET    /api/v1/oauth/connections → 200 with `{connections, auth_manager_available}`
- GET    /api/v1/oauth/connections → 403 without `tenant:manage`
- DELETE /api/v1/oauth/connections/{provider} → 204
- DELETE /api/v1/oauth/connections/{provider} → 403 without `tenant:manage`
- DELETE /api/v1/oauth/connections/{provider} → 503 when `AuthManager` is not configured

Initiating a fresh OAuth flow from REST is intentionally not exposed —
operators run the `authenticate` tool from chat, which handles the
multi-step device polling interactively.

## Configuration surface (the profile keys / env vars operators rely on)

- `TASKFORCE_AUTH_KEY` — Fernet master key (base64 32-byte) for token encryption. Strongly preferred for production so the key lives outside the store directory.
- `<store_dir>/.key` — fallback master key, auto-generated on first run. Default `store_dir` is `~/.taskforce/auth/`.
- Per-provider config dict (`client_id`, `client_secret`, `default_flow`, `default_scopes`, `metadata`) passed into `AuthManager(provider_configs=...)` from the profile loader. `metadata.device_auth_url` / `metadata.token_url` / `metadata.auth_url` override built-in endpoints for custom providers.
- Built-in flow types resolvable by name: `oauth2_device`, `oauth2_auth_code`, `credential`.
- Built-in provider endpoint catalogue: `google`, `microsoft`, `github` (for both device and auth-code flows).

## Tests (must exist and pass)

- spec("auth.token_store_round_trips_payload_encrypted")
- spec("auth.token_store_load_missing_returns_none")
- spec("auth.token_store_delete_missing_is_noop")
- spec("auth.token_store_write_is_atomic")
- spec("auth.master_key_env_overrides_key_file")
- spec("auth.get_token_returns_none_when_unknown")
- spec("auth.get_token_refreshes_expired_token_transparently")
- spec("auth.refresh_failure_persists_failed_status")
- spec("auth.authenticate_short_circuits_when_valid_token_present")
- spec("auth.authenticate_uses_default_flow_from_provider_config")
- spec("auth.revoke_deletes_token_idempotently")
- spec("auth.device_flow_times_out_after_expires_in")
- spec("auth.device_flow_propagates_denied_error")
- spec("auth.auth_code_flow_rejects_mismatched_state")
- spec("auth.auth_code_callback_server_binds_localhost_only")
- spec("auth.oauth_connections_requires_tenant_manage")
- spec("auth.oauth_revoke_without_auth_manager_returns_503")
- spec("auth.oauth_connections_reports_unreadable_token_row")
- spec("auth.authenticate_tool_marked_high_risk_approval")

## Known gaps

- **`.key` master-key file is world-readable on Windows** — the file is written with default ACLs (no chmod 0o600 fallback). Tracked in #282.
- **`TASKFORCE_AUTH_KEY` lives in the process env**, so any subprocess (tool execution, MCP server, native shell calls) inherits it. A compromised tool can exfiltrate the master key trivially. Tracked in #283.
- **`CredentialFlow` logs username and password through structlog when storage fails** — the prompt text is logged at INFO level. Plaintext credentials may end up in log aggregators. Tracked in #284.
- **No master-key rotation path** — there is no documented procedure to re-encrypt the store under a new `TASKFORCE_AUTH_KEY`. Operators who suspect a key compromise must revoke every connection and re-authenticate. Tracked in #302.
- **OAuth2 authorization-code flow does not use PKCE** — the `code_verifier` / `code_challenge` parameters are absent. Public clients on shared machines are vulnerable to code-interception. Tracked in #285.
- **`GET /oauth/connections` returns token metadata as-is** — `scopes`, `expires_at`, and `has_refresh_token` are fine, but a future schema change could leak `client_secret`. The response model masks nothing server-side; callers with `tenant:manage` can see every connection's metadata. Tracked in #299.
- **`EncryptedTokenStore._get_fernet()` lazy-init is not concurrency-safe** — two coroutines hitting it in parallel can both construct a Fernet instance. Benign today (idempotent), but a race window exists. Tracked in #311.
- **`AuthManager.get_token()` refresh race** — two concurrent callers requesting the same expired token both spawn a refresh request, doubling the upstream load and risking a `invalid_grant` on the second one. No per-provider in-flight dedup. Tracked in #310.
- **Device flow ignores `slow_down`'s required backoff increment** — RFC 8628 requires increasing the poll interval on `slow_down`, but the implementation keeps polling at the original interval. Risks IP throttling. Tracked in #332.
- **No backend `@pytest.mark.spec` markers exist yet** — Tests section above asserts the target, not current state.

## Cross-references

- related_spec: settings-store.md (intended provider-config storage seam; AuthManager is not yet wired to read it)
- related_spec: gateway.md (device flow uses the gateway's question/answer flow for user interaction)
- docs: CLAUDE.md → "Auth" entries (auth_manager, encrypted token store)
- commit: (auth_manager introduced 2026-03-21)
