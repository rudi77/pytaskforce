# CLAUDE.md - Taskforce Development Guide

**Version:** 1.7
**Date:** 2026-04-19
**Purpose:** Guide for AI-assisted development with Claude Code

---

## Project Overview

**Taskforce** is a production-ready multi-agent orchestration framework built with Clean Architecture principles. It provides autonomous AI agents that plan and execute complex tasks through LLM-driven reasoning (ReAct loop), TodoList decomposition, and extensible tool execution.

### Key Characteristics

- **Architecture:** Clean Architecture (Hexagonal) with strict four-layer separation
- **Language:** Python 3.11+ (also supports 3.12)
- **Package Manager:** `uv` (NOT pip/venv) - **This is mandatory**
- **Build Backend:** Hatchling
- **Deployment Modes:**
  - CLI (Typer + Rich + Textual) for local development
  - REST API (FastAPI) for production microservices
- **Persistence:** File-based (dev) or PostgreSQL (prod) via swappable adapters
- **LLM Integration:** Multi-provider (OpenAI, Anthropic, Google, Azure, Ollama, etc.) via LiteLLM
- **Extensibility:** Plugin system, skills (context/prompt/agent types), MCP tool servers
- **Packaging:** Multi-package monorepo — lean core framework plus optional agent packages
  (`taskforce-butler`, `taskforce-coding-agent`, `taskforce-rag-agent`) and a unified CLI
  (`taskforce-cli`) that wires them together.

### Repository Layout

```
pytaskforce/
├── src/taskforce/          # Core framework package (LLM-agnostic, no agent-specific code)
├── cli/src/taskforce_cli/  # Unified CLI entry point (discovers installed agent packages)
├── agents/                 # Optional agent packages (each with its own pyproject.toml)
│   ├── butler/             # taskforce_butler — event-driven daemon, scheduler, rules
│   ├── coding-agent/       # taskforce_coding_agent — epic orchestration, sub-agents
│   ├── rag-agent/          # taskforce_rag_agent — Azure AI Search tools
│   ├── security-agent/     # taskforce security profile
│   └── swe-bench-agent/    # SWE-Bench evaluation profile
├── packages/               # Internal auxiliary packages (autooptim, etc.)
├── cli/                    # Unified CLI package source
├── servers/                # Standalone MCP servers (document-extraction-mcp, ...)
├── examples/               # Example agents (accounting, customer support)
├── docs/                   # Markdown documentation
└── tests/                  # Framework tests (agent packages have their own tests/)
```

The `taskforce` distribution remains installable on its own and only depends on the
framework code in `src/taskforce/`. Agent packages opt in additional capabilities and
are discovered by the unified CLI via Python imports at startup.

---

## Documentation Structure

Documentation is maintained **as Markdown in-repo**. Canonical entry points:

| Location | Purpose |
|----------|---------|
| `README.md` | Main user entry point (Quick Start, CLI + API, links into `docs/`) |
| `docs/index.md` | Docs navigation hub |
| `docs/architecture.md` | Stable architecture entry-point (links into `docs/architecture/`) |
| `docs/adr/` | Architecture Decision Records (index: `docs/adr/index.md`) |
| `docs/features/` | Feature guides (long-term memory, skills, enterprise) |
| `docs/epics/` | Epic planning and tracking documents |
| `docs/prd/` | Product Requirements Documents |
| `docs/integrations.md` | External integrations (communication providers, etc.) |
| `.github/PULL_REQUEST_TEMPLATE.md` | PR template with Clean Architecture compliance checklist |
| `.github/ISSUE_TEMPLATE/bug_report.yml` | Bug report template |
| `.github/ISSUE_TEMPLATE/feature_request.yml` | Feature request template (includes layer impact) |
| `.env.example` | Environment variable template (copy to `.env` for local setup) |

### Documentation Upkeep Rule (MANDATORY)

When code changes affect CLI/API/config behavior, **update the relevant docs pages in the same session**:

| Change Type | Update These Files |
|-------------|-------------------|
| CLI behavior | `README.md` and `docs/cli.md` |
| API routes/schemas/errors | `README.md` and `docs/api.md` |
| Config/profile changes | `docs/profiles.md` (and update example snippets) |
| Architecture changes | `docs/architecture.md` and/or `docs/architecture/` sharded pages |
| Cross-cutting decisions | Add/update an ADR in `docs/adr/` |
| Developer workflow (uv/pytest/ruff/black/mypy) | `README.md` and `docs/testing.md` |
| Integrations/communication | `docs/integrations.md` |
| Features (memory, skills) | `docs/features/` relevant page |

---

## Clean Architecture: Four-Layer Structure

Taskforce enforces strict architectural boundaries through four distinct layers:

```
src/taskforce/
├── core/                      # LAYER 1: Pure Domain Logic
│   ├── domain/                # Agent, LeanAgent, Planning, Events, Models, Dream, Workflow
│   │   ├── lean_agent_components/  # Modular agent components (context_manager, prompt_builder, …)
│   │   └── planning/          # Planning primitives (react_loop, interrupt, state, types)
│   └── interfaces/            # Protocols (29 interface files — see table below)
│
├── infrastructure/            # LAYER 2: External Integrations
│   ├── acp/                   # Agent Communication Protocol runtime/client/server/message-bus
│   ├── auth/                  # OAuth2 / token store implementations
│   ├── cache/                 # Tool result caching
│   ├── communication/         # Communication Gateway components (adapters, senders, registry)
│   ├── event_sources/         # Framework-wide event sources: polling base,
│   │                          # calendar, webhook, file_watcher, imap_email,
│   │                          # github (HMAC-verified). Auto-registered in
│   │                          # the application EventSourceRegistry.
│   ├── llm/                   # LiteLLM service + LLM Router (multi-provider, dynamic routing)
│   ├── memory/                # File-based memory store
│   ├── messaging/             # In-memory message bus
│   ├── persistence/           # File state manager, agent/conversation registries
│   ├── runtime/               # Runtime tracking (heartbeats, checkpoints)
│   ├── scheduler/             # SchedulerService + FileJobStore (cron / interval / one-shot)
│   ├── skills/                # Skill loading, parsing, registry (context/prompt/agent types)
│   ├── tools/
│   │   ├── native/            # Native tools (see "Native Tools" section)
│   │   ├── mcp/               # MCP server connections (client, connection_manager, wrapper)
│   │   ├── orchestration/     # Sub-agent, parallel-agent, ACP-agent tools
│   │   ├── base_tool.py       # BaseTool convenience class
│   │   ├── filters.py         # Tool filtering helpers
│   │   ├── registry.py        # Short-name → tool spec registry
│   │   └── wrappers.py        # Tool wrappers (approval, caching)
│   └── tracing/               # Phoenix tracing integration
│
├── application/               # LAYER 3: Use Cases & Orchestration
│   ├── factory.py             # Dependency injection (central wiring)
│   ├── executor.py            # Execution orchestration (streaming-first)
│   ├── tool_registry.py       # Tool catalog, mapping, resolution
│   ├── tool_builder.py        # Tool instantiation from definitions
│   ├── agent_registry.py      # Custom agent registration API
│   ├── event_source_registry.py    # Plugin registry for event sources
│   │                          # (name → factory, used by butler daemon)
│   ├── agent_creation_pipeline.py  # Agent build pipeline (definition → agent)
│   ├── config_schema.py       # Pydantic schema helpers for configs
│   ├── gateway.py             # Unified Communication Gateway service
│   ├── profile_loader.py      # Profile YAML loading and resolution
│   ├── system_prompt_assembler.py # System prompt composition
│   ├── intent_router.py       # Intent routing for chat
│   ├── skill_manager.py       # Skill lifecycle management
│   ├── skill_service.py       # Skill service (discovery, slash-command resolution)
│   ├── plugin_loader.py       # Plugin loading and discovery
│   ├── infrastructure_builder.py  # Infrastructure setup
│   ├── sub_agent_spawner.py   # Sub-agent session spawning
│   ├── conversation_manager.py # Persistent conversation lifecycle (ADR-016)
│   ├── persistent_agent_service.py # Persistent orchestrator runtime (ADR-016)
│   ├── channel_ask_router.py  # Channel-based user question routing
│   ├── learning_service.py    # Post-mission knowledge extraction → wiki
│   ├── workflow_runtime_service.py # Resumable HITL workflow runtime (ADR-014-hitl)
│   ├── auth_manager.py        # OAuth2 manager
│   ├── planning_strategy_factory.py # Planning strategy wiring
│   ├── request_queue.py       # Request buffering for sessionless orchestrator
│   ├── topic_detector.py      # Conversation topic detection
│   ├── token_analytics_facade.py / tracing_facade.py  # Facade helpers
│   ├── progress_update_builder.py / execution_error_handler.py  # Streaming helpers
│   └── acp_service.py         # ACP application service (ADR-018)
│
├── api/                       # LAYER 4: Entrypoints
│   ├── server.py              # FastAPI application
│   ├── cli/
│   │   ├── main.py            # Framework-only CLI (falls back when taskforce_cli is missing)
│   │   ├── simple_chat.py     # Interactive chat interface
│   │   ├── output_formatter.py # Rich output formatting
│   │   └── commands/          # Framework CLI subcommands (run, chat, tools, skills,
│   │                          # missions, conversations, config, memory, acp)
│   ├── routes/                # FastAPI route modules (execution, agents, sessions,
│   │                          # tools, health, gateway, workflows, conversations, …)
│   └── schemas/               # Pydantic request/response schemas
│
├── configs/                   # Framework-shipped YAML profiles
│   │                          # (default.yaml, acp_peer.yaml, llm_config.yaml,
│   │                          #  showcase_coder.yaml, showcase_orchestrator.yaml,
│   │                          #  showcase_researcher.yaml)
├── plugins/                   # Bundled plugin agents (ap_poc_agent, document_extraction_agent)
└── skills/                    # Bundled skill scripts (pdf-processing, code-review, …)
```

### Agent-Package Layout

