# ADR-025: Cowork-Plugin Compatibility and Managed-Agent-Cookbook Importer

## Status

Proposed — 2026-05-10

## Context

Anthropic released `claude-for-financial-services` in May 2026 as an
open-source reference, with ten end-to-end workflow agents (Pitch Agent,
Market Researcher, Earnings Reviewer, Model Builder, Meeting Prep Agent,
Valuation Reviewer, GL Reconciler, Month-End Closer, Statement Auditor, KYC
Screener) plus seven vertical skill bundles (`financial-analysis`,
`investment-banking`, `equity-research`, `private-equity`,
`wealth-management`, `fund-admin`, `operations`) and eleven MCP data
connectors (Daloopa, Morningstar, S&P Global, FactSet, Moody's, MT
Newswires, Aiera, LSEG, PitchBook, Chronograph, Egnyte).

The repository ships every agent in two forms from a single source of
truth:

1. **Cowork plugin** (`plugins/agent-plugins/<slug>/`) — Markdown + JSON,
   no build step. Self-contained: bundles the skills the agent uses.
2. **Managed-agent cookbook** (`managed-agent-cookbooks/<slug>/agent.yaml`)
   — same system prompt, same skills, deployed via
   `POST /v1/agents` for headless/long-running execution.

We want to run these agents (and the equivalent we will publish for our
own verticals — salon bookkeeping, BluDelta contract intelligence,
household documents) inside Taskforce without re-wiring profiles, skills,
tools, and schedules per vertical.

A previous draft of this ADR proposed a new first-class `AgentTemplate`
primitive with its own *Connector*, *Credential Vault*, *ContextBridge*
and *Dispatch* abstractions. None of those abstractions exist in the
Anthropic reference, and Taskforce already covers their function through
existing primitives. Re-using what is there is preferable to inventing a
parallel layer.

## Decision

Add **plugin compatibility** with the Anthropic Cowork-plugin format and a
**managed-agent-cookbook importer**, on top of Taskforce's existing
plugin/profile/skill/MCP/butler infrastructure.

Three thin adapter components are introduced. No new core primitives, no
new credential vault, no new context-bridge, no new dispatch endpoint.

### Relationship to the existing `agent_templates.py`

`src/taskforce/application/agent_templates.py` and
`/api/v1/agent-templates` already exist with five hardcoded UI-wizard
starters (`_BUCHHALTER`, `_HANDWERKER`, `_ASSISTENT`, `_RECHERCHE`,
`_BLANK`). They are starting points for the *Create Custom Agent* wizard
and remain unchanged. The mechanism described here deliberately uses
**Cowork-plugin** (interactive path) and **managed-agent-cookbook**
(scheduled / Butler path) as the names, mirroring the Anthropic source
terminology and avoiding any rename of the existing wizard API.

## Architecture

### 1. Cowork-Plugin Importer

A new module `src/taskforce/application/cowork_plugin_importer.py`
ingests an Anthropic-style Cowork plugin (directory or Git URL) and
produces a Taskforce plugin layout that the existing `PluginLoader`
already understands.

Mapping:

| Cowork plugin element | Taskforce target | Reuses |
| --- | --- | --- |
| `plugins/<slug>/agents/<slug>.md` (system prompt + bundled skills + frontmatter) | `.agent.md` profile | `ProfileLoader` (`application/profile_loader.py`), `agent_file_loader.py` |
| `plugins/<slug>/skills/*/SKILL.md` (context skills) | Skill of type `context` | `FileSkillRegistry`, `SkillParser` (`infrastructure/skills/`) |
| `plugins/<slug>/commands/*.md` (slash commands like `/comps`, `/dcf`, `/ic-memo`) | Skill of type `prompt` | same `FileSkillRegistry`; `prompt`-type skills are exactly Cowork's slash-command shape |
| `plugins/<slug>/.mcp.json` (MCP server URLs) | `mcp_servers:` block on the imported profile | `MCPConnectionManager`, `MCPClient` (`infrastructure/tools/mcp/`) |
| MCP auth tokens (`API_KEY`, OAuth) | env vars or existing token store | `EncryptedTokenStore` (`infrastructure/auth/encrypted_token_store.py`) |

CLI surface:

```bash
taskforce plugin import-cowork <path-or-git-url>   # writes to plugins/<slug>/
taskforce plugin import-cowork --vertical investment-banking <path>
```

The importer is a file-shape transformer; it does not introduce a new
runtime concept. After import, the plugin is loadable by the existing
`PluginLoader` (`application/plugin_loader.py`) and the resulting profile
is selectable with `--profile <slug>` like any other.

### 2. Managed-Agent-Cookbook Importer

A new module
`src/taskforce/application/managed_cookbook_importer.py` reads an
Anthropic `managed-agent-cookbooks/<slug>/agent.yaml` (orchestrator +
leaf-worker subagents + steering examples) and produces:

- a Taskforce profile for the orchestrator + per-subagent profiles under
  `agents/<package>/configs/custom/`,
