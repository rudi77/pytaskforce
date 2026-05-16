---
feature: acp
status: shipped
since: 2026-03-14
last_verified: 2026-05-16
owner: rudi77
adr: ADR-018
---

# Agent Communication Protocol (ACP)

Taskforce speaks the open **Agent Communication Protocol** so two Taskforce
instances — or any ACP-compliant framework such as BeeAI — can interoperate
over REST/JSON. A profile can expose its main agent as an ACP server, register
remote ACP agents as peers, call them through the `call_acp_agent` tool (or
the CLI / runtime), and optionally route the inter-agent message bus over ACP
runs. All ACP code paths are gated behind the optional `--extra acp`
dependency and load lazily: profiles without an `acp:` section work unchanged
on an install without `acp-sdk`.

## Capabilities (what the user can do)

- expose the profile's main agent as an ACP server on a configurable host/port so remote Taskforce peers can call it
- register remote ACP peers (in profile YAML, in `.taskforce/acp_peers.json`, via CLI, or via REST) and reference them by name
- resolve a peer's bearer token from an env var at call time, so secrets never have to be written to the registry file
- call a remote ACP agent from an agent's tool list via `call_acp_agent` (sync or streamed)
- call a remote ACP agent from the operator CLI via `taskforce acp call <peer> <mission>` (sync or streamed)
- list, add, remove, update, and connectivity-probe peers from the CLI and the REST API
- route the in-process message bus over ACP runs so `publish(topic, payload)` fans out to configured peers and `subscribe(topic)` registers a local inbox agent
- receive ACP-delivered missions through the Communication Gateway as the `acp` channel, sharing session/history/push logic with Telegram, Teams, and REST

## Invariants (what must always be true)

- Importing `taskforce` never imports `acp_sdk`; profiles with no `acp:` block remain fully usable on a plain `uv sync` install.
- A call to an unknown peer raises (CLI exits non-zero, `call_acp_agent` returns an error payload with `success=false`) — there is no silent fallback to a default peer.
- A cross-tenant ACP call is rejected unless the peer carries `allow_cross_tenant: true`; when both an `allow_cross_tenant` peer and a `cross_tenant_acp_authorizer` are installed, the authorizer's verdict applies on every call (no caching).
- A peer's tenant scope hides it from other tenants in `peers.list()` / `peers.get(name)`; a hidden peer cannot be removed by an unauthorised tenant.
- Connectivity probe (`POST /peers/{name}/test`, `ping_peer`) reports `ok=false` when an auth-required peer responds with 401/403 — reachability alone is not success.
- The on-disk peer registry file is written with mode `0600` on POSIX so literal bearer tokens are not world-readable.
- Bearer tokens stored via `token_env` are resolved at read time, not at registration; rotating the env var takes effect on the next `peers.get()`.
- `AcpRuntime.start()` and `stop()` are idempotent — repeated calls do not double-start the embedded server or leak client sessions.
- A failing ACP call inside `call_acp_agent` never crashes the parent agent; the failure surfaces as a tool-result payload with `success=false` and a structured `error` field.

## API surface (the contract clients depend on)

The Taskforce REST API exposes peer management for operators and the UI. The
actual ACP protocol endpoints (`/agents`, `/runs`, …) are served by the
embedded `acp_sdk.server.Server` on the port configured under
`acp.server.port`, not by the Taskforce FastAPI app.

- GET    /api/v1/acp/peers → 200 with peer list
- GET    /api/v1/acp/status → 200 with `{configured_peers, peers[]}`
- POST   /api/v1/acp/peers → 201 created
- POST   /api/v1/acp/peers → 409 on duplicate name
- POST   /api/v1/acp/peers → 400 on invalid payload
- PUT    /api/v1/acp/peers/{name} → 200 (creates if missing)
- PUT    /api/v1/acp/peers/{name} → 400 on invalid payload
- DELETE /api/v1/acp/peers/{name} → 204
- DELETE /api/v1/acp/peers/{name} → 404 when missing
- POST   /api/v1/acp/peers/{name}/test → 200 with `{ok, status_code, latency_ms, agent, base_url, error}`
- POST   /api/v1/acp/peers/{name}/test → 404 when peer missing

## Configuration surface (the profile keys operators rely on)