Agent-specific code (daemons, role configs, domain-specific tools) lives under `agents/`:

```
agents/
├── butler/
│   ├── src/taskforce_butler/  # daemon.py, service.py, event_router.py, rule_engine.py,
│   │                          # learning_service.py, role_loader.py, cli/, domain/,
│   │                          # interfaces/ (butler protocols), infrastructure/
│   │                          #   (event_sources/, scheduler/, tools/)
│   └── configs/               # butler.yaml + custom/ (accountant, pc-agent, …)
│                              # + roles/ (accountant.yaml, personal_assistant.yaml)
├── coding-agent/
│   ├── src/taskforce_coding_agent/  # task_complexity_classifier.py, cli/, orchestration
│   └── configs/               # coding_agent.yaml, coding_analysis.yaml
│                              # + custom/ (coding_planner, coding_worker, coding_reviewer,
│                              #   test_engineer, doc_writer, swe_analyzer, swe_coder, …)
├── rag-agent/
│   ├── src/taskforce_rag_agent/     # RAG tools + CLI
│   └── configs/               # rag_agent.yaml
├── security-agent/            # security profile
└── swe-bench-agent/           # SWE-Bench profile
```

Each agent package ships its own `pyproject.toml`, optional CLI (`taskforce_<name>.cli`)
and, where applicable, tool implementations that the core tool registry references via
their fully-qualified module paths (e.g. `taskforce_butler.infrastructure.tools.calendar_tool`).
Without the package installed the corresponding registry entry simply fails to resolve at
tool-build time, keeping the framework usable standalone.

### Unified CLI (`cli/src/taskforce_cli/`)

`cli/src/taskforce_cli/main.py` is the top-level CLI:

- Registers framework commands (`run`, `chat`, `tools`, `skills`, `config`, `memory`, `acp`).
- Dynamically adds `taskforce butler`, `taskforce epic`, and `taskforce rag` when the
  corresponding agent packages are importable.
- `_detect_default_profile()` returns `"butler"` if `taskforce_butler` is installed,
  otherwise `"dev"`. This is why "default profile" depends on what is installed.
- `agent_discovery.register_agent_config_dirs()` adds the agent packages' `configs/`
  directories to the profile loader's search path, so `--profile butler`,
  `--profile coding_agent`, `--profile rag_agent`, etc. resolve across packages.

The fallback framework-only CLI in `src/taskforce/api/cli/main.py` is used when
`taskforce_cli` is not installed. It defaults to `--profile dev`.

### Import Rules (CRITICAL)

**Dependency Direction:** Inward only (API → Application → Infrastructure → Core)

```python
# ✅ ALLOWED
# Core layer
from taskforce.core.interfaces.state import StateManagerProtocol  # Protocol only

# Infrastructure layer
from taskforce.core.interfaces.llm import LLMProviderProtocol     # Implements protocol
from taskforce.core.domain.agent import Agent                      # Uses domain

# Application layer
from taskforce.core.domain.agent import Agent                      # Uses domain
from taskforce.infrastructure.llm.litellm_service import LiteLLMService  # Wires infrastructure

# API layer
from taskforce.application.executor import AgentExecutor          # Uses application layer

# ❌ FORBIDDEN
# Core layer - NEVER import infrastructure
from taskforce.infrastructure.persistence.file_state_manager import FileStateManager  # VIOLATION!

# Infrastructure should not import from API or Application
from taskforce.api.routes.execution import execute_mission       # VIOLATION!
```

**Layer Import Matrix:**

| Layer          | Can Import From                    | CANNOT Import From     |
|----------------|-------------------------------------|------------------------|
| Core/Domain    | `core/interfaces` ONLY              | Infrastructure, Application, API |
| Core/Interfaces| NOTHING (protocol definitions)      | Any other layer        |
| Infrastructure | `core/interfaces`, `core/domain`    | Application, API       |
| Application    | All layers                          | API                    |
| API            | Application, `core/interfaces`      | Infrastructure directly|

---

## Core Concepts

### 1. Protocol-Based Design

All layer boundaries use **Python Protocols (PEP 544)** instead of abstract base classes.

The framework's protocols live in `src/taskforce/core/interfaces/`. Event-driven
primitives (`EventSourceProtocol`, `SchedulerProtocol`, `RuleEngineProtocol`,
`LearningStrategyProtocol`) are part of the core so any agent package can reuse
them. The `ButlerProtocol` and butler-only contracts remain inside the
`taskforce_butler` agent package.

| Protocol(s) | File | Purpose |
|-------------|------|---------|
| `StateManagerProtocol` | `state.py` | Session state persistence |
| `LLMProviderProtocol` | `llm.py` | LLM provider abstraction |
| `ToolProtocol` | `tools.py` | Tool execution interface (also defines `ApprovalRiskLevel` enum) |
| `WikiStoreProtocol` | `wiki_store.py` | Wiki-style long-term memory storage (ADR-020) |
| `OutboundSenderProtocol`, `InboundAdapterProtocol`, `ConversationStoreProtocol`, `RecipientRegistryProtocol`, `RecipientResolverProtocol` | `gateway.py` | Communication Gateway contracts (incl. opaque-recipient resolution extension point) |
| `MessageBusProtocol` | `messaging.py` | Inter-agent messaging |
| `HeartbeatStoreProtocol`, `CheckpointStoreProtocol`, `AgentRuntimeTrackerProtocol` | `runtime.py` | Runtime tracking |
| `SkillProtocol`, `SkillMetadata`, `SkillRegistryProtocol`, `SkillContextProtocol` | `skills.py` | Skill interface and lifecycle (context/prompt/agent types) |
| `ToolMapperProtocol` | `tool_mapping.py` | Tool name resolution |
| `ToolResolverProtocol` | `tool_resolver.py` | Tool name → instance resolution with DI |
| `ToolResultStoreProtocol` | `tool_result_store.py` | Tool result caching |
| `SubAgentSpawnerProtocol` | `sub_agents.py` | Sub-agent spawning |
| `TenantContextProtocol`, `UserContextProtocol`, `IdentityProviderProtocol`, `PolicyEngineProtocol` | `identity_stubs.py` | Identity and tenancy management |
| `LoggerProtocol` | `logging.py` | Structured logging |
| `TokenStoreProtocol`, `AuthFlowProtocol`, `AuthManagerProtocol` | `auth.py` | OAuth2 authentication |
<!-- ADR-020 removed ConsolidationProtocol and DreamEngineProtocol: the wiki
     is curated by the agent at save-time, not by background services. -->

| `AgentStateProtocol` | `agent_state.py` | Singleton agent state persistence (ADR-016) |
| `ChannelAskProtocol` | `channel_ask.py` | Channel-based user interaction |
| `ExperienceProtocol` | `experience.py` | Session experience tracking |
| `TokenEstimatorProtocol` | `token_estimator.py` | Token counting |
| `ConversationProtocol`, `ConversationManagerProtocol` | `conversation.py` | Conversation lifecycle (ADR-016) |
| `EmbeddingsProtocol` | `embeddings.py` | Text embeddings |
| `ContextManagerProtocol`, `ContextSnapshot`, `ContextItem`, `SubAgentContextEntry` | `context_manager.py` | Unified LLM context (messages, tools, snapshots) |
| `AcpServerProtocol`, `AcpClientProtocol`, `AcpPeerRegistryProtocol`, `AcpRuntimeProtocol` | `acp.py` | Agent Communication Protocol (ADR-018) |
| `EventSourceProtocol` | `event_source.py` | External event ingestion (polling/webhook) |
| `SchedulerProtocol` | `scheduler.py` | Time-based job scheduling (cron, interval, one-shot) |
| `RuleEngineProtocol` | `rule_engine.py` | Trigger-rule evaluation against agent events |
| `LearningStrategyProtocol` | `learning.py` | Automatic knowledge extraction from conversations |

```python
# core/interfaces/state.py
from typing import Protocol, Optional, Dict, Any, List

class StateManagerProtocol(Protocol):
    """Protocol for session state persistence."""

    async def save_state(self, session_id: str, state_data: Dict[str, Any]) -> None: ...
    async def load_state(self, session_id: str) -> Optional[Dict[str, Any]]: ...
```

**Why Protocols?**
- Duck typing - any object matching the interface works
- Easier testing - no inheritance required for mocks
- More Pythonic - leverages structural subtyping

### 2. Dependency Injection via Factory

The `AgentFactory` provides a unified API with two mutually exclusive modes:

```python
# application/factory.py
from taskforce.application.factory import AgentFactory

factory = AgentFactory()

# Option 1: Config file (for predefined agents)
agent = await factory.create_agent(config="dev")
agent = await factory.create_agent(config="src/taskforce/configs/custom/coding_worker.yaml")

# Option 2: Inline parameters (for programmatic creation)
agent = await factory.create_agent(
    system_prompt="You are a helpful coding assistant.",
    tools=["python", "file_read", "file_write"],
    persistence={"type": "file", "work_dir": ".taskforce_coding"},
    max_steps=20,
)

# ERROR: Cannot mix both modes
# agent = await factory.create_agent(config="dev", tools=["python"])  # ValueError!
```

**Rules:**
- `config` and inline parameters are **mutually exclusive**
- If `config` provided → all settings loaded from YAML file
- If inline parameters → settings from parameters (with sensible defaults)

### 3. Planning Strategies

Four planning strategies are available, configured via `agent.planning_strategy` in profile YAML:

| Strategy | Value | Description |
|----------|-------|-------------|
| **Native ReAct** | `native_react` | Default. Pure ReAct loop - Thought → Action → Observation cycle |
| **Plan and Execute** | `plan_and_execute` | Creates a plan first, then executes steps sequentially |
| **Plan and React** | `plan_and_react` | Hybrid - creates plan, uses ReAct within each step |
| **SPAR** | `spar` | Structured Sense → Plan → Act → Reflect cycle with iterative refinement |

```yaml
# Profile YAML
agent:
  planning_strategy: spar  # or native_react, plan_and_execute, plan_and_react
  planning_strategy_params:
    max_step_iterations: 3
    max_plan_steps: 12
    reflect_every_step: true
```

