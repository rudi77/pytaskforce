# Taskforce Feature Spec — Index

**Generated:** 2026-05-16 (Phase A1 of spec-check rollout)
**Total features:** 27 subsystems + 3 presentation-layer = 30 specs (agent packages explicitly excluded — see below)

Each row links to its dedicated spec file under `docs/spec/<feature>.md`. Files marked as `_TODO_` haven't been written yet — Phase A3 (3 pilots) and Phase A4 (bulk).

## Status legend
- **shipped** — production-ready, in default profile or as documented opt-in
- **partial** — code exists but coverage/docs/tests incomplete
- **wip** — in active development (last commit < 2 weeks)
- **legacy** — older feature, may be slated for replacement
- **deprecated** — explicitly retired
- **enterprise** — only available with `taskforce-enterprise` plugin installed

---

## Core Framework

| # | Feature | Status | Spec | Description |
|---|---------|--------|------|-------------|
| 01 | ReAct Loop & Planning Strategies | shipped | [react-loop.md](react-loop.md) | Main agent execution engine + 4 strategies (native_react, plan_and_execute, plan_and_react, spar) |
| 02 | Context Manager | shipped | [context-manager.md](context-manager.md) | Single source of truth for LLM context (messages + tools), token budgeting, role-aware compression |
| 03 | Tool System | shipped | [tools.md](tools.md) | Native tools (~25), registry, MCP integration, approval gating, parallel execution, result store |
| 04 | Sub-Agent Orchestration | shipped | [sub-agents.md](sub-agents.md) | call_agent, call_agents_parallel, sub-agent context snapshots, ADR-015 |
| 05 | Skills System | shipped | [skills.md](skills.md) | Context/prompt/agent skill types, activation, slash-command resolution, bundled skills |
| 06 | Plugin System | shipped | [plugins.md](plugins.md) | Entry-point-based discovery (taskforce.tools, .cli_apps, .config_dirs), bundled plugins, ADR-026 |
| 07 | Profile System | shipped | [profiles.md](profiles.md) | YAML profile loading, `.agent.md` format, deployment manifest, profile auto-discovery |

## LLM & Routing

| # | Feature | Status | Spec | Description |
|---|---------|--------|------|-------------|
| 08 | LiteLLM Service | shipped | [llm-service.md](llm-service.md) | Multi-provider (OpenAI, Anthropic, Azure, Google, Ollama) via LiteLLM, retry, streaming |
| 09 | LLM Router | shipped | [llm-router.md](llm-router.md) | Dynamic per-call model selection via phase hints (planning/reasoning/acting/summarizing), ADR-012 |
| 10 | Content-Filter Recovery | shipped | [content-filter-recovery.md](content-filter-recovery.md) | Staged recovery: tool_results_only → aggressive → no_tools → rephrase, ADR-025 |

## Memory & Persistence

| # | Feature | Status | Spec | Description |
|---|---------|--------|------|-------------|
| 11 | Wiki Long-Term Memory | shipped | [wiki-memory.md](wiki-memory.md) | Markdown wiki pages, agent-curated, on-demand recall (no auto-injection), ADR-020 |
| 12 | Conversation Persistence | shipped | [conversations.md](conversations.md) | Persistent conversations (ADR-016), forking, archiving, history-cap policies |
| 13 | Settings Store | shipped | [settings-store.md](settings-store.md) | Fernet-encrypted runtime config (LLM keys, channels, OAuth), per-tenant override, hydration |

## Communication & Events

| # | Feature | Status | Spec | Description |
|---|---------|--------|------|-------------|
| 14 | Communication Gateway | shipped | [gateway.md](gateway.md) | Unified inbound/outbound for Telegram, Teams, generic webhooks, notifications, broadcast, ADR-009 |
| 15 | ChannelAskRouter | shipped | _TODO_ [channel-ask.md](channel-ask.md) | Per-channel question routing with pairing codes (`/link <code>`), opaque-recipient resolution |
| 16 | Event Sources + Scheduler | shipped | _TODO_ [events-scheduler.md](events-scheduler.md) | Polling/webhook/calendar/imap/github sources + cron/interval/one-shot scheduler |
| 17 | Standing Goals | shipped (2026-05-06) | _TODO_ [standing-goals.md](standing-goals.md) | Proactive layer that re-evaluates recurring goals on schedule, ADR-024 |

## Security & Auth

| # | Feature | Status | Spec | Description |
|---|---------|--------|------|-------------|
| 18 | OAuth2 + Auth Manager | shipped | [auth.md](auth.md) | Device + AuthCode flows, encrypted token store, provider config, credential store |
| 19 | Tool Approval Gating | shipped (2026-05-07) | _TODO_ [approval-gating.md](approval-gating.md) | Per-tool approval, profile + tenant-level bypass lists, lifecycle hooks |

## Workflows & Runtime