- `acp.server.enabled: bool` (default `false`) — start the embedded ACP server on profile load.
- `acp.server.host: str` (default `0.0.0.0`), `acp.server.port: int` (default `8800`).
- `acp.server.agent_name: str | null` (default `null`, falls back to profile name) — name under which the profile is advertised.
- `acp.server.expose_profile: bool` (default `true`) — register the profile's main agent as an ACP agent.
- `acp.peers: list[{name, base_url, agent, description, tenant_id, allow_cross_tenant, auth}]` — peers usable from this profile.
- `acp.peers[].auth.type: "none"|"bearer"|"mtls"` (default `none`). `bearer` reads `token` or resolves `token_env` at call time; `mtls` carries `cert_path` / `key_path` (schema only — runtime is a known gap).
- `acp.message_bus.transport: "in_memory"|"acp"` (default `in_memory`) — swap the in-process bus for the ACP-backed one.
- `acp.message_bus.publish_peers: list[str]` — peer names that receive `publish(topic, …)` runs (mission agent = `bus_<topic>`).
- `acp.message_bus.subscribe_topics: list[str]` — topics auto-registered as inbox agents on the local ACP server.
- `TASKFORCE_ACP_WORK_DIR` env var — overrides the directory holding `acp_peers.json` (default `.taskforce`); tests and tenant overlays use it.

## Extension points

- `AcpServerProtocol`, `AcpClientProtocol`, `AcpPeerRegistryProtocol`, `AcpRuntimeProtocol` in `taskforce.core.interfaces.acp` — replace any layer of the ACP stack (e.g. swap the SDK, plug in a tenant-aware registry, point at a different transport).
- `InMemoryPeerRegistry`, `FilePeerRegistry`, `EnvPeerRegistry`, `TenantScopedPeerRegistry` in `taskforce.infrastructure.acp.peer_registry` — composable registry wrappers; enterprise overlays stack `TenantScopedPeerRegistry` on top of a postgres-backed inner.
- `set_acp_tenant_id_provider` / `get_acp_tenant_id_provider` in `taskforce.application.infrastructure_overrides` — host applications inject a per-request tenant resolver consumed by `AcpRuntime.call()`.
- `get_cross_tenant_acp_authorizer` in `taskforce.application.infrastructure_overrides` — install a callback that approves or denies each cross-tenant call, evaluated per call (never cached).
- `AcpInboundAdapter(shared_secret=...)` in `taskforce.infrastructure.acp.acp_gateway_adapters` — configure a shared-secret header check when ACP traffic enters via the Communication Gateway.

## Tests (must exist and pass)

- spec("acp.no_acp_section_works_without_sdk")
- spec("acp.unknown_peer_raises_not_falls_back")
- spec("acp.cross_tenant_call_denied_without_flag")
- spec("acp.cross_tenant_authorizer_consulted_per_call")
- spec("acp.tenant_scoped_registry_hides_other_tenants")
- spec("acp.ping_reports_ok_false_on_auth_failure")
- spec("acp.peers_file_chmod_0600_on_posix")
- spec("acp.bearer_token_env_resolved_at_call_time")
- spec("acp.runtime_start_stop_idempotent")
- spec("acp.call_acp_agent_failure_returns_payload_not_raises")
- spec("acp.post_peers_duplicate_returns_409")
- spec("acp.delete_peer_missing_returns_404")
- spec("acp.test_peer_missing_returns_404")
- spec("acp.message_bus_publish_fans_out_to_publish_peers")
- spec("acp.message_bus_subscribe_registers_inbox_agent")

## Known gaps

- **`AcpMessageBus.subscribe` has no lock around inbox-agent registration.** Two concurrent `subscribe(topic)` calls for the same topic on a cold queue can both pass the `existing` check and register the handler twice on the underlying ACP server. Tracked in #313.
- **mTLS is config-only.** `auth.type: mtls` and the `cert_path` / `key_path` fields are accepted by the schema but the client layer still defaults to plain HTTPS / bearer. Documented at `docs/features/acp.md` → "Limitations".
- **No replay protection on the inbound gateway adapter's shared secret.** A captured legitimate ACP request with the correct `X-ACP-Secret` header can be replayed indefinitely. Same root cause as gateway #285 but separate code path.
- **`AcpOutboundSender.send_file` raises `NotImplementedError`.** Proactive file attachments are not yet supported over ACP; the Communication Gateway's file-send path will fail for the `acp` channel.
- **The on-disk peer registry stores literal bearer tokens unencrypted** when callers populate `auth.token` instead of `auth.token_env`. File mode 0600 protects against other-user reads but not root/backup leakage. Prefer `token_env` in production.
- **No `@pytest.mark.spec` markers exist yet** — Tests section above asserts the target, not current state. Spec-check will flag every marker as "asserted but missing test" on first run.

## Cross-references

- adr: ADR-018 (ACP Protocol Support — primary design)
- adr: ADR-022 §6 (multi-tenant ACP — peer scoping + cross-tenant authorisation)
- related_spec: sub-agents.md (local-process counterpart to remote ACP calls)
- related_spec: gateway.md (ACP can ingress through the Communication Gateway as the `acp` channel)
- related_spec: multi-tenant.md (`TenantScopedPeerRegistry` + cross-tenant authorizer)
- docs: docs/features/acp.md (user guide)
- profile: src/taskforce/configs/acp_peer.yaml (ready-to-run ACP server profile)