**Implementation:** `src/taskforce/core/domain/planning_strategy.py`

### 4. ReAct Loop (Reason + Act)

The core agent execution pattern:

```
┌─────────────────────────────────────────┐
│  1. THOUGHT (LLM Reasoning)             │
│     "I need to read the file first..."  │
└──────────────┬──────────────────────────┘
               │
               ▼
┌─────────────────────────────────────────┐
│  2. ACTION (Tool Selection)             │
│     tool: FileReadTool                  │
│     params: {path: "data.json"}         │
└──────────────┬──────────────────────────┘
               │
               ▼
┌─────────────────────────────────────────┐
│  3. OBSERVATION (Result)                │
│     {content: "...", success: true}     │
└──────────────┬──────────────────────────┘
               │
               ▼ (repeat until mission complete)
```

### 5. Context Management

The `ContextManager` (`core/domain/lean_agent_components/context_manager.py`) is the single source of truth for the full LLM context. It owns the mutable `messages` list and coordinates context preparation before each LLM call.

**Key methods:**
- `initialize(mission, state, base_system_prompt)` — builds initial messages from conversation history
- `restore(messages)` — restores from a paused execution (ask_user resume)
- `prepare_for_llm(mission, state)` — orchestrates system prompt rebuild + compression + preflight check
- `append_message(msg)` — appends tool results, nudges, circuit breakers
- `snapshot(include_content, skill_manager, memory_context)` — builds `ContextSnapshot` for `/tree` and `/write-tree`
- `register_sub_agent_context(specialist, session_id, snapshot)` — captures sub-agent context before close

**Protocol:** `ContextManagerProtocol` in `core/interfaces/context_manager.py`

**Value objects:** `ContextSnapshot`, `ContextItem`, `SubAgentContextEntry` (frozen dataclasses)

### 6. Domain Enums

All status values, event types, and action constants are defined in `core/domain/enums.py` to eliminate magic strings:

- `ExecutionStatus` - completed, failed, pending, paused
- `TaskStatus` - PENDING, DONE
- `EventType` - started, step_start, llm_token, tool_call, tool_result, ask_user, plan_updated, complete, error, etc.
- `LLMStreamEventType` - token, tool_call_start, tool_call_delta, tool_call_end, done
- `PlannerAction` - create_plan, mark_done, read_plan, update_plan
- `LLMAction` - tool_call, respond, ask_user
- `MessageRole` - user, assistant, system, tool

### 7. Error Handling

Execution API errors use a standardized payload (`code`, `message`, `details`, optional `detail`) via `ErrorResponse`, with responses emitted from `HTTPException` objects tagged by the `X-Taskforce-Error: 1` header.

Exception types live in `src/taskforce/core/domain/errors.py` (`TaskforceError`, `LLMError`, `ToolError`, etc.). Infrastructure tools should convert unexpected failures into `ToolError` payloads via `tool_error_payload`.

### 8. Dynamic LLM Routing

The **LLM Router** (`infrastructure/llm/llm_router.py`) wraps `LLMProviderProtocol` and routes each LLM call to a different model based on configurable rules. Planning strategies emit **phase hints** as the `model` parameter:

| Phase Hint | Emitted By | Typical Model |
|------------|-----------|---------------|
| `planning` | `_generate_plan()` | Strong reasoning model |
| `reasoning` | `NativeReActStrategy` main loop | Strong reasoning model |
| `acting` | `PlanAndExecuteStrategy`, `SparStrategy` act phase | Standard model |
| `reflecting` | `SparStrategy` reflect / `_run_reflection_cycle()` | Strong reasoning model |
| `summarizing` | `_stream_final_response()` | Fast/cheap model |

Routing rules are configured in `llm_config.yaml` (alongside model aliases):

```yaml
routing:
  enabled: true
  default_model: main
  rules:
    - condition: "hint:planning"
      model: powerful
    - condition: "hint:summarizing"
      model: fast
    - condition: has_tools
      model: main
```

When routing is disabled (default), the router transparently maps all hints back to `default_model` — fully backward-compatible.

**Implementation:** `LLMRouter` (Decorator pattern) → `LiteLLMService` → LiteLLM → Provider APIs

**ADR:** `docs/adr/adr-012-dynamic-llm-selection.md`

---

## Tools

The tool registry (`src/taskforce/infrastructure/tools/registry.py`) maps short
names to tool classes. Some entries resolve to classes in agent packages
(`taskforce_butler`, `taskforce_rag_agent`) — those are only available when the
corresponding package is installed.

### Framework-native tools (ship with core `taskforce`)

| Short Name | Class | Module (under `taskforce.infrastructure.tools.native.`) | Description |
|------------|-------|----------------------------------------------------------|-------------|
| `activate_skill` | ActivateSkillTool | `activate_skill_tool` | Runtime skill activation |
| `web_search` | WebSearchTool | `web_tools` | DuckDuckGo web search |
| `web_fetch` | WebFetchTool | `web_tools` | HTTP requests, web crawling |
| `python` | PythonTool | `python_tool` | Python code execution (isolated namespace) |
| `file_read` | FileReadTool | `file_tools` | Read file contents |
| `file_write` | FileWriteTool | `file_tools` | Write file contents |
| `git` | GitTool | `git_tools` | Git CLI operations |
| `github` | GitHubTool | `git_tools` | GitHub API operations |
| `shell` | ShellTool | `shell_tool` | Platform-agnostic shell execution |
| `bash` | BashTool | `shell_tool` | Bash-specific shell execution |
| `powershell` | PowerShellTool | `shell_tool` | Windows PowerShell execution |
| `ask_user` | AskUserTool | `ask_user_tool` | Interactive user prompts |
| `llm` | LLMTool | `llm_tool` | Delegated LLM calls (default alias `main`) |
| `grep` | GrepTool | `search_tools` | Content search (grep-style) |
| `glob` | GlobTool | `search_tools` | File pattern search (glob-style) |
| `edit` | EditTool | `edit_tool` | Targeted file editing (search/replace) |
| `fetch_result` | FetchResultTool | `fetch_result_tool` | Retrieve previously stored tool results |
| `wiki` | WikiTool | `wiki_tool` | Wiki-style long-term memory (markdown pages; see ADR-020) |
| `browser` | BrowserTool | `browser_tool` | Headless browser via Playwright (`uv sync --extra browser && playwright install chromium`) |
| `multimedia` | MultimediaTool | `multimedia_tool` | Image/media handling |
| `docx` | DocxTool | `docx_tool` | Microsoft Word document handling (`uv sync --extra office`) |
| `pptx` | PptxTool | `pptx_tool` | Microsoft PowerPoint handling (`uv sync --extra office`) |
| `excel` | ExcelTool | `excel_tool` | Microsoft Excel handling (`uv sync --extra office`) |
| `accounting_validate` | AccountingValidateTool | `accounting_validate_tool` | Invoice/compliance validation helper |
| `accounting_audit` | AccountingAuditTool | `accounting_audit_tool` | Accounting audit checks |
| `send_notification` | SendNotificationTool | `send_notification_tool` | Proactive push notifications via the Communication Gateway |

### Orchestration tools (under `taskforce.infrastructure.tools.orchestration.`)

| Short Name | Class | Module | Description |
|------------|-------|--------|-------------|
| `call_agents_parallel` | ParallelAgentTool | `parallel_agent_tool` | Run multiple sub-agents in parallel (ADR-015) |
| `call_acp_agent` | AcpAgentTool | `acp_agent_tool` | Invoke a remote agent over ACP (ADR-018) |

> The legacy `call_agent` / `agent_tool` primitive still exists in
> `orchestration/agent_tool.py` and `sub_agent_tool.py` but is not registered by
> short name — sub-agent invocation is typically configured via YAML or wired by
> `sub_agent_spawner`.

### Agent-package tools (registered by short name, resolved from optional packages)

| Short Name | Class | Fully-qualified module | Required package |
|------------|-------|------------------------|------------------|
| `rag_semantic_search` | SemanticSearchTool | `taskforce_rag_agent.tools.semantic_search_tool` | `taskforce-rag-agent` (+ `uv sync --extra rag`) |
| `rag_list_documents` | ListDocumentsTool | `taskforce_rag_agent.tools.list_documents_tool` | `taskforce-rag-agent` |
| `rag_get_document` | GetDocumentTool | `taskforce_rag_agent.tools.get_document_tool` | `taskforce-rag-agent` |
| `global_document_analysis` | GlobalDocumentAnalysisTool | `taskforce_rag_agent.tools.global_document_analysis_tool` | `taskforce-rag-agent` |
| `gmail` | GmailTool | `taskforce_butler.infrastructure.tools.email_tool` | `taskforce-butler` |
| `google_drive` | GoogleDriveTool | `taskforce_butler.infrastructure.tools.google_drive_tool` | `taskforce-butler` |
| `calendar` | CalendarTool | `taskforce_butler.infrastructure.tools.calendar_tool` | `taskforce-butler` |
| `schedule` | ScheduleTool | `taskforce_butler.infrastructure.tools.schedule_tool` | `taskforce-butler` |
| `reminder` | ReminderTool | `taskforce_butler.infrastructure.tools.reminder_tool` | `taskforce-butler` |
| `rule_manager` | RuleManagerTool | `taskforce_butler.infrastructure.tools.rule_manager_tool` | `taskforce-butler` |
| `authenticate` | AuthTool | `taskforce_butler.infrastructure.tools.auth_tool` | `taskforce-butler` |

### Tool categories reference

- **MCP Tools** (`infrastructure/tools/mcp/`): Model Context Protocol server connections
  (client, connection_manager, wrapper). MCP servers are configured per profile via the
  `mcp_servers:` block and their tools are resolved dynamically at build time.
- **ACP Integration** (`infrastructure/acp/`): Runtime, client, server, message bus and
  gateway adapters for the Agent Communication Protocol — see
  [docs/features/acp.md](docs/features/acp.md) and
  [ADR-018](docs/adr/adr-018-acp-protocol-support.md). Optional dependency group:
  `uv sync --extra acp`.

