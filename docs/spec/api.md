---
feature: api
status: shipped
since: 2026-01-02
last_verified: 2026-05-16
owner: rudi77
---

# REST API — Transport, Errors, Streaming, Lifespan

The meta-spec for the FastAPI surface that fronts every feature. This spec
covers the cross-cutting transport concerns — error envelope, SSE streaming
infrastructure, request/response middleware, OpenAPI generation, CORS,
lifespan startup/shutdown, health probes, mission-queue introspection, and
the auth seam — and intentionally does NOT enumerate per-feature routes.
Each feature owns its own route surface in its own spec
(`gateway.md`, `conversations.md`, `cowork.md`, `settings-store.md`, ...).

## Capabilities (what the user can do)

- reach a single FastAPI process at `/api/v1/...` for every Taskforce feature
- get a liveness signal at `/health` (no dependencies probed)
- get a readiness signal at `/health/ready` (probes tool registry, configs, LLM key presence)
- read OpenAPI JSON at `/openapi.json` and browse Swagger UI at `/docs` / ReDoc at `/redoc`
- stream long-running agent work via Server-Sent Events (`text/event-stream`)
- cancel a streaming mission cooperatively via `POST /execute/{session_id}/cancel`
- list and cancel queued or in-flight missions when a `PersistentAgentService` is registered
- receive standardized error payloads with a machine-readable `code` for every Taskforce-thrown error
- mount the bundled web UI from the same process (SPA catch-all yields to `/api/*`, `/docs`, `/health`)

## Invariants (what must always be true)

- Every Taskforce-originated HTTP error response carries the same envelope: `{code, message, details?, detail?}`. The `X-Taskforce-Error: 1` response header marks payloads emitted via `taskforce.api.errors.http_exception` so middleware can distinguish them from FastAPI defaults.
- FastAPI validation errors (422) and untagged HTTPExceptions fall through to FastAPI's default handler unchanged — the Taskforce handler only rewrites tagged exceptions.
- Routes raise via `taskforce.api.errors.http_exception(...)` rather than constructing `HTTPException` directly so the envelope and tag header are always consistent.
- SSE streams use `media_type="text/event-stream"`, frame each `ProgressUpdate` as `data: <json>\n\n`, and never buffer the entire response.
- A streaming endpoint that fails mid-stream still emits a final `data:` frame with an `event_type="error"` payload built by `_make_sse_error` — the client never sees a silently truncated stream.
- The lifespan startup runs in a deterministic order: tracing init → settings hydration → agent-package config-dir bootstrap → gateway prebuild → scheduler start → Telegram bot pollers start. Shutdown reverses this order so in-flight work sees still-live components.
- Settings hydration runs before the first LLM call and re-runs after every `PUT/DELETE /api/v1/settings/...` write, so UI-managed provider credentials apply without a restart.
- CORS middleware is added LAST so it wraps every other middleware (including plugin auth) and attaches `Access-Control-*` headers to error responses as well as successful ones.
- `allow_credentials=True` is only set when `CORS_ORIGINS` is an explicit list — the wildcard `*` default forces `allow_credentials=False` so browsers cannot send cookies cross-origin against an unscoped backend.
- The SPA catch-all served by `_mount_ui` never shadows `/api/`, `/health`, `/docs`, `/redoc`, or `/openapi.json` — those paths return 404 from the SPA fallback rather than the SPA's `index.html`.
- Plugin routers and middleware are registered before CORS and before the SPA mount, so plugin auth runs on every API request and plugin routes can override SPA paths.
- `require_permission(perm)` is a no-op when no auth middleware has attached `request.state.user` — single-user / framework-only builds remain unauthenticated by design.
- `get_settings_store`, `get_conversation_manager`, `get_project_store`, and `get_workflow_runtime_service` are intentionally NOT `lru_cache`-decorated so tenant-scoping overrides resolve per request.

## API surface (the contract clients depend on)

Cross-cutting routes owned by THIS spec (per-feature routes belong to their
respective specs):

- GET  /health → 200 with `{status, version, default_profile}`
- GET  /health/ready → 200 with `{status, version, checks}` when dependencies reachable
- GET  /health/ready → 503 on tool-registry build failure (envelope `code="not_ready"`)
- GET  /openapi.json → 200 (OpenAPI 3.x schema)
- GET  /docs → 200 (Swagger UI)
- GET  /redoc → 200 (ReDoc)
- GET  /api/v1/missions → 200 with `{missions: [...]}` listing queued/in-flight requests
- GET  /api/v1/missions → 503 when no `PersistentAgentService` is registered
- POST /api/v1/missions/{request_id}/cancel → 202 with `{request_id, session_id, status}` (`cancelled` for queued, `interrupt_requested` for in-flight)
- POST /api/v1/missions/{request_id}/cancel → 404 when the request_id is unknown
- POST /api/v1/missions/{request_id}/cancel → 503 when no `PersistentAgentService` is registered
- POST /api/v1/execute/{session_id}/cancel → 202 with `{session_id, status="interrupt_requested"}`
- POST /api/v1/execute/{session_id}/cancel → 404 (envelope `code="session_not_running"`) when no active execution

