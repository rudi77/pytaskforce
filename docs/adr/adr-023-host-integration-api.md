# ADR-023: Host-App Integration API (`taskforce.host`) and `taskforce serve`

**Status:** Accepted (initial implementation merged on `feature/host-integration-api`)
**Date:** 2026-05-03
**Related:** ADR-002 (Clean Architecture Layers), ADR-009 (Communication Gateway), ADR-011 (Unified Skills), ADR-016 (Persistent Agent Architecture), ADR-021 (UI Plugin System), ADR-022 (Multi-Tenant Enterprise Runtime)

## Context

Taskforce already supports three deployment shapes — in-process library
(`AgentFactory`), CLI (`taskforce run …`, `taskforce chat …`) and a
FastAPI server (`taskforce.api.server:app`). All three are real and used
in production. What's been missing is a **stable, public seam for an
external host application to embed any of them** without reaching into
private modules.

The concrete trigger for this ADR is a separate codebase (`pinta`) that
builds a Maler-Kostenvoranschlag agent on top of Taskforce. Today its
integration code reaches directly into module-private state to wire
itself up:

```python
# pinta/backend/src/agents/factory.py — current integration
from taskforce.infrastructure.tools.registry import (
    _TOOL_REGISTRY,    # underscore = "don't touch"
    register_tool,
)
```

The host app additionally:

* Loads its own `maler.yaml` via `yaml.safe_load` and bypasses the
  `ProfileLoader` entirely (so the framework's profile search-path,
  `extends:` resolution and Pydantic validation never run).
* Runs its own Telegram poller against the bot token (so the framework's
  `infrastructure/communication/telegram_poller.py`, gateway sessions
  store and pending-channel question store are duplicated by hand).
* Has no clean way to start the FastAPI app — `uvicorn taskforce.api.server:app`
  works but is undocumented and the host has to know the asgi path.
* Maintains a parallel `AIService` that calls the Azure OpenAI SDK
  directly for the Web-Chat path, because mounting only "the gateway and
  execution routes" inside their existing FastAPI app is not supported.

The same pattern repeats for any integrator. Without a stable API:

* Every minor refactor in `infrastructure/tools/registry.py`,
  `application/profile_loader.py`, `infrastructure/skills/` or
  `api/server.py` risks breaking host apps.
* Host apps reinvent infrastructure that the framework already ships.
* The "library / CLI / webservice" trio is not actually three modes —
  it's one mode (library) plus two undocumented packagings of it.

## Decision

Introduce a **public host-integration surface** consisting of two
artefacts. Both are additive — no existing API is renamed or removed.

### 1. `taskforce serve` CLI command

A new sub-command on `taskforce-cli` that thin-wraps `uvicorn.run` over
`taskforce.api.server:app`:

```bash
taskforce serve                             # 127.0.0.1:8070 by default
taskforce serve --host 0.0.0.0 --port 9000  # opt-in network exposure
taskforce serve --reload                    # dev hot-reload
taskforce serve --workers 4 --log-level info
taskforce serve --app myapp.main:app        # mount Taskforce inside a host ASGI app
```

Defaults follow the principle of least exposure: `--host 127.0.0.1`,
`--workers 1`, `--log-level info`. Container/k8s deployments must opt in
to `0.0.0.0`.

### 2. `taskforce.host` module

A new top-level module that re-exports the small set of symbols a host
app legitimately needs, with stability guarantees:

```python
from taskforce.host import (
    # Tool / profile / skill registration
    register_tool,             # idempotent re-export of registry.register_tool
    unregister_tool,
    is_tool_registered,
    register_profile_dir,      # wraps profile_loader.register_config_dir
    register_skill_dir,        # NEW: parallel registry for skills

    # FastAPI embedding
    mount_routes,              # selectively mount Taskforce routers on a host app
    create_embedded_app,       # build a fresh FastAPI app with a router subset
    available_routers,         # enumerate router names

    # Infrastructure overrides (re-exported from infrastructure_overrides)
    set_agent_registry_override,
    set_state_manager_override,
    set_gateway_components_override,
    clear_infrastructure_overrides,
)
```

The module sits **outside** the four-layer stack (Core → Infrastructure
→ Application → API). This is the only place where a layer-crossing
"public seam for external apps" is allowed. It contains no business
logic — it is a translation table from the framework's internal symbol
names to a stable external contract.

#### `register_skill_dir` (new infrastructure)