Profile YAML tool lists use **short tool names** (e.g., `file_read`,
`rag_semantic_search`). The registry is the source of truth — to see every
registered name at runtime use `taskforce tools list`.

Tool parallelism is opt-in per tool via `supports_parallelism` and controlled by
`agent.max_parallel_tools` (default 4) in profile YAML.

---

## Skills and Plugins

### Skills

File-based skill definitions that can be activated at runtime. Skills are YAML+Markdown files that define specialized agent behaviors. Three types are supported:

| Type | Invocation | Description |
|------|-----------|-------------|
| `context` (default) | `activate_skill` tool or intent routing | Injects instructions into the system prompt |
| `prompt` | `/skill-name [args]` in chat | One-shot prompt template with `$ARGUMENTS` substitution |
| `agent` | `/skill-name [args]` in chat | Temporarily overrides agent config (profile, tools, MCP servers) |

- **Storage:** Project-level in `.taskforce/skills/<name>/SKILL.md` or bundled with plugins/extensions
- **Naming:** Hierarchical using subdirectories and `:` separator (e.g., `agents/reviewer/` → `agents:reviewer` → `/agents:reviewer`)
- **Chat built-ins:** `/skills` lists all skills; `/skill-name [args]` invokes PROMPT/AGENT skills; `/<plugin_name>` switches to a plugin agent
- **CLI:** `taskforce skills list [--type context|prompt|agent]`, `taskforce run skill <name> [args]`
- **Management:** `SkillService` (application layer) handles discovery and invocation; `SkillManager` handles agent-internal lifecycle
- **Docs:** `docs/features/skills.md`

### Plugin System

Plugins extend Taskforce with custom agents, tools, and configurations via Python entry points.

- **Discovery:** `setuptools` entry points under `taskforce.plugins`
- **Structure:** Each plugin provides configs, tools, and optional domain logic
- **Loading:** `PluginLoader` and `PluginDiscovery` in the application layer
- **Examples:** `src/taskforce/plugins/ap_poc_agent/`, `document_extraction_agent/`
- **Docs:** `docs/plugins.md`

---

## Epic Orchestration

Multi-agent pipeline for complex, multi-step tasks using planner/worker/judge roles:

- **Orchestrator:** `src/taskforce/application/epic_orchestrator.py`
- **Auto-Epic Classifier:** `src/taskforce/application/task_complexity_classifier.py`
- **State:** Persisted under `.taskforce/epic_runs/<run_id>/` with `MISSION.md`, `CURRENT_STATE.md`, `MEMORY.md`
- **Profiles:** Planner, worker, judge configs in `src/taskforce/configs/`
- **CLI:** `taskforce epic` command with `--rounds` option for iterative refinement; `taskforce run mission --auto-epic` for automatic detection
- **Config:** `orchestration.auto_epic` section in profile YAML (see `AutoEpicConfig` in `core/domain/config_schema.py`)
- **Docs:** `docs/architecture/epic-orchestration.md`
- **ADR:** `docs/adr/adr-008-auto-epic-orchestration.md`

---

## Communication Gateway

The unified Communication Gateway replaces the earlier per-provider communication model. It provides a single entry point for all channel-based agent communication (Telegram, Teams, Slack, REST, etc.).

### Architecture

- **Protocols:** `core/interfaces/gateway.py` (5 protocols: `OutboundSenderProtocol`, `InboundAdapterProtocol`, `ConversationStoreProtocol`, `RecipientRegistryProtocol`, `RecipientResolverProtocol` — the last is an opt-in seam used by external auth/identity layers; the framework ships a pass-through default)
- **Domain Models:** `core/domain/gateway.py` (`InboundMessage`, `GatewayOptions`, `GatewayResponse`, `NotificationRequest`, `NotificationResult`)
- **Gateway Service:** `application/gateway.py` (`CommunicationGateway`) - orchestrates inbound processing, session management, agent execution, outbound replies, and proactive push
- **API Routes:** `api/routes/gateway.py`:
  - `POST /api/v1/gateway/{channel}/messages` - handle inbound messages from any channel
  - `POST /api/v1/gateway/{channel}/webhook` - handle raw provider webhooks (Telegram, Teams)
  - `POST /api/v1/gateway/notify` - send proactive push notifications
  - `POST /api/v1/gateway/broadcast` - broadcast to all recipients on a channel
  - `GET  /api/v1/gateway/channels` - list configured channels
- **Generic Webhook & Mission Routes:**
  - `POST /api/v1/events/{source_name}` - forwards inbound HTTP to a
    registered ``WebhookCapableEventSource`` (HMAC-verified for
    GitHub). Returns 401 on signature mismatch, 404 when no source is
    active, 415 for non-JSON bodies, 202 on accept.
  - `GET /api/v1/missions` / `POST /api/v1/missions/{request_id}/cancel`
    - list queued/in-flight missions and cancel by request_id
    (queued → ``status=cancelled``, in-flight → cooperative interrupt
    via ``executor.interrupt``). Surfaced through
    ``taskforce missions running`` and ``taskforce missions cancel``.
- **Send Notification Tool:** `infrastructure/tools/native/send_notification_tool.py` - allows agents to proactively push messages
- **Extension Implementations:** `taskforce/infrastructure/communication/`:
  - `gateway_registry.py` - Component wiring and factory
  - `gateway_conversation_store.py` - File-based gateway session/history persistence (`GatewayConversationStore`, distinct from the persistence-layer `FileConversationStore`)
  - `inbound_adapters.py` - Channel-specific payload normalization
  - `outbound_senders.py` - Channel-specific message dispatch
  - `recipient_registry.py` - Push notification recipient store
- **Persistence:** Domain conversations in `.taskforce/conversations/` (ADR-016 `FileConversationStore`); gateway session/history records in `.taskforce/gateway_sessions/` (`GatewayConversationStore`).
  When the `taskforce-enterprise` plugin is installed, paths are routed per-tenant + per-user (ADR-022 iter-2): per-user buckets land at `.taskforce/tenants/{tid}/users/{uid}/{state,conversations,gateway_sessions,memory,skills,agent_state.json}`; tenant-shared buckets stay at `.taskforce/tenants/{tid}/{custom,workflows}/`. Stand-alone framework usage continues to write the flat layout above.
- **ADRs:** `docs/adr/adr-006-communication-providers.md` (original), `docs/adr/adr-009-communication-gateway.md` (current)
- **Docs:** `docs/integrations.md`

---

## Proactive Layer — Standing Goals (ADR-024)

Framework-core opt-in layer that lets the agent revisit recurring
intentions on its own schedule. Disabled by default; enable via the
butler profile's `proactive:` block.

- **Domain:** `core/domain/standing_goal.py` — `StandingGoal` dataclass
  (`description`, `evaluation_prompt`, `frequency` cron, `priority`,
  `enabled`, `last_evaluated_at`, `last_action_taken`).
- **Protocol:** `core/interfaces/standing_goals.py`
  (`StandingGoalStoreProtocol`).
- **Store:** `infrastructure/persistence/file_standing_goal_store.py`
  — atomic JSON under `<work_dir>/standing_goals.json`,
  `asyncio.Lock`-serialized writes.
- **Evaluator:** `application/goal_evaluator_service.py`
  (`GoalEvaluatorService`, `GoalDecision`). Cron pre-filter re-uses
  `_next_cron_occurrence` from the SchedulerService so most ticks
  perform zero LLM calls.
- **REST:** `api/routes/standing_goals.py` —
  `GET/POST/PATCH/DELETE /api/v1/standing-goals` and
  `POST /api/v1/standing-goals/{id}/evaluate-now`.
- **CLI:** `taskforce goals list/show/add/disable/enable/remove/run-now`.
- **Heartbeat:** `agents/butler/src/taskforce_butler/daemon.py`
  (`_setup_proactive_layer` + `_heartbeat_loop`) spawns a background
  asyncio task that calls `evaluate_due_goals` every
  `heartbeat_minutes`.

Sample butler-profile fragment:

```yaml
proactive:
  enabled: true
  heartbeat_minutes: 15
  standing_goals:
    - description: Weekly summary
      evaluation_prompt: |
        Prepare last week's coding summary using the wiki tool. $NOW
      frequency: "0 9 * * 1"
      priority: 4
```

ADR: `docs/adr/adr-024-standing-goals.md`.

---

## Butler Agent (Optional Package)

The Butler is a proactive, event-driven agent daemon. It is shipped as a separate
package (`taskforce-butler`) under `agents/butler/` and becomes available once
installed. When installed, the unified CLI auto-registers `taskforce butler ...`
and switches the default profile from `dev` to `butler`.

See **[ADR-010](docs/adr/adr-010-event-driven-butler-agent.md)** and
**[ADR-017](docs/adr/adr-017-butler-role-specialization.md)** for design details.

### Package Layout

```
agents/butler/
├── src/taskforce_butler/
│   ├── __init__.py
│   ├── daemon.py             # ButlerDaemon — top-level daemon process
│   ├── service.py            # ButlerService — lifecycle orchestration
│   ├── learning_service.py   # Auto-extraction from conversations
│   ├── role_loader.py        # Butler role specialization loader
│   ├── cli/commands.py       # Typer app registered as `taskforce butler`
│   ├── domain/               # butler_role.py
│   └── infrastructure/
│       ├── event_sources/    # CalendarEventSource, WebhookEventSource
│       │                     # (extend taskforce.infrastructure.event_sources.polling_base)
│       └── tools/            # gmail, google_drive, calendar, schedule,
│                             # reminder, rule_manager, auth tools
└── configs/
    ├── butler.yaml           # Main butler profile
    ├── custom/               # Custom role configs (accountant, pc-agent, …)
    └── roles/                # accountant.yaml, personal_assistant.yaml
```