The standardized error envelope used by every Taskforce-thrown error:

```
{ "code": "<machine-readable>", "message": "<human-readable>",
  "details": { /* optional structured */ }, "detail": "<message echo>" }
```

## Configuration surface

- `CORS_ORIGINS` — comma-separated allow list (default `*`; explicit list enables `allow_credentials`)
- `TASKFORCE_UI_DIR` — explicit path to a built web UI; otherwise resolved from `<package>/api/_ui` or `<repo>/ui/dist`
- `TASKFORCE_LOG_DIR` — log destination (default `.taskforce/logs`)
- `TASKFORCE_LOG_FILE` — log file name (default `api.log`)
- `LOGLEVEL` / `TASKFORCE_LOG_DEBUG` — enable DEBUG logging
- `TASKFORCE_WORK_DIR` — base work directory threaded into every infrastructure builder (default `.taskforce`)
- `TASKFORCE_PLUGIN_CONFIG` — optional YAML path read on startup to seed plugin configuration

## Extension points

- `taskforce.plugins` entry-point group — plugins contribute middleware and routers; routers are mounted at `/api/v1` after the core routers and before the SPA catch-all.
- `set_persistent_agent_service(service)` in `taskforce.api.dependencies` — embedding hosts (butler daemon, custom REST processes) publish their queue so `/api/v1/missions/*` becomes reachable.
- `register_active_event_source(name, source)` / `unregister_active_event_source(name)` — webhook-capable event sources publish themselves so `POST /api/v1/events/{source_name}` can dispatch payloads.
- `set_standing_goal_store(store)` / `set_goal_evaluator(evaluator)` — daemon publishes its instances so the standing-goals routes share state across processes.
- `taskforce.application.infrastructure_overrides` — overrides for settings store, conversation store, project store, gateway components, recipient resolver, etc. Resolved per request (not cached) so tenant context is honored.

## Tests (must exist and pass)

- spec("api.error_envelope_has_code_and_message")
- spec("api.error_envelope_marked_with_x_taskforce_error_header")
- spec("api.untagged_http_exception_falls_through_to_fastapi_default")
- spec("api.health_returns_200_with_version_and_default_profile")
- spec("api.health_ready_returns_503_when_tool_registry_unavailable")
- spec("api.openapi_schema_served_at_openapi_json")
- spec("api.sse_stream_emits_terminal_error_frame_on_producer_exception")
- spec("api.missions_list_returns_503_when_no_persistent_agent_service")
- spec("api.missions_cancel_unknown_request_id_returns_404")
- spec("api.execute_cancel_unknown_session_returns_404")
- spec("api.cors_wildcard_disables_allow_credentials")
- spec("api.spa_catchall_does_not_shadow_api_routes")
- spec("api.settings_hydration_runs_before_first_request")

## Known gaps

- **`HTTPException` raised in routes via `HTTPException(...detail=...)` (instead of the `http_exception` helper) leaks raw `detail` strings without the standardized envelope.** Tracked in #289.
- **CORS defaults to `*` allow-origin.** Production deployments must set `CORS_ORIGINS` explicitly or any browser context can issue requests against the API. Tracked in #290.
- **No top-level mission timeout.** A wedged LLM call or runaway tool loop can keep `/execute` and `/execute/stream` hanging indefinitely; only cooperative `cancel` ends them. Tracked in #338.
- **SSE streaming backpressure is hardcoded to a 64-slot internal queue inside the executor's progress channel** — slow consumers cause silent slot pressure rather than explicit `429`/disconnect. Tracked in #364.
- **Webhook signature verification has no replay protection.** A captured legitimate payload can be replayed indefinitely against any channel. Tracked in #285 (owned by `gateway.md` but listed here because the surface is REST).
- **SSE error frames leak exception type and message** — applies to every streaming endpoint; conversations.md owns the detail (#287/#288).
- **No global request-id middleware.** Errors and structured logs don't share a correlation id across the request lifecycle, so multi-service debugging requires manual stitching.
- **OpenAPI `responses` declarations are inconsistent across routes** — some routes declare full error schemas (e.g. `execution.py`), others rely on FastAPI defaults. Client SDKs generated from the spec see only partial error contracts.
- **No backend `@pytest.mark.spec` markers exist yet** — Tests section above asserts the target, not current state.

## Cross-references

- related_spec: gateway.md (channel-specific routes, webhook signature handling)
- related_spec: conversations.md (SSE event contract for `/messages/stream`)
- related_spec: cowork.md (`/api/v1/projects/*`)
- related_spec: settings-store.md (`/api/v1/settings/*`, hydration)
- related_spec: auth.md (`/api/v1/oauth/*`)
- related_spec: persistent-agent.md (the queue surfaced by `/api/v1/missions/*`)
- related_spec: multi-tenant.md (`require_permission` seam, per-request store resolution)
- docs: docs/api.md (user-facing REST reference)
- commit: ad64a20 (initial FastAPI app, 2026-01-02)
- commit: 381580c (extracted `exception_handlers` for `taskforce.host` reuse, 2026-05-03)