- a `WorkflowDefinition` that the existing
  `WorkflowRuntimeService` (`application/workflow_runtime_service.py`)
  can run on demand, on a schedule, or via webhook,
- optional Butler trigger-rule entries when the cookbook declares
  schedule-driven activation.

Mapping:

| `agent.yaml` element | Taskforce target | Reuses |
| --- | --- | --- |
| Orchestrator system prompt + tools | `.agent.md` profile | `ProfileLoader` |
| `callable_agents` (subagent delegation, currently a Claude API research preview) | `call_agents_parallel` invocations | `SubAgentSpawner` (`application/sub_agent_spawner.py`), `ParallelAgentTool` (`infrastructure/tools/orchestration/parallel_agent_tool.py`) |
| Leaf-worker subagents (depth-1) | Sub-profiles in `configs/custom/` | `coding_agent`-style sub-agent layout (`agents/coding-agent/configs/custom/`) |
| Steering events / handoff requests | ACP messages or direct sub-agent calls | `infrastructure/acp/acp_message_bus.py`, `acp_server.py` |
| Long-running session | Persistent agent + Butler daemon | `PersistentAgentService` (`application/persistent_agent_service.py`), `ButlerDaemon` (`agents/butler/src/taskforce_butler/daemon.py`) |
| Schedule trigger | `WorkflowDefinition` with `trigger: schedule` | `SchedulerService` (`infrastructure/scheduler/scheduler_service.py`) |
| HITL approval gate | Existing wait/resume API | `WorkflowCheckpointStore` (`infrastructure/runtime/workflow_checkpoint_store.py`), `/api/v1/workflows/wait,resume,resume-and-continue` |
| Out-of-band approval (Telegram/Teams/email) | Communication Gateway | `CommunicationGateway` (`application/gateway.py`), `api/routes/gateway.py` |

CLI surface:

```bash
taskforce cookbook import <path>                   # imports a managed-agent-cookbook
taskforce cookbook import <path> --schedule "0 9 * * 1"   # also wires a scheduled trigger
```

### 3. Vertical-Plugin Convention (file layout)

Anthropic groups skills + commands + MCP configs by vertical (`investment-
banking`, `equity-research`, `fund-admin`, `operations`, …). The existing
Taskforce plugin layout already supports that; this ADR only documents
the convention so vertical bundles stay consistent across imports and
in-house additions:

```
examples/<vertical>/                  # or agents/<package>/
├── skills/                           # context skills
├── commands/                         # prompt-type skills (slash commands)
└── .mcp.json                         # vertical-scoped MCP connectors
```

A future `taskforce-financial-services` agent package under
`agents/financial-services/` can ship the imported Anthropic verticals
end-to-end, analogous to `taskforce-butler`, `taskforce-rag-agent`, and
`taskforce-coding-agent`.

## Explicitly Out of Scope

The earlier draft introduced abstractions that turned out to have no
counterpart in the Anthropic reference and no missing capability in
Taskforce. Each is dropped from this ADR; if a real need surfaces later,
it gets its own ADR.

- **Connector as a separate primitive from Tool.** Anthropic's eleven
  data integrations are MCP servers. Taskforce already supports MCP via
  `infrastructure/tools/mcp/`. Office and RAG tools stay as native tools.