Framework-side helpers that Butler consumes:
- `core/domain/agent_event.py` — `AgentEvent` model
- `core/domain/schedule.py` — `ScheduleJob` model
- `core/domain/trigger_rule.py` — `TriggerRule`, `RuleAction`, `RuleActionType`
- `core/interfaces/{event_source,scheduler,rule_engine,learning}.py` — protocols
- `application/event_router.py` — `EventRouter` (event → action dispatch)
- `infrastructure/rule_engine/file_rule_engine.py` — `FileRuleEngine`
- `infrastructure/scheduler/` — `SchedulerService` + `FileJobStore`
- `infrastructure/event_sources/polling_base.py` — `PollingEventSource` base class
  that Butler's concrete event sources extend.

### Running the Butler

```bash
# Install the package
uv pip install taskforce-butler          # or via workspace install

# Start the butler daemon
taskforce butler start --profile butler
taskforce start                          # shortcut: equivalent to 'butler start'

# Check status
taskforce butler status

# Manage trigger rules
taskforce butler rules list
taskforce butler rules add --name "calendar_reminder" --source calendar --type calendar.upcoming

# View scheduled jobs
taskforce butler schedules list

# Butler roles
taskforce butler roles list
taskforce butler roles show accountant
```

### Butler Profile

The butler profile (`agents/butler/configs/butler.yaml`) configures event sources,
trigger rules, scheduler, and notification defaults. The unified CLI adds the
package's `configs/` directory to the profile loader so `--profile butler` resolves
transparently.

---

## Development Workflow

### Setup

```bash
# Clone and navigate
cd /home/user/pytaskforce

# Install dependencies (MUST use uv)
uv sync

# Install optional dependency groups as needed
uv sync --extra browser       # Playwright browser automation
uv sync --extra rag            # Azure AI Search
uv sync --extra office         # docx/pptx/excel tools
uv sync --extra acp            # Agent Communication Protocol SDK

# For browser tool: also install Playwright browsers
playwright install chromium

# To use butler / coding-agent / rag-agent features, install the matching
# agent package(s) — they live under agents/ in this repo:
uv pip install -e agents/butler
uv pip install -e agents/coding-agent
uv pip install -e agents/rag-agent

# Activate virtual environment
source .venv/bin/activate  # Linux/Mac
# .\.venv\Scripts\Activate.ps1  # Windows

# Verify installation
taskforce --help
```

### Running Tests

```bash
# All tests
uv run pytest

# Specific layer
uv run pytest tests/unit/core/
uv run pytest tests/unit/infrastructure/
uv run pytest tests/unit/application/
uv run pytest tests/integration/

# With coverage
uv run pytest --cov=taskforce --cov-report=html

# Single test file (useful for targeted debugging)
PYTHONPATH=src pytest -q -c /dev/null <path_to_test>
```

Note: `asyncio_mode = "auto"` is configured in `pyproject.toml`, so `@pytest.mark.asyncio` is applied automatically to all async test functions.

### Code Quality

```bash
# Format code (must run before commit)
uv run black src/taskforce tests

# Lint code
uv run ruff check src/taskforce tests

# Fix auto-fixable issues
uv run ruff check --fix src/taskforce tests

# Type checking
uv run mypy src/taskforce
```

Black and Ruff are configured with `line-length = 100` and `target-version = py311`.

### CI Pipeline

CI runs on every push (`.github/workflows/ci.yml`):
1. `uv sync --locked` - Install dependencies
2. `uv run pytest` - Run all tests
3. Auto-tag on default branch: `v<major>.<minor>.<patch>` (major/minor from `pyproject.toml`, patch auto-increments)

### Running the Agent

```bash
# CLI mode
taskforce run mission "Analyze sales data and create visualization"

# With specific profile
taskforce run mission "..." --profile dev
taskforce run mission "..." --profile coding_agent

# Interactive chat
taskforce chat

# Epic orchestration
taskforce epic "Build a REST API for user management" --rounds 3

# API server
uvicorn taskforce.api.server:app --reload
```

### Local Dev Launcher (Windows / PowerShell)

`dev.ps1` (repo root) boots backend + UI together for the enterprise dev setup:

```powershell
.\dev.ps1                  # backend (8070) + UI (5173) in this terminal, prefixed logs
.\dev.ps1 -Split           # both in two separate terminal windows (independent Ctrl+C)
.\dev.ps1 -Backend         # backend only, foreground
.\dev.ps1 -Frontend        # UI only, foreground
.\dev.ps1 -Install         # force reinstall enterprise plugin + UI deps
.\dev.ps1 -SkipMigrate     # skip alembic on startup
.\dev.ps1 -Build           # production build of UI only
.\dev.ps1 -Port 8080       # override backend port (also re-points UI proxy)
.\dev.ps1 -ForceVite       # always wipe ui/node_modules/.vite + start Vite with --force
```

Stale-chunk protection: before starting the UI, the launcher fingerprints
`ui/node_modules/@taskforce/enterprise-ui/dist/index.js` (+ `index.css`) and
compares against `ui/.dev-fingerprint`. If the dist changed since the last run,
`ui/node_modules/.vite` is wiped and Vite is restarted with `--force`, which
prevents the browser from requesting old hashed chunks (e.g. 404 on
`CreateUserPage-XXX.js` / "Page update required" fallback).

---

## Coding Standards

### 1. Code Style

- **PEP8 compliance** - Enforced via Black and Ruff
- **English names only** - `user_count`, `is_valid`, `document_id`
- **No abbreviations** - except universally known (`url`, `id`, `db`)
- **Type annotations** - Required on ALL function signatures

```python
# ✅ GOOD
def calculate_total_price(items: List[Item], tax_rate: float) -> Decimal:
    """Calculate total price including tax."""
    ...

# ❌ BAD
def calc_tot(itms, tx):  # No types, abbreviated
    ...
```

### 2. Function Guidelines

- **Max 30 lines** per function/method
- **Single responsibility** - one function does one thing
- **Pure functions preferred** - avoid side effects where possible
- **Docstrings required** - Google style for all public functions

```python
def generate_plan(mission: str, llm_provider: LLMProviderProtocol) -> TodoList:
    """Generate a TodoList plan from mission description.

    Args:
        mission: Mission description text
        llm_provider: LLM service for plan generation

    Returns:
        TodoList with decomposed tasks

    Raises:
        ValueError: If mission is empty
        LLMError: If plan generation fails
    """
    if not mission.strip():
        raise ValueError("Mission cannot be empty")

    # Implementation...
```

### 3. Error Handling

- **Specific exceptions** - Catch `ValueError`, `HTTPException`, not generic `Exception`
- **Contextual error messages** - Include relevant IDs and state
- **No silent failures** - Always log or re-raise
- **Tool errors** - Convert to `ToolError` payloads via `tool_error_payload`

```python
# ✅ GOOD
try:
    state = await state_manager.load_state(session_id)
except FileNotFoundError:
    logger.warning(f"Session state not found: {session_id}")
    state = create_new_state()
except Exception as e:
    logger.error(f"Failed to load state for {session_id}: {e}")
    raise

# ❌ BAD
try:
    state = await state_manager.load_state(session_id)
except:  # Too broad, silent
    pass
```

### 4. Architectural Patterns

**Functional Core, OO Shell:**
- **Core domain** - Pure functions, minimal classes
- **Infrastructure** - Classes for I/O, state management, external APIs
- **Avoid God objects** - Small, focused classes

### 5. Type Safety: Concrete Types over Dictionaries

- **No magic strings** - Use `Enum`, `Literal`, or class constants (see `core/domain/enums.py`)
- **Concrete data structures** - Use `dataclass`, `NamedTuple`, or Pydantic `BaseModel` instead of `dict`
- **Typed return values** - Functions return concrete types, not `Dict[str, Any]`

```python
# ❌ AVOID - Magic strings and dictionaries
def get_status(data: dict) -> dict:
    if data["status"] == "success":
        return {"code": 200, "message": "OK"}

# ✅ PREFERRED - Enums and dataclasses
from taskforce.core.domain.enums import ExecutionStatus

@dataclass
class StatusResult:
    code: int
    message: str

def get_status(data: RequestData) -> StatusResult:
    if data.status == ExecutionStatus.COMPLETED:
        return StatusResult(code=200, message="OK")
```

**Exceptions** (where `dict` is acceptable):
- Dynamic JSON payloads from external APIs (before validation)
- Logging contexts and metrics
- Temporary intermediate results in tests

---

## Testing Strategy

### Test Structure

Mirror source structure:

```
tests/
├── unit/
│   ├── core/              # Pure domain logic tests
│   │   └── domain/
│   │       └── lean_agent_components/
│   ├── infrastructure/    # Adapter tests
│   │   ├── tools/
│   │   ├── skills/
│   │   └── cache/
│   ├── application/       # Service tests
│   └── api/               # API/CLI tests
│       └── cli/
├── integration/           # End-to-end tests (~25 files)
├── core/domain/           # Additional core tests (planning strategies)
├── fixtures/              # Shared test data
├── examples/              # Example tests
├── taskforce/  # Extension tests
└── conftest.py            # Shared fixtures (mock LLM, state managers, etc.)
```

### Coverage Targets

- Core domain: **≥90%** (critical business logic)
- Infrastructure: **≥80%** (adapter implementations)
- Application: **≥75%** (orchestration)
- Overall: **≥80%**

### Writing Tests

**Core Layer Tests (Pure Unit Tests):**

```python
# tests/unit/core/test_agent.py
import pytest
from unittest.mock import Mock
from taskforce.core.domain.agent import Agent
from taskforce.core.interfaces.state import StateManagerProtocol

@pytest.fixture
def mock_state_manager() -> StateManagerProtocol:
    """Create protocol-compatible mock."""
    mock = Mock(spec=StateManagerProtocol)
    mock.save_state = Mock(return_value=None)
    mock.load_state = Mock(return_value=None)
    return mock

def test_agent_executes_react_loop(mock_state_manager, mock_llm, mock_tools):
    """Test ReAct loop execution with protocol mocks."""
    agent = Agent(
        state_manager=mock_state_manager,
        llm_provider=mock_llm,
        tools=mock_tools
    )
    result = agent.execute("Test mission", "session-123")
    assert result.success
    mock_state_manager.save_state.assert_called()
```

