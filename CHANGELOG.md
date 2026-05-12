# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

After v0.2.0 the project is in a stabilization phase: bug fixes, hardening,
and test coverage only. New features are deferred.

### Fixed

- **Telegram inbound resolves per-(tenant, user) instead of one
  hard-coded recipient (#162).** Adds a ``ChannelLinkRegistryProtocol``
  seam, a file-based default
  (``<work_dir>/channel_links/<channel>.json``), and a
  ``/link <code>`` command intercepted by the gateway before the
  recipient resolver. New
  ``POST /api/v1/gateway/{channel}/link-codes`` mints a short-lived
  single-use code for the authenticated caller; the user pastes it
  into the channel, the gateway records the persistent link, and
  from then on ``_PassthroughRecipientResolver`` surfaces the
  linked ``user_id`` as the recipient (plus ``tenant_id`` in
  ``RecipientInfo.attributes``). ``DELETE
  /api/v1/gateway/{channel}/links/me`` revokes a pairing.
  ``set_channel_link_registry_override`` lets enterprise plugins
  back the registry with a tenant-scoped postgres store without
  touching the resolver. Single-tenant builds are bit-for-bit
  unchanged when no code is ever minted.

- **Narrow broad `except Exception` in 3 override consumers (#222).**
  ``parallel_agent_tool._resolve_result_dir``,
  ``file_storage._default_root`` + ``get_file_storage``, and the
  butler ``email_tool._resolve_seen_path`` previously caught every
  exception from the override lookup and logged at WARNING. A
  rename regression inside the framework would therefore silently
  revert per-(tenant, user) routing to flat buckets, with only a
  per-call warning that operators are unlikely to spot. Each
  consumer now separates ``ImportError`` (older framework lacking
  the hook — fall back silently) from any other exception (logged
  at ERROR with traceback, then fall back). New unit tests pin both
  branches.

- **Documented unbounded per-scope FileStorage cache (#218).** The
  module header of ``src/taskforce/application/file_storage.py``
  now explicitly states that ``_storage_by_root`` has no eviction
  policy and that ``reset_file_storage()`` is the sanctioned drop
  path. Matches the existing wording in
  ``TenantScopedStoreFactory``; LRU eviction is tracked as a
  framework-wide follow-up.

- **Per-user routing for `ParallelAgentTool` results + `FileStorage`
  uploads (#212).** Two new framework override hooks let plugins
  route the tool-side persistence paths per request scope without
  forking framework code:
  - ``set_sub_agent_result_dir_override`` — ``ParallelAgentTool``
    consults the override at write-time (inside ``_compact_result``)
    so process-shared tool instances still route per-(tenant, user).
    Falls back to ``<work_dir>/sub_agent_results`` when no override
    is installed.
  - ``set_upload_storage_dir_override`` — ``get_file_storage()`` now
    caches one ``FileStorage`` instance per resolved root, so each
    scope keeps its own SQLite index. The env-var ``TASKFORCE_UPLOADS_DIR``
    keeps working for single-tenant ops; the override always wins
    over it so per-user routing cannot be silently overridden.
  Standalone single-tenant behaviour is bit-for-bit unchanged
  (override unset → singleton cache); paired with the enterprise
  plugin's wiring PR every per-(tenant, user) deployment gets clean
  upload + sub-agent-result separation.

- **Butler `gmail_seen.json` per-user routing (#213).** The butler
  Gmail tool previously kept a single ``.taskforce/gmail_seen.json``
  shared across every user in every tenant — fine for single-user
  dev, a privacy gap in multi-user butler deployments. New framework
  override hook
  ``taskforce.application.infrastructure_overrides.set_butler_state_dir_override``
  lets plugins route the butler agent-package state directory per
  request scope; the enterprise plugin wires it to
  ``tenants/{tid}/users/{uid}/butler/``. Standalone default moved
  from top-level ``.taskforce/gmail_seen.json`` to grouped
  ``.taskforce/butler/gmail_seen.json`` so a future
  ``calendar_last_check.json`` etc. sits alongside. Legacy top-level
  ``gmail_seen.json`` files are abandoned (no migration); the seen-id
  tracking simply restarts.

## [0.2.0] - 2026-05-06

This release closes ADR-022 (Multi-Tenant Enterprise Runtime). All seven
slices are implemented end-to-end. The framework remains tenant-unaware
and bit-for-bit identical to v0.1.x in single-tenant builds; multi-tenancy
lives entirely in `taskforce-enterprise` via the seams added here.

### Added

- **First-class workflow definitions (ADR-022 §7).** A workflow names the
  participating agents, the trigger (manual/chat/schedule/event/webhook),
  and the orchestration topology (sequence / fan-out + join via
  `depends_on` / ACP-mediated steps). Definitions persist as YAML per
  tenant under `tenants/<tid>/workflows/definitions/`.
  - REST: `GET/POST /api/v1/workflows/definitions`,
    `GET/DELETE /api/v1/workflows/definitions/{id}`,
    `POST /api/v1/workflows/definitions/{id}/run`,
    `POST /api/v1/workflows/webhooks/{trigger_path}` with HMAC verification.
  - Independent steps in the same dependency level run in parallel via
    `asyncio.gather` (G6).
  - Schedule triggers auto-register a `ScheduleJob` with
    `ScheduleActionType.EXECUTE_WORKFLOW`; the scheduler dispatcher
    re-enters the workflow runtime when the cron tick fires (G3, G4).
  - `@workflow_name` mentions in chat resolve to chat-triggered
    workflows in the gateway (G5).
  - Steps may target a remote ACP peer via `acp_peer`; the cross-tenant
    authorizer still applies (G7).
- **Workflow management UI** at `/workflows`. Full CRUD + run from the
  browser, with editor for trigger config (cron, webhook path + HMAC
  signature header/algo) and steps. After save the page surfaces the
  registered `scheduled_job_id` and the resolved webhook URL.
- **Tenant-aware Communication Gateway (ADR-022 §4).**
  `RecipientResolverProtocol` resolves channel-specific identities to
  `(tenant_id, user_id)`; `@agent_name` routing dispatches inbound
  messages to one of several agents owned by the resolved user;
  outbound senders, `send_notification`, and broadcast all carry
  `tenant_id`. Per-call `components_provider` ensures the right
  per-tenant recipient registry / outbound senders are consulted on
  every outbound send (G1).
- **Per-agent isolated workspace (ADR-022 §4).**
  `WorkspaceContextProtocol` plumbs a workspace root into `BaseTool`;
  filesystem and shell tools resolve relative paths against
  `${WORK_DIR}/tenants/<tid>/agents/<aid>/workspace/` and reject `..`
  traversal.
- **Sandboxed tool execution seam (ADR-022 §5).**
  `SandboxedExecutorProtocol` defines the contract for executing
  dangerous tools (bash/shell/powershell/python) in a sandbox. The
  framework ships an in-process executor and a hard startup warning
  when a multi-tenant runtime has no sandboxed executor wired. The
  container-backed implementation is deferred to enterprise.
- **Generalised scheduler (ADR-022 §6).** Job-store contract grows
  `tenant_id` and `agent_id`; the `schedule` tool moved into the
  framework so any agent — not just the Butler — can register
  recurring jobs that run as that agent in that tenant. Custom job
  stores can be injected.
- **Skills hot-reload + dynamic skill directories.** `SkillService`
  watches the filesystem so a skill written into a tenant's skills
  directory becomes available without restart. Skill write moved
  behind an enterprise admin route (G10).
- **Tenant-scoped ACP peers + cross-tenant authorizer.** Peer
  registries partition by tenant; cross-tenant ACP calls require an
  installable authorizer to grant `acp:peer:cross_tenant`.
- **`TenantResolverProtocol` seam.** `get_current_tenant_id()`
  resolves the active tenant from a `ContextVar`; framework-only
  builds always return `"default"`.
- **`taskforce.host` integration API and `taskforce serve` CLI**
  (ADR-023). Embeds Taskforce in host applications with a clean
  module boundary.
- **Login screen and 401 redirect** in the UI shell.
- **Custom-agent picker per chat conversation** in the UI.
- **`skill-creator` skill** plus runtime hardening for hot-reloaded
  skills.

### Changed

- **ADR-022 boundary table for Workflows corrected.** Workflow CRUD
  and the authoring UI live in `taskforce` (core); enterprise only
  layers tenant-scoping, RBAC, role-gated approval steps, and audit
  on top.
- **Gateway conversation store renamed and moved on disk.** The
  Communication Gateway's `FileConversationStore` is now
  `GatewayConversationStore` and writes to
  `.taskforce/gateway_sessions/{channel}/{conversation_id}.json`
  instead of `.taskforce/conversations/{channel}/{conversation_id}.json`.
  This removes a name/path collision with the persistence-layer
  `FileConversationStore` (ADR-016). The corresponding in-memory class
  is `InMemoryGatewayConversationStore`.
  - **Migration:** existing channel-to-session mappings under
    `.taskforce/conversations/{channel}/` are not auto-migrated. To
    preserve them, move the files:
    `mv .taskforce/conversations/{channel} .taskforce/gateway_sessions/{channel}`.
    Otherwise the gateway will mint new sessions on next inbound
    message.
- **Enterprise UI plugin moved out** to the
  `taskforce-enterprise` sibling repository.

### Fixed

- **Communication Gateway is now wired during lifespan startup** so
  workflow runs (and any route that doesn't `Depends(get_gateway)`)
  build agents whose `send_notification` tool actually has a gateway
  reference.
- **Scheduler job ids are Windows-safe.** Workflow-derived job ids
  use `__` as separator instead of `:`, which NTFS reserves for
  alternate-data-streams and which crashed `os.replace` during the
  temp-file swap with WinError 87.
- **Butler → coding-agent skill creation works on Windows.**
- **OpenAPI codegen falls back to `uv run python`** and writes its
  dump script to a tempfile so cmd.exe doesn't mangle `-c "...;..."`
  on Windows.
- **ACP tool calls enforce the tenant policy** end-to-end.

### Removed

- **`FileHeartbeatStore`** (`taskforce.infrastructure.runtime`).
  Heartbeats were recorded per ReAct step but never read by
  production code, so the per-step file write produced disk churn
  without a consumer. The infrastructure builder now uses
  `InMemoryHeartbeatStore` even when `runtime.store: file` is
  configured. `FileCheckpointStore` continues to persist checkpoints
  normally; infer cross-process liveness from checkpoint mtimes if
  needed.
- **`scripts/test_enterprise_features.py`** — stale, replaced by
  proper integration tests in `taskforce-enterprise`.

## [0.1.0] - 2026-01-05

### Added

- Initial release of Taskforce multi-agent orchestration framework
- **LeanAgent** with ReAct loop execution and native tool calling
- **Planning Strategies**: NativeReAct, PlanAndExecute, PlanAndReact
- **Native Tools**:
  - File operations (read, write)
  - Shell execution (PowerShell)
  - Python code execution
  - Git and GitHub integration
  - Web search and fetch
  - Ask user for input
- **MCP Tool Integration** (stdio and SSE protocols)
- **CLI Interface** with Typer:
  - `taskforce run mission` - Execute missions
  - `taskforce chat` - Interactive chat mode
  - `taskforce tools list` - List available tools
  - `taskforce sessions` - Session management
  - `taskforce config` - Configuration management
- **REST API** with FastAPI for microservice deployment
- **Persistence**: File-based (dev) and PostgreSQL (prod) state managers
- **RAG Integration**: Azure AI Search semantic search tools
- **Observability**: Arize Phoenix tracing integration
- **Context Management**: Configurable context policies for LLM calls
- **Custom Agent Definitions**: YAML-based agent configuration

### Architecture

- Clean Architecture (Hexagonal) with four-layer separation:
  - Core: Pure domain logic and protocols
  - Infrastructure: External integrations (LLM, persistence, tools)
  - Application: Use cases and dependency injection
  - API: CLI and REST entrypoints
- Protocol-based design using Python Protocols (PEP 544)
- Async-first implementation for all I/O operations

[Unreleased]: https://github.com/rudi77/pytaskforce/compare/v0.2.0...HEAD
[0.2.0]: https://github.com/rudi77/pytaskforce/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/rudi77/pytaskforce/releases/tag/v0.1.0