- **Credential Vault with scoped, time-bounded issuance and audit log.**
  MCP servers handle their own provider auth ("MCP access may require a
  subscription or API key from the provider"). The existing
  `EncryptedTokenStore` (Fernet-based) covers the cases where Taskforce
  itself has to hold a credential. AES-GCM upgrade can happen separately
  if a compliance driver appears.
- **`ContextBridge` with typed cross-tool artifacts** (`FinancialModel`,
  `DeckOutline`, …). Not present in the source repository. Cowork carries
  cross-app context through its chat surface; managed runs carry it
  through the `/v1/agents` event loop. Workflow checkpoints already
  persist intermediate state when Taskforce-side persistence is needed.
- **Dispatch API** (`POST /api/v1/dispatch`). The existing
  Communication-Gateway routes (`/api/v1/gateway/{channel}/messages`,
  `/api/v1/gateway/notify`) cover the assistive dispatch case;
  `/api/v1/workflows/definitions/{id}/run` and the webhook trigger cover
  the managed dispatch case. No new endpoint is needed.
- **Marketplace with signed templates.** Anthropic distributes via Git
  URL or zip upload. Same is good enough for us; signing is future work.

## Consequences

### Positive

- One canonical way to ingest any Cowork-shaped vertical agent
  (Anthropic-published or partner-published) into Taskforce, with no
  per-vertical wiring.
- Both Anthropic deployment paths map cleanly onto existing Taskforce
  primitives: assistive ⟶ profile + plugin + Communication Gateway,
  managed ⟶ profile + `WorkflowDefinition` + Butler/Scheduler.
- The 11 FSI MCP connectors come for free — Taskforce already speaks
  MCP. No new client code.
- The salon-bookkeeping, BluDelta-contract-intelligence and
  household-documents verticals can be packaged by the same convention
  (Section 3) without waiting on a marketplace.
- No new abstraction layer to maintain. The blast radius of this ADR is
  two new application modules and one CLI subcommand group each.

### Negative

- The importers are format adapters; they will need maintenance as
  Anthropic evolves the Cowork plugin spec or `agent.yaml` schema. Lock
  the supported version explicitly and surface a clear error on
  mismatch.
- Slash commands imported as `prompt`-type skills go through Taskforce's
  skill router, not Cowork's. Expect minor differences in argument
  handling around `$ARGUMENTS` semantics — covered by tests on import.
- Some Cowork plugin features (e.g. Cowork-specific UI affordances) have
  no Taskforce equivalent and will be silently no-ops on import. Document
  the unsupported subset in the importer's `--help`.

### Risks

- **MCP-server auth drift.** Each provider has its own auth model. We
  rely on each MCP server respecting the auth token Taskforce hands it
  via env or `EncryptedTokenStore`. Mitigation: per-connector smoke tests
  during import (`taskforce plugin lint`).
- **`callable_agents` (Anthropic preview API) semantics.** Subagent
  delegation is a research preview on the Claude side. Mapping to
  `call_agents_parallel` is a structural translation; if the preview
  semantics change, the cookbook importer must be revisited. Mitigation:
  pin the supported `agent.yaml` schema version.

## Alternatives Considered

1. **Stay with profiles + plugins, document the patterns.**
   Rejected — without an importer, every Anthropic-published vertical
   would need manual transcription. Friction defeats the purpose.

2. **Introduce a new `AgentTemplate` primitive with its own Connector
   and Credential-Vault layer (the previous draft).**
   Rejected — none of those abstractions exist in the Anthropic source
   we want to consume. Building a parallel layer would duplicate
   `PluginLoader`, `ProfileLoader`, MCP, and `EncryptedTokenStore`.

3. **Mirror Anthropic's repo structure verbatim under
   `taskforce/plugins/agent-plugins/` and skip the importer.**
   Rejected — we still want a single Taskforce-native plugin layout so
   `taskforce-butler`, `taskforce-rag-agent`, `taskforce-financial-
   services`, and partner-built verticals are all loaded the same way.
   The importer keeps the canonical layout uniform.

## Implementation Plan

Phased rollout, all on top of existing infrastructure.

- **Phase 1 (~3–5 days)** — `cowork_plugin_importer.py` + CLI subcommand
  + tests. Reference imports: `pitch-agent` and `gl-reconciler` from
  `claude-for-financial-services`. Lint command
  (`taskforce plugin lint`) that validates the imported plugin loads
  cleanly under `PluginLoader` and that all referenced MCP servers
  resolve.

- **Phase 2 (~3–5 days)** — `managed_cookbook_importer.py` + CLI
  subcommand + tests. Reference import: `gl-reconciler` cookbook,
  including a scheduled trigger via `WorkflowDefinition`. Verify that
  HITL gates surface through `/api/v1/workflows/wait,resume`.

- **Phase 3 (~3 days, optional)** —
  `agents/financial-services/` agent package shipping the imported
  vertical bundles end-to-end, analogous to `taskforce-butler`. New
  `--extra fsi` group in `pyproject.toml` for any additional Python
  dependencies (e.g. PDF / table extraction libraries some verticals
  need).

- **Phase 4 (ongoing)** — extend the importer as Anthropic ships new
  verticals; build the same convention out for our own verticals (salon
  bookkeeping, BluDelta contract intelligence, household documents).

## References

- [ADR-009 — Unified Communication Gateway](adr-009-communication-gateway.md)
- [ADR-010 — Event-Driven Butler Agent](adr-010-event-driven-butler-agent.md)
- [ADR-011 — Unified Skills System](adr-011-unified-skills-system.md)
- [ADR-014 — Resumable Human-in-the-Loop Workflows](adr-014-resumable-human-in-the-loop-workflows.md)
- [ADR-015 — Parallel Sub-Agent Execution](adr-015-parallel-sub-agent-execution.md)
- [ADR-016 — Persistent Agent Architecture](adr-016-persistent-agent-architecture.md)
- [ADR-017 — Butler Role Specialization](adr-017-butler-role-specialization.md)
- [ADR-018 — Agent Communication Protocol Support](adr-018-acp-protocol-support.md)
- [ADR-022 — Multi-Tenant Enterprise Runtime](adr-022-multi-tenant-enterprise-runtime.md)
- [ADR-023 — Host Integration API](adr-023-host-integration-api.md)
- [ADR-024 — Standing Goals](adr-024-standing-goals.md)
- Anthropic, [Claude for Financial Services](https://github.com/anthropics/claude-for-financial-services) (2026-05-05) — reference architecture pattern and dual-mode deployment.
- `docs/features/skills.md`
- `docs/plugins.md`
- `docs/architecture/multi-agent-orchestration-plan.md`