**Integration Tests:**

Integration tests for `/api/v1/execute` should mock `executor.execute_mission` to avoid long-running real executions (see `tests/integration/test_server_streaming.py`).

```python
# tests/integration/test_file_state_manager.py
import pytest
from pathlib import Path
from taskforce.infrastructure.persistence.file_state_manager import FileStateManager

@pytest.mark.asyncio
async def test_file_state_manager_saves_and_loads(tmp_path: Path):
    """Test file-based persistence with actual filesystem."""
    manager = FileStateManager(work_dir=str(tmp_path))
    test_data = {"mission": "Test", "step": 1}
    await manager.save_state("test-session", test_data)
    loaded = await manager.load_state("test-session")
    assert loaded == test_data
```

---

## Configuration Management

### Profiles

Profiles are YAML files discovered via a search path that spans the framework and
any installed agent packages. The unified CLI registers the package `configs/`
directories at startup (see `taskforce_cli.agent_discovery.register_agent_config_dirs`).

**Framework-shipped profiles** (`src/taskforce/configs/`):

- `default.yaml` — general-purpose profile with essential tools (file, shell, python,
  web, git, memory, ask_user, llm). Profile id: `default`.
- `llm_config.yaml` — model aliases and dynamic-routing rules (not a profile itself,
  referenced via `llm.config_path`).
- `acp_peer.yaml` — profile for agents exposed over the ACP protocol.
- `showcase_coder.yaml`, `showcase_orchestrator.yaml`, `showcase_researcher.yaml` —
  demo profiles used by examples and docs.
- `dev` — not a physical file; resolved by the framework from built-in defaults.

**Agent-package profiles** (available when the package is installed):

| Profile | Package | Location |
|---------|---------|----------|
| `butler` | taskforce-butler | `agents/butler/configs/butler.yaml` |
| `butler_roles/accountant`, `butler_roles/personal_assistant` | taskforce-butler | `agents/butler/configs/roles/` |
| Butler custom roles (`accountant`, `pc-agent`, `research_agent`, `vision_ocr`) | taskforce-butler | `agents/butler/configs/custom/` |
| `coding_agent`, `coding_analysis` | taskforce-coding-agent | `agents/coding-agent/configs/` |
| Coding sub-agents (`coding_planner`, `coding_worker`, `coding_reviewer`, `code_reviewer`, `test_engineer`, `doc_writer`, `swe_analyzer`, `swe_coder`) | taskforce-coding-agent | `agents/coding-agent/configs/custom/` |
| `rag_agent` | taskforce-rag-agent | `agents/rag-agent/configs/rag_agent.yaml` |

**Default profile resolution:** The unified CLI picks `butler` when `taskforce_butler`
is importable, otherwise falls back to `dev`. The framework-only fallback CLI
(`src/taskforce/api/cli/main.py`) always defaults to `dev`. Override with
`--profile <name>` or `TASKFORCE_PROFILE`.

```yaml
# Example: src/taskforce/configs/default.yaml
profile: default

persistence:
  type: file
  work_dir: .taskforce

agent:
  planning_strategy: native_react
  planning_strategy_params:
    max_step_iterations: 3
    max_plan_steps: 12
    reflect_every_step: false
  max_steps: 30

llm:
  config_path: src/taskforce/configs/llm_config.yaml
  default_model: main

memory:
  store_dir: .taskforce/memory

logging:
  level: INFO
  format: console

context_policy:
  max_items: 10
  max_chars_per_item: 3000
  max_total_chars: 15000

tools:
  - web_search
  - web_fetch
  - file_read
  - file_write
  - edit
  - python
  - bash
  - shell
  - grep
  - glob
  - git
  - ask_user
  - memory
  - llm
```

### Optional Dependency Groups

Defined in `pyproject.toml` under `[project.optional-dependencies]`:

| Group | Purpose | Install Command |
|-------|---------|-----------------|
| `browser` | Playwright headless browser automation | `uv sync --extra browser` |
| `rag` | Azure AI Search integration | `uv sync --extra rag` |
| `pdf` | Kept for backwards compatibility — core already includes `pypdf`, `pdfplumber`, `docling` | `uv sync --extra pdf` |
| `office` | python-docx, python-pptx, openpyxl (for the `docx`/`pptx`/`excel` tools) | `uv sync --extra office` |
| `postgres` | PostgreSQL persistence (SQLAlchemy, Alembic, AsyncPG) | `uv sync --extra postgres` |
| `tokenizer` | Tiktoken token counting | `uv sync --extra tokenizer` |
| `tracing` | Arize Phoenix OTEL + LiteLLM instrumentation | `uv sync --extra tracing` |
| `auth` | Cryptography for authentication / OAuth2 | `uv sync --extra auth` |
| `evals` | Inspect AI + SWE-Bench evaluation framework | `uv sync --extra evals` |
| `build` | Package building and publishing | `uv sync --extra build` |
| `acp` | Agent Communication Protocol (IBM/Linux Foundation) SDK | `uv sync --extra acp` |

> The `personal-assistant` group has been removed — Google Workspace integration
> now ships with the `taskforce-butler` agent package instead of as an extra on
> the framework distribution.

Dev dependencies are managed separately via `[dependency-groups]`:

```bash
uv sync --group dev   # pytest, ruff, black, mypy, pyinstaller
```

### Environment Variables

**Required:**
- `OPENAI_API_KEY` - OpenAI API access
- `DATABASE_URL` - PostgreSQL connection (prod only)

**Optional:**
- `AZURE_OPENAI_API_KEY` - Azure OpenAI access
- `AZURE_OPENAI_ENDPOINT` - Azure endpoint
- `GITHUB_TOKEN` - GitHub API operations
- `TASKFORCE_PROFILE` - Override profile selection
- `TASKFORCE_WORK_DIR` - Override work directory (default: `.taskforce`)

---

## Common Patterns and Recipes

### Enabling Long-Term Memory (Wiki)

The native `wiki` tool provides wiki-style long-term memory — one
markdown page per topic under `.taskforce/memory/wiki/`. Configure via
profile YAML:

```yaml
tools:
  - wiki

wiki:
  store_dir: .taskforce/memory/wiki     # optional — derived from persistence.work_dir
  context_injection:
    max_total_chars: 2000
    top_k_relevant: 5
    include_index: true
```

The agent curates the wiki itself (creates/updates/deletes pages via
the `wiki` tool). There is no background consolidation or dreaming —
relevance comes from search ranking plus index membership.

**See:** [Long-Term Memory Documentation](docs/features/longterm-memory.md), [ADR-020](docs/adr/adr-020-wiki-style-memory.md).

### Adding a New Tool

1. **Create tool in infrastructure layer** (prefer `BaseTool` to reduce boilerplate):

```python
# infrastructure/tools/native/my_tool.py
from taskforce.infrastructure.tools.base_tool import BaseTool

class MyTool(BaseTool):
    """Performs X operation on Y input."""

    tool_name = "my_tool"
    tool_description = "Performs X operation on Y input"
    tool_parameters_schema = {
        "type": "object",
        "properties": {
            "input": {"type": "string", "description": "Input data"}
        },
        "required": ["input"],
    }

    async def _execute(self, **params) -> dict:
        """Execute the tool."""
        input_data = params["input"]
        # Tool logic here...
        return {"result": "...", "success": True}
```

> `BaseTool` (in `infrastructure/tools/base_tool.py`) provides default implementations
> for `name`, `description`, `parameters_schema`, `validate_params`, `requires_approval`,
> `approval_risk_level`, `supports_parallelism`, and error-safe execution wrapping.
> Existing tools implementing `ToolProtocol` directly continue to work unchanged.

2. **Register in tool registry** (`infrastructure/tools/registry.py`): Add the short name → class mapping.

3. **Write tests:**

```python
# tests/unit/infrastructure/tools/test_my_tool.py
import pytest
from taskforce.infrastructure.tools.native.my_tool import MyTool

@pytest.mark.asyncio
async def test_my_tool_executes():
    tool = MyTool()
    result = await tool.execute(input="test")
    assert result["success"]
```

### Adding a New Persistence Adapter

1. **Implement protocol:**

```python
# infrastructure/persistence/my_state_manager.py
from typing import Optional, Dict, Any, List
from taskforce.core.interfaces.state import StateManagerProtocol

class MyStateManager:
    """Custom state persistence implementation."""

    async def save_state(self, session_id: str, state_data: Dict[str, Any]) -> None: ...
    async def load_state(self, session_id: str) -> Optional[Dict[str, Any]]: ...
    async def delete_state(self, session_id: str) -> None: ...
    async def list_sessions(self) -> List[str]: ...
```

2. **Add to factory** (`application/factory.py`): Wire the new adapter based on `persistence.type` config value.

---

## Important Implementation Notes

### 1. Async/Await Patterns

- **ALL I/O operations must be async** - file, database, HTTP, LLM calls
- Use `asyncio.gather()` for parallel operations
- Use `async with` for resource management
- Use `await asyncio.sleep()` instead of `time.sleep()` (blocks event loop!)

```python
# ✅ GOOD - Async I/O with aiofiles
async def process_files(file_paths: List[str]) -> List[str]:
    async with aiofiles.open(file_paths[0]) as f:
        content = await f.read()
    return content

# ❌ BAD - Blocking I/O
def process_files(file_paths: List[str]) -> List[str]:
    with open(file_paths[0]) as f:  # Blocks event loop!
        content = f.read()
```

### 2. Structured Logging

Use `structlog` with contextual information:

```python
import structlog

logger = structlog.get_logger(__name__)

# ✅ GOOD - Contextual logging
logger.info(
    "agent.mission.started",
    session_id=session_id,
    mission=mission,
    profile=profile
)

# ❌ BAD - Generic logging
logger.info("Mission started")
```

### 3. Simplified Architecture Patterns

**Executor Pattern - Single Source of Truth:**