| # | Feature | Status | Spec | Description |
|---|---------|--------|------|-------------|
| 20 | Workflow Runtime (HITL) | shipped | _TODO_ [workflows.md](workflows.md) | Resumable multi-step orchestration with checkpoints, generative dreaming, ADR-014 |
| 21 | Cooperative Agent Interruption | shipped | _TODO_ [interruption.md](interruption.md) | Graceful cancel for mission, sub-agent, subprocess, ADR-019 |
| 22 | Agent Daemon (Generic) | shipped (2026-05-13) | _TODO_ [agent-daemon.md](agent-daemon.md) | Generic long-running agent runtime (was butler-specific, now framework), ADR-027 |
| 23 | Persistent Agent Service | shipped | _TODO_ [persistent-agent.md](persistent-agent.md) | Sessionless orchestrator with request queue, ADR-016 |

## Cross-Agent Protocols

| # | Feature | Status | Spec | Description |
|---|---------|--------|------|-------------|
| 24 | ACP Protocol | shipped (--extra acp) | _TODO_ [acp.md](acp.md) | Agent Communication Protocol for remote agent invocation, ADR-018 |

## Observability

| # | Feature | Status | Spec | Description |
|---|---------|--------|------|-------------|
| 25 | Observability | shipped (--extra tracing) | _TODO_ [observability.md](observability.md) | Phoenix tracing (OpenTelemetry) + SQLite token analytics |

## Enterprise / Multi-Tenant

| # | Feature | Status | Spec | Description |
|---|---------|--------|------|-------------|
| 26 | Multi-Tenant Runtime | shipped (enterprise) | _TODO_ [multi-tenant.md](multi-tenant.md) | org_id/user_id scoping via taskforce-enterprise plugin, per-user store overrides, ADR-022 |
| 27 | CoWork Projects | shipped (2026-05-15) | [cowork.md](cowork.md) | Per-project workspaces with project-bound conversations, project CRUD |

## Agent Packages — NOT in spec scope

Decision 2026-05-16: agent packages (Butler, Coding-Agent, RAG-Agent,
Security-Agent, SWE-Bench-Agent) are excluded from `docs/spec/*`. They
change too often (prompts, sub-agents, tools, role overlays) for the
spec-contract model — pinning them would produce constant drift noise
or force the spec to be too vague to catch anything real.

Agents still need testing and improvement, but via a different mechanism
(eval suites, live monitoring, smoke tests, `/evolve` cycles). The
specific shape of that is a separate discussion.

## API, CLI, UI (presentation layer — not separate features but separate specs for verification)

| # | Feature | Status | Spec | Description |
|---|---------|--------|------|-------------|
| 31 | REST API | shipped | _TODO_ [api.md](api.md) | FastAPI with streaming SSE, ~30+ routes, deployment-manifest-filtered agent listing |
| 32 | Unified CLI | shipped | _TODO_ [cli.md](cli.md) | taskforce_cli with auto-discovery of agent packages (butler, coding, rag) via entry-points |
| 33 | Web UI (Bundled) | shipped (recent) | _TODO_ [web-ui.md](web-ui.md) | React SPA: Chat, Projects, Workflows, Settings (5 tabs), Monitoring, Agents, Tools, ACP |

---

## Coverage targets (after Phase A4)

| Status | Now | Target |
|---|---|---|
| Specced (file exists, sections filled) | 0/33 | 33/33 |
| Verifiable mechanically (file/route/registry checks) | — | ≥80% of items per spec |
| Has at least one `@pytest.mark.spec("<feature>.<item>")` test | — | ≥1 per spec |
| Behavior-invariants documented | — | ≥3 per user-facing feature |

## Explicitly NOT in spec scope

Resolved 2026-05-16: the spec covers the **system** (contracts, invariants), not every concrete instance plugged into it. The following are out of scope at every level — no own spec, no sub-section, no listing:

- **Google Workspace tools** (gmail/google_drive/calendar) — concrete tool instances; `tools.md` covers the tool system contract, not each tool
- **Security Agent profile** (`agents/security-agent/`) — example profile, not a subsystem
- **SWE-Bench Agent profile** (`agents/swe-bench-agent/`) — eval profile, not a subsystem
- **Bundled skills** (code-review, evolve, skill-creator, pdf-processing, ...) — concrete skill instances; `skills.md` covers the skill system
- **Bundled plugins** (`ap_poc_agent`, `document_extraction_agent`) — example plugins; `plugins.md` covers the plugin system
- **Standalone MCP servers** (`servers/document-extraction-mcp/`) — concrete MCP server; `tools.md` covers the MCP integration contract

Rule of thumb for what gets a spec: if it disappeared or broke silently, would a regression-check need to catch that contractually? If yes → spec. If no → out of scope.

## Spec file naming convention

- Lowercase kebab-case: `react-loop.md`, `channel-ask.md`, `agent-butler.md`
- Prefix `agent-` for agent-package specs
- No prefix for framework features
- One file per row above