To make this work, `application/skill_service.py` gains a global
`_extra_skill_dirs: list[Path]` registry, parallel to the existing
`profile_loader._extra_config_dirs`. Late registration after the
`SkillService` singleton has been constructed propagates the new
directory into the live registry and triggers a refresh, so host apps
can register skills both at startup and dynamically.

Path inputs are normalised via `Path(path).expanduser().resolve()` so
that `"./foo"`, `"foo"` and `/abs/path/foo` all dedupe to the same
entry — matching the contract `register_config_dir` already provides.

#### `mount_routes` and `create_embedded_app`

`mount_routes(app, prefix=, include=, exclude=)` mounts a chosen subset
of Taskforce's REST routers onto an existing `FastAPI` instance. Two
routers (`health`, `acp`) are mounted at the app root because their
public URLs are not under `/api/v1`; everything else honours `prefix`.
The function is **idempotent**: it remembers what it mounted on each app
via a private sentinel attribute (`_taskforce_host_mounted_routers`), so
re-invocation under uvicorn `--reload` or test fixtures does not produce
duplicate routes.

`create_embedded_app(...)` builds a fresh FastAPI instance with a chosen
router subset, optionally installing the Taskforce HTTP-exception
handler. Unlike `taskforce.api.server:app` it does **not** install
plugins, CORS middleware or the lifespan tracing hooks — the host app
owns those.

#### Side-effect: extracted exception handler

`api/server.py` previously owned `taskforce_http_exception_handler` at
module scope. To let `taskforce.host.create_embedded_app` reuse it
without triggering `server.py`'s module-level `app = create_app()` (and
therefore plugin discovery, the global app construction, and the
exception-handler/CORS wiring on the standalone app), the handler is
extracted into a dedicated module:

```
src/taskforce/api/exception_handlers.py   # taskforce_http_exception_handler
```

`server.py` and `host.create_embedded_app` both import from this module.

### 3. Layer position of `taskforce.host`

```
┌─────────────────────────────────────────────────┐
│              taskforce.host                     │  ← new public seam
│         (re-exports + embedding helpers)        │
├─────────────────────────────────────────────────┤
│   API   →   Application   →   Infrastructure   →   Core
└─────────────────────────────────────────────────┘
```

`taskforce.host` may import from any layer. The four-layer rules in
`CLAUDE.md` continue to apply to everything below it. Documenting this
explicitly avoids future "layer violation" comments on the
`from taskforce.infrastructure.tools.registry import ...` line in
`host/__init__.py`.

## Consequences

### Positive

* **Three deployment modes are now real, not aspirational.** A host app
  can pick library / CLI / webservice based on its own constraints
  without writing per-mode integration glue.
* **Pinta-style reach into private state goes away.** `_TOOL_REGISTRY`,
  the `taskforce_cli.agent_discovery._AGENT_PACKAGES` table and the
  ad-hoc `yaml.safe_load(maler.yaml)` are all replaced by stable
  `taskforce.host.register_*` calls.
* **`taskforce serve` removes a documentation gap.** Host docs no
  longer have to point at `uvicorn taskforce.api.server:app` and
  explain how to set `--host`/`--workers`/`--reload` correctly.
* **Selective router mounting unlocks gateway-only embedding.** A host
  FastAPI app can adopt `gateway` + `execution` + `skills` (the three
  routers Pinta needs) without inheriting `evals`, `agent_deployments`,
  `analytics`, `mcp` etc.
* **`api.server.py` stays free of new responsibilities.** All the
  "embedded app" logic lives in `host/__init__.py`, not in
  `create_app()`. The standalone server is unchanged.
* **The override hooks (`set_*_override`) become discoverable.** They
  exist for `taskforce-enterprise` already (ADR-022) but were not
  re-exported from a public location. Now they are part of the same
  public surface a host app browses.
* **Idempotency is built in.** `register_tool`, `register_profile_dir`,
  `register_skill_dir` and `mount_routes` all tolerate repeat calls.
  Host apps can call them from `__init__.py` modules without worrying
  about uvicorn `--reload` or pytest fixtures triggering double
  registration.

### Negative

* **Two ways to do the same thing during the transition.** Existing
  callers can still use `infrastructure.tools.registry.register_tool`
  directly. Until the codebase is fully migrated, both paths coexist.
  Mitigation: the framework's own callers stay on the underlying
  modules (no churn); only host apps and docs steer toward
  `taskforce.host`.
* **`taskforce.host` is now an API contract.** Anything we re-export
  freezes; we cannot rename it without a deprecation cycle. Mitigation:
  the surface is intentionally tiny (10 functions) and each one wraps a
  single underlying call.