`execute_mission()` delegates to `execute_mission_streaming()` to avoid code duplication:

```python
# ✅ CURRENT PATTERN - execute_mission delegates to streaming
async def execute_mission(self, mission, ...) -> ExecutionResult:
    result = None
    async for update in self.execute_mission_streaming(mission, ...):
        if progress_callback:
            progress_callback(update)
        if update.event_type == "complete":
            result = ExecutionResult(...)
    return result
```

**Tool Registry - Direct Usage:**

```python
# ✅ CORRECT - Use ToolRegistry directly
from taskforce.application.tool_registry import ToolRegistry, get_tool_registry

registry = get_tool_registry()
tools = registry.list_native_tools()
resolved = registry.resolve(["python", "file_read"])

# ❌ DEPRECATED - Don't use these (removed)
# from taskforce.application.tool_catalog import ToolCatalog
# from taskforce.application.tool_mapper import ToolMapper
```

**ContextManager — Context Preparation:**

```python
# ✅ CORRECT - Use ContextManager for LLM context preparation
await agent.context.prepare_for_llm(mission=mission, state=state)
# Then pass context to LLM provider
await agent.llm_provider.complete_stream(
    messages=agent.context.messages,
    tools=agent.context.tools,
    ...
)

# ❌ AVOID - Manual 4-step context preparation
# prompt = agent._build_system_prompt(mission, state, messages)
# agent.context.set_system_prompt(prompt)
# await agent.context.compress()
# agent.context.preflight_check()
```

**Agent Components - Call Directly:**

```python
# ✅ CORRECT - Call component methods directly
tool_msg = await agent.tool_result_message_factory.build_message(...)
agent.context.append_message(tool_msg)

# ❌ AVOID - Direct message list manipulation
# messages.append(tool_msg)
```

### 4. Sub-Agent Spawning

Sub-agent spawning is centralized in `application/sub_agent_spawner.py` to
standardize isolated session creation. The `coding_agent` profile (shipped with
`taskforce_coding_agent`) delegates to custom sub-agents defined in
`agents/coding-agent/configs/custom/`. Sub-agent context snapshots are captured
before `agent.close()` and registered on the parent agent's ContextManager for
`/tree --sub-agents` inspection. Parallel execution is handled by the
`call_agents_parallel` tool (ADR-015).

---

## Deployment

### Local Development

```bash
# Use file-based persistence
export TASKFORCE_PROFILE=dev
taskforce run mission "..."
```

### Docker

```bash
# Build
docker build -t taskforce:latest .

# Run with environment
docker run -e DATABASE_URL=postgresql://... \
           -e OPENAI_API_KEY=sk-... \
           taskforce:latest
```

### Kubernetes

See `docs/architecture/section-10-deployment.md` for:
- Helm charts
- Health check configuration
- Database migration jobs
- Horizontal pod autoscaling

---

## Troubleshooting

### Import Errors

**Problem:** `ImportError: cannot import name 'X' from 'taskforce.core'`

**Solution:** Check layer import rules. Core cannot import from infrastructure.

### Protocol Not Satisfied

**Problem:** `TypeError: object does not implement protocol`

**Solution:** Ensure all protocol methods are implemented with correct signatures.

### State Version Conflicts

**Problem:** `StateVersionError: concurrent modification detected`

**Solution:** Reload state before saving. Implement retry logic for concurrent updates.

---

## Key Files Reference

### Core Domain
- `src/taskforce/core/domain/agent.py` - ReAct loop implementation
- `src/taskforce/core/domain/lean_agent.py` - LeanAgent (simplified) implementation
- `src/taskforce/core/domain/lean_agent_components/` - Agent components (call directly, not via wrappers):
  - `context_manager.py` - ContextManager: single source of truth for LLM context (messages, tools, snapshots)
  - `message_history_manager.py` - Message compression and budget management
  - `message_sanitizer.py` - Message sanitization
  - `tool_executor.py` - Tool execution and result message factory
  - `prompt_builder.py` - System prompt construction
  - `state_store.py` - State persistence helpers
  - `resource_closer.py` - MCP resource cleanup
- `src/taskforce/core/domain/planning_strategy.py` - Planning strategies (native_react, plan_and_execute, plan_and_react, spar)
- `src/taskforce/core/domain/enums.py` - All domain enumerations (ExecutionStatus, EventType, etc.)
- `src/taskforce/core/domain/models.py` - Core data models (ExecutionResult, StreamEvent, TokenUsage)
- `src/taskforce/core/domain/errors.py` - Exception types (TaskforceError, LLMError, ToolError)
- `src/taskforce/core/domain/exceptions.py` - Execution exceptions with structured context (TaskforceExecutionError)
- `src/taskforce/core/domain/config_schema.py` - Configuration schema definitions
- `src/taskforce/core/domain/gateway.py` - Communication Gateway domain models (InboundMessage, GatewayOptions, GatewayResponse, NotificationRequest, NotificationResult)
- `src/taskforce/core/domain/agent_definition.py` - Unified agent definition model (AgentSource enum)
- `src/taskforce/core/domain/agent_models.py` - Agent domain models (CustomAgentDefinition, ProfileAgentDefinition)
- `src/taskforce/core/domain/tool_result.py` - Typed ToolResult dataclass (replaces Dict[str, Any])
- `src/taskforce/core/domain/runtime.py` - Runtime tracking models (HeartbeatRecord)
- `src/taskforce/core/domain/memory.py` - Memory domain models (includes PREFERENCE and LEARNED_FACT kinds)
- `src/taskforce/core/domain/memory_service.py` - Memory service logic
- `src/taskforce/core/domain/messaging.py` - Inter-agent messaging models
- `src/taskforce/core/domain/agent_event.py` - Butler event model (AgentEvent, AgentEventType)
- `src/taskforce/core/domain/schedule.py` - Schedule job models (ScheduleJob, ScheduleType, ScheduleAction)
- `src/taskforce/core/domain/trigger_rule.py` - Trigger rule models (TriggerRule, TriggerCondition, RuleAction)
- `src/taskforce/core/domain/sub_agents.py` - Sub-agent management
- `src/taskforce/core/domain/skill.py` - Skill domain models
- `src/taskforce/core/domain/skill_workflow.py` - Skill workflow orchestration
- `src/taskforce/core/domain/epic.py` - Epic orchestration models
- `src/taskforce/core/domain/context_builder.py` - Context construction
- `src/taskforce/core/domain/context_policy.py` - Context filtering policies
- `src/taskforce/core/domain/token_budgeter.py` - Token budget management
- `src/taskforce/core/tools/tool_converter.py` - Tool format conversion
- `src/taskforce/core/tools/planner_tool.py` - Planning tool for agents
- `src/taskforce/core/utils/time.py` - UTC time utilities

### Protocols (`src/taskforce/core/interfaces/`)
- `state.py` - `StateManagerProtocol` - session state persistence
- `llm.py` - `LLMProviderProtocol` - LLM provider abstraction
- `tools.py` - `ToolProtocol`, `ApprovalRiskLevel` - tool execution interface
- `memory_store.py` - `MemoryStoreProtocol` - memory storage
- `gateway.py` - `OutboundSenderProtocol`, `InboundAdapterProtocol`, `ConversationStoreProtocol`, `RecipientRegistryProtocol`, `RecipientResolverProtocol` (+ `RecipientInfo` value object) - Communication Gateway
- `messaging.py` - `MessageBusProtocol` - inter-agent messaging
- `runtime.py` - `HeartbeatStoreProtocol`, `CheckpointStoreProtocol`, `AgentRuntimeTrackerProtocol` - runtime tracking
- `skills.py` - `SkillProtocol`, `SkillMetadata`, `SkillRegistryProtocol`, `SkillContextProtocol` - skill lifecycle
- `tool_mapping.py` - `ToolMapperProtocol` - tool name resolution
- `tool_resolver.py` - `ToolResolverProtocol` - tool name → instance resolution with DI
- `tool_result_store.py` - `ToolResultStoreProtocol` - tool result caching
- `sub_agents.py` - `SubAgentSpawnerProtocol` - sub-agent spawning
- `identity_stubs.py` - `TenantContextProtocol`, `UserContextProtocol`, `IdentityProviderProtocol`, `PolicyEngineProtocol` - identity/tenancy
- `logging.py` - `LoggerProtocol` - structured logging
- `auth.py` - `TokenStoreProtocol`, `AuthFlowProtocol`, `AuthManagerProtocol` - OAuth2 authentication
- `agent_state.py` - `AgentStateProtocol` - singleton agent state (ADR-016)
- `channel_ask.py` - `ChannelAskProtocol` - channel-based user interaction
- `experience.py` - `ExperienceProtocol` - session experience tracking
- `token_estimator.py` - `TokenEstimatorProtocol` - token counting
- `conversation.py` - `ConversationProtocol`, `ConversationManagerProtocol` - persistent conversations (ADR-016)
- `embeddings.py` - `EmbeddingsProtocol` - text embeddings
- `context_manager.py` - `ContextManagerProtocol` + value objects - unified LLM context
- `acp.py` - ACP protocols (ADR-018)
- `event_source.py` - `EventSourceProtocol` - external event ingestion (polling/webhook)
- `scheduler.py` - `SchedulerProtocol` - time-based job scheduling (cron, interval, one-shot)
- `rule_engine.py` - `RuleEngineProtocol` - trigger-rule evaluation against agent events
- `learning.py` - `LearningStrategyProtocol` - automatic knowledge extraction from conversations

> Event-driven primitives (`EventSourceProtocol`, `SchedulerProtocol`,
> `RuleEngineProtocol`, `LearningStrategyProtocol`) live in the framework core
> under `src/taskforce/core/interfaces/{event_source,scheduler,rule_engine,learning}.py`
> so any agent package can reuse them. The `ButlerProtocol` and other butler-only
> contracts remain inside the `taskforce_butler` agent package.

### Infrastructure
- `src/taskforce/infrastructure/persistence/file_state_manager.py` - File-based state
- `src/taskforce/infrastructure/persistence/file_agent_registry.py` - File-based agent registry
- `src/taskforce/infrastructure/llm/litellm_service.py` - Unified LLM service (multi-provider via LiteLLM)
- `src/taskforce/infrastructure/llm/llm_router.py` - LLM Router for dynamic per-call model selection (Decorator pattern)
- `src/taskforce/infrastructure/llm/llm_config_loader.py` - LLM configuration loading and model alias resolution
- `src/taskforce/infrastructure/llm/llm_response_parser.py` - LLM streaming response parsing
- `src/taskforce/infrastructure/memory/file_memory_store.py` - File-based memory
- `src/taskforce/infrastructure/cache/tool_result_store.py` - Tool result caching
- `src/taskforce/infrastructure/tools/base_tool.py` - `BaseTool` convenience base class
- `src/taskforce/infrastructure/tools/registry.py` - Tool short-name registry
- `src/taskforce/infrastructure/tools/native/*.py` - Native tools (see "Tools" section)
- `src/taskforce/infrastructure/tools/orchestration/*.py` - `agent_tool`, `sub_agent_tool`, `parallel_agent_tool`, `acp_agent_tool`
- `src/taskforce/infrastructure/tools/mcp/connection_manager.py` - MCP connections
- `src/taskforce/infrastructure/event_sources/polling_base.py` - `PollingEventSource` base class for polling event sources
- `src/taskforce/infrastructure/scheduler/scheduler_service.py` - `SchedulerService` (asyncio cron / interval / one-shot)
- `src/taskforce/infrastructure/scheduler/file_job_store.py` - `FileJobStore` for persisting `ScheduleJob`s
- `src/taskforce/infrastructure/rule_engine/file_rule_engine.py` - `FileRuleEngine` for evaluating `TriggerRule`s
- `src/taskforce/infrastructure/skills/` - Skill loading/parsing/registry
- `src/taskforce/infrastructure/tracing/phoenix_tracer.py` - Phoenix tracing
- `src/taskforce/infrastructure/acp/` - ACP runtime, client, server, message bus, gateway adapters (ADR-018)
- `src/taskforce/infrastructure/communication/` - Gateway adapters, senders, stores, registry
- `src/taskforce/infrastructure/messaging/` - Message bus adapters
- `src/taskforce/infrastructure/runtime/` - Runtime tracking (heartbeats, checkpoints)
- `src/taskforce/infrastructure/auth/` - Token store / OAuth flow implementations

### Application
- `src/taskforce/application/factory.py` - Dependency injection (central wiring)
- `src/taskforce/application/executor.py` - Execution orchestration (streaming-first)
- `src/taskforce/application/tool_registry.py` - Tool catalog, mapping, and resolution
- `src/taskforce/application/tool_builder.py` - Tool instantiation from definitions
- `src/taskforce/application/agent_registry.py` - Custom agent registration API
- `src/taskforce/application/agent_creation_pipeline.py` - Agent build pipeline
- `src/taskforce/application/config_schema.py` - Pydantic schema helpers
- `src/taskforce/application/gateway.py` - Unified Communication Gateway service
- `src/taskforce/application/profile_loader.py` - Profile YAML loading/resolution
- `src/taskforce/application/system_prompt_assembler.py` - System prompt composition
- `src/taskforce/application/intent_router.py` - Intent routing for chat
- `src/taskforce/application/skill_manager.py` - Skill lifecycle management
- `src/taskforce/application/skill_service.py` - Skill discovery, slash-command resolution
- `src/taskforce/application/plugin_loader.py` - Plugin loading and discovery
- `src/taskforce/application/infrastructure_builder.py` - Infrastructure setup
- `src/taskforce/application/infrastructure_overrides.py` - Optional override hooks (`set_agent_registry_override`, `set_state_manager_override`, `set_gateway_components_override`) used by external packages to replace selected `InfrastructureBuilder` build methods without subclassing
- `src/taskforce/application/sub_agent_spawner.py` - Sub-agent session spawning
- `src/taskforce/application/conversation_manager.py` - Persistent conversation lifecycle (ADR-016)
- `src/taskforce/application/persistent_agent_service.py` - Persistent orchestrator runtime (ADR-016)
- `src/taskforce/application/channel_ask_router.py` - Channel-based user question routing
- `src/taskforce/application/learning_service.py` - Post-mission knowledge extraction (LLM → wiki)
- `src/taskforce/application/workflow_runtime_service.py` - Resumable HITL workflow runtime
- `src/taskforce/application/auth_manager.py` - OAuth2 manager
- `src/taskforce/application/planning_strategy_factory.py` - Planning strategy wiring
- `src/taskforce/application/request_queue.py` - Request buffering
- `src/taskforce/application/topic_detector.py` - Conversation topic detection
- `src/taskforce/application/token_analytics_facade.py` / `tracing_facade.py` - Facades
- `src/taskforce/application/progress_update_builder.py` / `execution_error_handler.py` - Streaming helpers
- `src/taskforce/application/acp_service.py` - ACP application service (ADR-018)

> Epic orchestration (`epic_orchestrator`, `task_complexity_classifier`,
> `epic_state_store`) and butler lifecycle services (`butler_service`, `rule_engine`,
> `event_router`, `learning_service`) have moved to the `taskforce_coding_agent` and
> `taskforce_butler` packages under `agents/`.

### API
- `src/taskforce/api/server.py` - FastAPI application
- `src/taskforce/api/cli/main.py` - Framework-only CLI entry (falls back when `taskforce_cli` is missing)
- `src/taskforce/api/cli/simple_chat.py` - Interactive chat interface
- `src/taskforce/api/cli/commands/` - Framework subcommands (`run`, `chat`, `tools`, `skills`, `missions`, `conversations`, `config`, `memory`, `acp`)
- `src/taskforce/api/routes/` - REST endpoints (execution, agents, sessions, tools, health, gateway, workflows, conversations, …)
- `src/taskforce/api/schemas/` - Request/response schemas
- `cli/src/taskforce_cli/main.py` - Unified CLI that dynamically adds `butler`, `epic`, `rag` commands when the matching package is installed

### Agent Packages
- `agents/butler/` - `taskforce_butler` (daemon, scheduler, event sources, rules, learning, butler roles, tools)
- `agents/coding-agent/` - `taskforce_coding_agent` (epic orchestration, complexity classifier, sub-agent configs)
- `agents/rag-agent/` - `taskforce_rag_agent` (RAG tools, rag_agent profile)
- `agents/security-agent/`, `agents/swe-bench-agent/` - additional agent profiles

### Framework-shipped configs and assets
- `src/taskforce/configs/` - Framework profiles (default, acp_peer, showcase_*)
- `src/taskforce/configs/llm_config.yaml` - Model aliases and LLM routing rules
- `src/taskforce/plugins/` - Bundled plugin agents (ap_poc_agent, document_extraction_agent)
- `src/taskforce/skills/` - Bundled skills (pdf-processing, code-review, data-analysis, documentation, …)

### Examples
- `examples/accounting_agent/` - Full accounting agent with custom tools, skills, rules
- `examples/customer_support_agent/` - Customer support agent example

### MCP Servers
- `servers/document-extraction-mcp/` - Document extraction MCP server (OCR, layout analysis, etc.)

---

## Additional Resources

- **Docs Hub:** `docs/index.md`
- **Architecture:** `docs/architecture.md` (entry) → `docs/architecture/` (sharded pages)
- **CLI Guide:** `docs/cli.md`
- **API Guide:** `docs/api.md`
- **Profiles & Config:** `docs/profiles.md`
- **Testing:** `docs/testing.md`
- **Integrations:** `docs/integrations.md`
- **Features:** `docs/features/` (longterm-memory, skills, enterprise)
- **Plugin System:** `docs/plugins.md`
- **Skills (unified):** `docs/features/skills.md` (context/prompt/agent types, slash-name invocation)
- **C4 Diagrams:** `docs/architecture/c4/` (PlantUML: system context, container, component-level diagrams per layer)
- **ADRs:** `docs/adr/index.md` (19 ADRs: uv, clean architecture, enterprise, multi-agent runtime, epic orchestration, communication providers, unified memory, auto-epic, communication gateway, event-driven butler, unified skills, dynamic LLM selection, memory consolidation, resumable HITL workflows / generative dreaming, parallel sub-agent execution, persistent agent architecture, butler role specialization, ACP protocol support, cooperative agent interruption)
- **Epics:** `docs/epics/index.md` (20+ epic planning documents)
- **PRD:** `docs/prd/index.md`
- **Stories:** `docs/stories/`
- **Coding Standards:** `docs/architecture/coding-standards.md`
- **Examples:** `docs/examples/` (custom tool tutorial, programmatic agent creation)

---

## Quick Reference: Do's and Don'ts

### ✅ DO

- Use `uv` for all package management
- Follow the four-layer architecture strictly
- Write protocol-compatible implementations
- Add comprehensive docstrings (Google style)
- Write tests for all new functionality
- Use type annotations everywhere
- Use concrete types (`dataclass`, Pydantic) instead of `dict`
- Use `Enum` from `core/domain/enums.py` instead of magic strings
- Keep functions ≤30 lines
- Log with structured context via `structlog`
- Make everything async for I/O
- Register new tools in `infrastructure/tools/registry.py`
- **Update docs when changing CLI/API/config** (see Documentation Upkeep Rule above)

### ❌ DON'T

- Import infrastructure in core domain
- Use `pip` or `venv` (use `uv` only)
- Create circular dependencies between layers
- Write blocking I/O (use async)
- Catch generic `Exception` without re-raising
- Skip type annotations
- Use `Dict[str, Any]` for structured data (use dataclasses/Pydantic)
- Use magic strings (use `core/domain/enums.py` enums)
- Create God objects or classes
- Log sensitive data (API keys, passwords)
- Hardcode configuration values
- Use deprecated wrapper classes (`ToolCatalog`, `ToolMapper`, `ToolResolver`)

---

**Last Updated:** 2026-03-22
**For Questions:** See `docs/` or create an issue in the repository