* **`SkillService` singleton lifecycle becomes load-bearing.** Late
  `register_skill_dir` calls only see the live singleton; calls that
  arrive *before* the singleton is built also work via the global
  `_extra_skill_dirs` list. Two code paths means two test cases —
  both are covered, but the contract must be documented in the
  function's docstring (and is).
* **Extracted exception handler is a one-time disruption.** Anything
  previously importing `taskforce.api.server.taskforce_http_exception_handler`
  must switch to `taskforce.api.exception_handlers`. There are zero
  such callers in the framework today, but external code that copied
  the import path will break.

### Neutral

* The `_BUILTIN_ROUTERS` map in `taskforce.host` duplicates the router
  list in `api/server.py:create_app`. Both must be kept in sync when a
  new top-level router is added. Acceptable cost: routers are added
  rarely (≈1/quarter), and the cost of an out-of-sync map is a clear
  test failure (the host test asserts routers can be mounted).

## Implementation

Introduced on branch `feature/host-integration-api`, single commit:

* **New files**
  * `cli/src/taskforce_cli/commands/serve.py`
  * `src/taskforce/host/__init__.py`
  * `src/taskforce/api/exception_handlers.py`
  * `tests/unit/test_host.py` (14 tests)
  * `tests/unit/test_cli_serve.py` (5 tests)
* **Modified**
  * `cli/src/taskforce_cli/main.py` — register `serve` sub-command.
  * `src/taskforce/api/server.py` — import `taskforce_http_exception_handler` from the extracted module.
  * `src/taskforce/application/skill_service.py` — add `_extra_skill_dirs` registry and `register_skill_dir` / `get_extra_skill_dirs` / `clear_extra_skill_dirs`; merge into `get_skill_service()`.

All tests pass (353 in the touched-area suite). The 7 pre-existing
`tests/integration/test_llm_service_integration.py` failures (real
Azure OpenAI calls) are unaffected by this change and reproduce on
`main`.

## Migration guide for host apps (Pinta as the worked example)

1. Replace direct `_TOOL_REGISTRY` access with
   `taskforce.host.register_tool(name, class_name, module)`.
2. Move `maler.yaml` next to a `register_profile_dir(...)` call so the
   framework's `ProfileLoader` discovers it; pass `profile="maler"` to
   `AgentFactory.create_agent` instead of a custom YAML reader.
3. Move skills under `<your_repo>/skills/<name>/SKILL.md` and call
   `register_skill_dir("<your_repo>/skills")` once at startup.
4. Replace the bespoke Telegram poller with the framework's gateway:
   either run `taskforce serve` as a sidecar and POST to
   `/api/v1/gateway/telegram/webhook`, or mount the gateway router on
   the host app via `mount_routes(app, include=["gateway", "execution", "skills"])`.
5. For RBAC/multi-tenant deployments (ADR-022), install
   `taskforce-enterprise` and let it call the same
   `set_agent_registry_override(...)` /
   `set_state_manager_override(...)` /
   `set_gateway_components_override(...)` hooks — now re-exported from
   `taskforce.host` for discoverability.

## Open questions / follow-ups

* **`register_inbound_adapter` / `register_outbound_sender` for custom
  channels.** Today host apps add channels via
  `set_gateway_components_override` (which replaces *all* gateway
  components). A finer-grained "register one channel" API is desirable;
  deferred to a follow-up because `build_gateway_components` already
  accepts `extra_senders` / `extra_adapters` kwargs that the wrapper
  can route through.
* **Python client SDK** (`taskforce-client`). Outside the scope of
  this ADR. Once the REST surface stabilises around `taskforce.host`,
  generate from the OpenAPI schema.
* **Reference Dockerfile + compose snippet** for "Taskforce as
  sidecar" deployments. To be added to `docs/integration/`.
* **ADR for the broader integration patterns** (library / CLI /
  sidecar / ACP-peer trade-off matrix). Could be a separate ADR or a
  section in `docs/integrations.md` — preference for the latter so the
  matrix stays close to the user-facing setup docs.

## References

* `cli/src/taskforce_cli/commands/serve.py`
* `src/taskforce/host/__init__.py`
* `src/taskforce/api/exception_handlers.py`
* `src/taskforce/application/skill_service.py` — `register_skill_dir`
* `src/taskforce/application/profile_loader.py` — `register_config_dir` (parity reference)
* `src/taskforce/application/infrastructure_overrides.py` — re-exported override hooks
* `tests/unit/test_host.py`, `tests/unit/test_cli_serve.py`
