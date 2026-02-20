# CLAUDE.md - Taskforce Development Guide

**Version:** 1.4
**Date:** 2026-02-20
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
- **Extensibility:** Plugin system, skills, slash commands, MCP tool servers

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
│   ├── domain/                # Agent, LeanAgent, Planning, Events, Models
│   │   └── lean_agent_components/  # Modular agent components
│   ├── interfaces/            # Protocols (18 interface files, ~30 protocol definitions)
│   ├── prompts/               # System prompts and templates
│   ├── tools/                 # Core tool abstractions (converter, planner)
│   └── utils/                 # Path and time utilities
│
├── infrastructure/            # LAYER 2: External Integrations
│   ├── llm/                   # LiteLLM service (multi-provider: OpenAI, Anthropic, Google, Azure, etc.)
│   ├── persistence/           # File state manager, agent registry
│   ├── memory/                # File-based memory store
│   ├── cache/                 # Tool result caching
│   ├── tools/
│   │   ├── native/            # 19 built-in tools
│   │   ├── mcp/               # MCP server connections
│   │   ├── rag/               # Azure AI Search tools
│   │   └── orchestration/     # Agent/sub-agent tools
│   ├── skills/                # Skill loading, parsing, registry
│   ├── slash_commands/        # Slash command loading/parsing
│   └── tracing/               # Phoenix tracing integration
│
├── application/               # LAYER 3: Use Cases & Orchestration
│   ├── factory.py             # Dependency injection (central wiring)
│   ├── executor.py            # Execution orchestration (streaming-first)
│   ├── tool_registry.py       # Tool catalog, mapping, resolution
│   ├── agent_registry.py      # Custom agent registration API
│   ├── gateway.py             # Unified Communication Gateway service
│   ├── profile_loader.py      # Profile YAML loading and resolution
│   ├── system_prompt_assembler.py # System prompt composition
│   ├── intent_router.py       # Intent routing for chat
│   ├── skill_manager.py       # Skill lifecycle management
│   ├── skill_service.py       # Skill execution service
│   ├── slash_command_registry.py  # Slash command registry
│   ├── plugin_loader.py       # Plugin loading from entry points
│   ├── plugin_discovery.py    # Plugin discovery
│   ├── infrastructure_builder.py  # Infrastructure setup
│   ├── epic_orchestrator.py   # Multi-agent epic execution
│   ├── epic_state_store.py    # Epic run state persistence
│   ├── task_complexity_classifier.py  # Auto-epic complexity classification
│   ├── sub_agent_spawner.py   # Sub-agent session spawning
│   ├── tracing_facade.py      # Tracing facade
│   └── command_loader_service.py  # Command loader
│
└── api/                       # LAYER 4: Entrypoints
    ├── server.py              # FastAPI application
    ├── cli/
    │   ├── main.py            # CLI entry point (Typer)
    │   ├── simple_chat.py     # Interactive chat interface
    │   ├── output_formatter.py # Rich output formatting
    │   └── commands/          # CLI subcommands (run, chat, epic, tools, skills, sessions, missions, config)
    ├── routes/                # FastAPI route modules (execution, agents, sessions, tools, health, gateway)
    └── schemas/               # Pydantic request/response schemas
```

### Extensions Package

Separately under `src/taskforce_extensions/`:

```
src/taskforce_extensions/
├── configs/                   # Profile YAML configs (dev, coding_agent, rag_agent, security, etc.)
│   └── custom/                # Custom sub-agent configs
├── infrastructure/
│   ├── communication/         # Communication Gateway components
│   │   ├── gateway_registry.py      # Gateway component wiring
│   │   ├── gateway_conversation_store.py  # Conversation persistence
│   │   ├── inbound_adapters.py      # Channel-specific inbound adapters
│   │   ├── outbound_senders.py      # Channel-specific outbound senders
│   │   └── recipient_registry.py    # Push notification recipient store
│   ├── messaging/             # In-memory message bus
│   └── runtime/               # Runtime tracking (heartbeats, checkpoints)
├── plugins/                   # Plugin agents (ap_poc_agent, document_extraction_agent)
└── skills/                    # Skill scripts (PDF processing, etc.)
```

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

**18 interface files** in `core/interfaces/` with **~30 protocol definitions**:

| Protocol(s) | File | Purpose |
|-------------|------|---------|
| `StateManagerProtocol` | `state.py` | Session state persistence |
| `LLMProviderProtocol` | `llm.py` | LLM provider abstraction |
| `ToolProtocol` | `tools.py` | Tool execution interface (also defines `ApprovalRiskLevel` enum) |
| `MemoryStoreProtocol` | `memory_store.py` | Long-term memory storage |
| `OutboundSenderProtocol`, `InboundAdapterProtocol`, `ConversationStoreProtocol`, `RecipientRegistryProtocol` | `gateway.py` | Communication Gateway contracts |
| `MessageBusProtocol` | `messaging.py` | Inter-agent messaging |
| `HeartbeatStoreProtocol`, `CheckpointStoreProtocol`, `AgentRuntimeTrackerProtocol` | `runtime.py` | Runtime tracking |
| `SkillProtocol`, `SkillMetadata`, `SkillRegistryProtocol`, `SkillContextProtocol` | `skills.py` | Skill interface and lifecycle |
| `SlashCommandLoaderProtocol` | `slash_commands.py` | Slash command loading |
| `ToolMapperProtocol` | `tool_mapping.py` | Tool name resolution |
| `ToolResultStoreProtocol` | `tool_result_store.py` | Tool result caching |
| `SubAgentSpawnerProtocol` | `sub_agents.py` | Sub-agent spawning |
| `TenantContextProtocol`, `UserContextProtocol`, `IdentityProviderProtocol`, `PolicyEngineProtocol` | `identity_stubs.py` | Identity and tenancy management |
| `LoggerProtocol` | `logging.py` | Structured logging |
| `EventSourceProtocol` | `event_source.py` | External event source (butler) |
| `SchedulerProtocol` | `scheduler.py` | Job scheduling (butler) |
| `RuleEngineProtocol` | `rule_engine.py` | Rule evaluation (butler) |
| `LearningStrategyProtocol` | `learning.py` | Automatic learning (butler) |

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
agent = await factory.create_agent(config="src/taskforce_extensions/configs/custom/coding_worker.yaml")

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
- If inline parameters → settings from parameters (with sensible defaults from `dev.yaml`)

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

### 5. Domain Enums

All status values, event types, and action constants are defined in `core/domain/enums.py` to eliminate magic strings:

- `ExecutionStatus` - completed, failed, pending, paused
- `TaskStatus` - PENDING, DONE
- `EventType` - started, step_start, llm_token, tool_call, tool_result, ask_user, plan_updated, complete, error, etc.
- `LLMStreamEventType` - token, tool_call_start, tool_call_delta, tool_call_end, done
- `PlannerAction` - create_plan, mark_done, read_plan, update_plan
- `LLMAction` - tool_call, respond, ask_user
- `MessageRole` - user, assistant, system, tool

### 6. Error Handling

Execution API errors use a standardized payload (`code`, `message`, `details`, optional `detail`) via `ErrorResponse`, with responses emitted from `HTTPException` objects tagged by the `X-Taskforce-Error: 1` header.

Exception types live in `src/taskforce/core/domain/errors.py` (`TaskforceError`, `LLMError`, `ToolError`, etc.). Infrastructure tools should convert unexpected failures into `ToolError` payloads via `tool_error_payload`.

---

## Native Tools

19 built-in tools in `infrastructure/tools/native/`:

| Tool | File | Description |
|------|------|-------------|
| File Read/Write | `file_tools.py` | File operations |
| Shell | `shell_tool.py` | Shell command execution (shell + powershell) |
| Python | `python_tool.py` | Python code execution (isolated namespace) |
| Git | `git_tools.py` | Git and GitHub operations |
| Web | `web_tools.py` | HTTP requests, web crawling (web_search + web_fetch) |
| Browser | `browser_tool.py` | Headless browser automation via Playwright (requires `uv sync --extra browser && playwright install chromium`) |
| Search | `search_tools.py` | Grep/glob-style search |
| Edit | `edit_tool.py` | Targeted file editing |
| LLM | `llm_tool.py` | Delegated LLM calls |
| Memory | `memory_tool.py` | Long-term memory CRUD |
| Multimedia | `multimedia_tool.py` | Image/media handling |
| Ask User | `ask_user_tool.py` | Interactive user prompts |
| Activate Skill | `activate_skill_tool.py` | Runtime skill activation |
| Send Notification | `send_notification_tool.py` | Proactive push notifications via Communication Gateway |
| Calendar | `calendar_tool.py` | Google Calendar list/create (butler) |
| Schedule | `schedule_tool.py` | Cron/interval/one-shot job management (butler) |
| Reminder | `reminder_tool.py` | One-shot reminder creation (butler) |
| Rule Manager | `rule_manager_tool.py` | Event-to-action trigger rule management (butler) |

Additional tool categories:
- **RAG Tools** (`infrastructure/tools/rag/`): Azure AI Search integration (semantic search, document retrieval, global analysis)
- **MCP Tools** (`infrastructure/tools/mcp/`): Model Context Protocol server connections
- **Orchestration Tools** (`infrastructure/tools/orchestration/`): Agent invocation, sub-agent spawning

Profile YAML tool lists use **short tool names** (e.g., `file_read`, `rag_semantic_search`) instead of full type/module specs. The tool registry in `infrastructure/tools/registry.py` maps short names to implementations.

Tool parallelism is opt-in per tool via `supports_parallelism` and controlled by `agent.max_parallel_tools` (default 4) in profile YAML.

---

## Skills, Slash Commands, and Plugins

### Skills

File-based skill definitions that can be activated at runtime. Skills are YAML+Markdown files that define specialized agent behaviors with custom prompts, tools, and workflows.

- **Storage:** Project-level in `.taskforce/skills/` or bundled with plugins/extensions
- **Management:** `SkillManager` (application layer) handles lifecycle
- **Activation:** Via `activate_skill` tool or `/skills` chat command
- **Docs:** `docs/features/skills.md`

### Slash Commands

Flexible, file-based commands defined as Markdown files with optional YAML frontmatter.

- **Storage:** Project-wide in `.taskforce/commands/` or user-specific in `~/.taskforce/commands/`. Project-level overrides user-level.
- **Naming:** Hierarchical based on folder structure (e.g., `agents/reviewer.md` → `/agents:reviewer`)
- **Types:**
  - `prompt`: Simple prompt templates where `$ARGUMENTS` is replaced by user input
  - `agent`: Defines a specialized agent with its own `profile`, `tools`, and `system_prompt`
- **Behavior:** An `agent`-type command temporarily overrides the current agent's configuration for that single execution
- **Built-ins:** Chat includes `/plugins` and `/skills` for discovery, and `/<plugin_name>` switches to a plugin agent
- **Docs:** `docs/slash-commands.md`

### Plugin System

Plugins extend Taskforce with custom agents, tools, and configurations via Python entry points.

- **Discovery:** `setuptools` entry points under `taskforce.plugins`
- **Structure:** Each plugin provides configs, tools, and optional domain logic
- **Loading:** `PluginLoader` and `PluginDiscovery` in the application layer
- **Examples:** `src/taskforce_extensions/plugins/ap_poc_agent/`, `document_extraction_agent/`
- **Docs:** `docs/plugins.md`

---

## Epic Orchestration

Multi-agent pipeline for complex, multi-step tasks using planner/worker/judge roles:

- **Orchestrator:** `src/taskforce/application/epic_orchestrator.py`
- **Auto-Epic Classifier:** `src/taskforce/application/task_complexity_classifier.py`
- **State:** Persisted under `.taskforce/epic_runs/<run_id>/` with `MISSION.md`, `CURRENT_STATE.md`, `MEMORY.md`
- **Profiles:** Planner, worker, judge configs in `src/taskforce_extensions/configs/`
- **CLI:** `taskforce epic` command with `--rounds` option for iterative refinement; `taskforce run mission --auto-epic` for automatic detection
- **Config:** `orchestration.auto_epic` section in profile YAML (see `AutoEpicConfig` in `core/domain/config_schema.py`)
- **Docs:** `docs/architecture/epic-orchestration.md`
- **ADR:** `docs/adr/adr-008-auto-epic-orchestration.md`

---

## Communication Gateway

The unified Communication Gateway replaces the earlier per-provider communication model. It provides a single entry point for all channel-based agent communication (Telegram, Teams, Slack, REST, etc.).

### Architecture

- **Protocols:** `core/interfaces/gateway.py` (4 protocols: `OutboundSenderProtocol`, `InboundAdapterProtocol`, `ConversationStoreProtocol`, `RecipientRegistryProtocol`)
- **Domain Models:** `core/domain/gateway.py` (`InboundMessage`, `GatewayOptions`, `GatewayResponse`, `NotificationRequest`, `NotificationResult`)
- **Gateway Service:** `application/gateway.py` (`CommunicationGateway`) - orchestrates inbound processing, session management, agent execution, outbound replies, and proactive push
- **API Routes:** `api/routes/gateway.py`:
  - `POST /gateway/{channel}/messages` - handle inbound messages from any channel
  - `POST /gateway/{channel}/webhook` - handle raw provider webhooks (Telegram, Teams)
  - `POST /gateway/notify` - send proactive push notifications
  - `POST /gateway/broadcast` - broadcast to all recipients on a channel
  - `GET  /gateway/channels` - list configured channels
- **Send Notification Tool:** `infrastructure/tools/native/send_notification_tool.py` - allows agents to proactively push messages
- **Extension Implementations:** `taskforce_extensions/infrastructure/communication/`:
  - `gateway_registry.py` - Component wiring and factory
  - `gateway_conversation_store.py` - File-based conversation persistence
  - `inbound_adapters.py` - Channel-specific payload normalization
  - `outbound_senders.py` - Channel-specific message dispatch
  - `recipient_registry.py` - Push notification recipient store
- **Persistence:** Chat history in `.taskforce/conversations/`
- **ADRs:** `docs/adr/adr-006-communication-providers.md` (original), `docs/adr/adr-009-communication-gateway.md` (current)
- **Docs:** `docs/integrations.md`

---

## Butler Agent (Event-Driven Architecture)

The Butler is a proactive, event-driven agent daemon that runs 24/7 and acts as a personal assistant. See **[ADR-010](docs/adr/adr-010-event-driven-butler-agent.md)** for the full architecture.

### Key Components

| Component | Layer | File(s) | Purpose |
|-----------|-------|---------|---------|
| `AgentEvent` | Core/Domain | `core/domain/agent_event.py` | Event model from external sources |
| `ScheduleJob` | Core/Domain | `core/domain/schedule.py` | Scheduled job model (cron/interval/one-shot) |
| `TriggerRule` | Core/Domain | `core/domain/trigger_rule.py` | Event-to-action rule model |
| `EventSourceProtocol` | Core/Interfaces | `core/interfaces/event_source.py` | External event source contract |
| `SchedulerProtocol` | Core/Interfaces | `core/interfaces/scheduler.py` | Job scheduling contract |
| `RuleEngineProtocol` | Core/Interfaces | `core/interfaces/rule_engine.py` | Rule evaluation contract |
| `LearningStrategyProtocol` | Core/Interfaces | `core/interfaces/learning.py` | Automatic learning contract |
| `SchedulerService` | Infrastructure | `infrastructure/scheduler/scheduler_service.py` | Asyncio-based scheduler |
| `FileJobStore` | Infrastructure | `infrastructure/scheduler/job_store.py` | Job persistence |
| `CalendarEventSource` | Infrastructure | `infrastructure/event_sources/calendar_source.py` | Google Calendar polling |
| `WebhookEventSource` | Infrastructure | `infrastructure/event_sources/webhook_source.py` | HTTP webhook receiver |
| `RuleEngine` | Application | `application/rule_engine.py` | Rule evaluation and persistence |
| `EventRouter` | Application | `application/event_router.py` | Event-to-action dispatch |
| `ButlerService` | Application | `application/butler_service.py` | Butler lifecycle orchestration |
| `LearningService` | Application | `application/learning_service.py` | Auto-extraction from conversations |
| `ButlerDaemon` | API | `api/butler_daemon.py` | Top-level daemon process |
| Butler CLI | API | `api/cli/commands/butler.py` | `taskforce butler` commands |

### Running the Butler

```bash
# Start the butler daemon
taskforce butler start --profile butler

# Check butler status
taskforce butler status

# Manage trigger rules
taskforce butler rules list
taskforce butler rules add --name "calendar_reminder" --source calendar --type calendar.upcoming

# View scheduled jobs
taskforce butler schedules list
```

### Butler Profile

The butler profile (`src/taskforce_extensions/configs/butler.yaml`) configures event sources, trigger rules, scheduler, and notification defaults.

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
uv sync --extra pdf            # PDF processing
uv sync --extra personal-assistant  # Google Calendar/API

# For browser tool: also install Playwright browsers
playwright install chromium

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
├── taskforce_extensions/  # Extension tests
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

Taskforce uses YAML configuration profiles. Built-in profiles are in `src/taskforce_extensions/configs/`:

- `dev.yaml` - Default development profile
- `coding_agent.yaml` - Coding specialist with sub-agents
- `rag_agent.yaml` - RAG-enabled agent
- `security.yaml` - Security-hardened profile
- `orchestrator.yaml`, `planner.yaml`, `worker.yaml`, `judge.yaml` - Epic orchestration roles
- `butler.yaml` - Butler daemon profile (event sources, scheduler, notifications)
- `custom/` - Custom sub-agent configs (coding_planner, coding_worker, coding_reviewer, etc.)

```yaml
# src/taskforce_extensions/configs/dev.yaml
profile: dev
specialist: null

persistence:
  type: file
  work_dir: .taskforce

runtime:
  enabled: true
  store: file
  work_dir: .taskforce

agent:
  planning_strategy: native_react
  max_steps: 30

llm:
  config_path: src/taskforce_extensions/configs/llm_config.yaml
  default_model: main

logging:
  level: DEBUG
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
  - python
  - powershell
  - ask_user
```

### Optional Dependency Groups

Defined in `pyproject.toml` under `[project.optional-dependencies]`:

| Group | Purpose | Install Command |
|-------|---------|-----------------|
| `browser` | Playwright headless browser automation | `uv sync --extra browser` |
| `rag` | Azure AI Search integration | `uv sync --extra rag` |
| `pdf` | PDF processing (pypdf, pdfplumber, reportlab) | `uv sync --extra pdf` |
| `personal-assistant` | Google Calendar/API integration | `uv sync --extra personal-assistant` |
| `dev` | Testing and linting tools | `uv sync --extra dev` |
| `build` | Package building and publishing | `uv sync --extra build` |

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

### Enabling Long-Term Memory

The native `memory` tool provides file-backed Markdown records for long-term memory. Configure via profile YAML:

```yaml
# In profile YAML
memory:
  store_dir: .taskforce/.memory
```

Alternatively, use an MCP Memory Server for knowledge graph-based memory:

```yaml
mcp_servers:
  - type: stdio
    command: npx
    args: ["-y", "@modelcontextprotocol/server-memory"]
    env:
      MEMORY_FILE_PATH: ".taskforce/.memory/knowledge_graph.jsonl"
    description: "Long-term knowledge graph memory"
```

**See:** [Long-Term Memory Documentation](docs/features/longterm-memory.md), [ADR-007](docs/adr/adr-007-unified-memory-service.md)

### Adding a New Tool

1. **Create tool in infrastructure layer:**

```python
# infrastructure/tools/native/my_tool.py
from typing import Dict, Any
from taskforce.core.interfaces.tools import ToolProtocol

class MyTool:
    """Description of what the tool does."""

    @property
    def name(self) -> str:
        return "my_tool"

    @property
    def description(self) -> str:
        return "Performs X operation on Y input"

    @property
    def parameters_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "input": {"type": "string", "description": "Input data"}
            },
            "required": ["input"]
        }

    async def execute(self, **params) -> Dict[str, Any]:
        """Execute the tool."""
        input_data = params["input"]
        # Tool logic here...
        return {"result": "...", "success": True}

    def validate_parameters(self, params: Dict[str, Any]) -> bool:
        """Validate parameters match schema."""
        return "input" in params
```

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

**Agent Components - Call Directly:**

```python
# ✅ CORRECT - Call component methods directly
messages = await agent.message_history_manager.compress_messages(messages)
messages = agent.message_history_manager.preflight_budget_check(messages)
tool_msg = await agent.tool_result_message_factory.build_message(...)

# ❌ AVOID - Wrapper methods have been removed
# messages = await agent._compress_messages(messages)
```

### 4. Sub-Agent Spawning

Sub-agent spawning is centralized in `application/sub_agent_spawner.py` to standardize isolated session creation. The `coding_agent` profile delegates to custom sub-agents defined in `src/taskforce_extensions/configs/custom/`.

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

### Protocols (core/interfaces/)
- `state.py` - `StateManagerProtocol` - session state persistence
- `llm.py` - `LLMProviderProtocol` - LLM provider abstraction
- `tools.py` - `ToolProtocol`, `ApprovalRiskLevel` - tool execution interface
- `memory_store.py` - `MemoryStoreProtocol` - memory storage
- `gateway.py` - `OutboundSenderProtocol`, `InboundAdapterProtocol`, `ConversationStoreProtocol`, `RecipientRegistryProtocol` - Communication Gateway
- `messaging.py` - `MessageBusProtocol` - inter-agent messaging
- `runtime.py` - `HeartbeatStoreProtocol`, `CheckpointStoreProtocol`, `AgentRuntimeTrackerProtocol` - runtime tracking
- `skills.py` - `SkillProtocol`, `SkillMetadata`, `SkillRegistryProtocol`, `SkillContextProtocol` - skill lifecycle
- `slash_commands.py` - `SlashCommandLoaderProtocol` - slash command loading
- `tool_mapping.py` - `ToolMapperProtocol` - tool name resolution
- `tool_result_store.py` - `ToolResultStoreProtocol` - tool result caching
- `sub_agents.py` - `SubAgentSpawnerProtocol` - sub-agent spawning
- `identity_stubs.py` - `TenantContextProtocol`, `UserContextProtocol`, `IdentityProviderProtocol`, `PolicyEngineProtocol` - identity/tenancy
- `logging.py` - `LoggerProtocol` - structured logging
- `event_source.py` - `EventSourceProtocol` - external event sources (butler)
- `scheduler.py` - `SchedulerProtocol` - job scheduling (butler)
- `rule_engine.py` - `RuleEngineProtocol` - rule evaluation (butler)
- `learning.py` - `LearningStrategyProtocol` - automatic learning (butler)

### Infrastructure
- `src/taskforce/infrastructure/persistence/file_state_manager.py` - File-based state
- `src/taskforce/infrastructure/persistence/file_agent_registry.py` - File-based agent registry
- `src/taskforce/infrastructure/llm/litellm_service.py` - Unified LLM service (multi-provider via LiteLLM)
- `src/taskforce/infrastructure/llm/openai_service.py` - Backward-compatible alias (imports LiteLLMService)
- `src/taskforce/infrastructure/memory/file_memory_store.py` - File-based memory
- `src/taskforce/infrastructure/cache/tool_result_store.py` - Tool result caching
- `src/taskforce/infrastructure/tools/registry.py` - Tool short-name registry (19 native + RAG tools)
- `src/taskforce/infrastructure/tools/native/*.py` - 19 native tools (incl. browser, send_notification, butler tools)
- `src/taskforce/infrastructure/tools/mcp/connection_manager.py` - MCP connections
- `src/taskforce/infrastructure/scheduler/scheduler_service.py` - Asyncio-based job scheduler (butler)
- `src/taskforce/infrastructure/scheduler/job_store.py` - File-based job persistence (butler)
- `src/taskforce/infrastructure/event_sources/base.py` - Polling event source base class (butler)
- `src/taskforce/infrastructure/event_sources/calendar_source.py` - Google Calendar polling (butler)
- `src/taskforce/infrastructure/event_sources/webhook_source.py` - HTTP webhook receiver (butler)
- `src/taskforce/infrastructure/tools/rag/*.py` - RAG tools (Azure AI Search)
- `src/taskforce/infrastructure/tools/orchestration/*.py` - Agent/sub-agent tools
- `src/taskforce/infrastructure/skills/` - Skill loading/parsing/registry
- `src/taskforce/infrastructure/slash_commands/` - Slash command loading/parsing
- `src/taskforce/infrastructure/tracing/phoenix_tracer.py` - Phoenix tracing

### Application
- `src/taskforce/application/factory.py` - Dependency injection (central wiring)
- `src/taskforce/application/executor.py` - Execution orchestration (streaming-first)
- `src/taskforce/application/tool_registry.py` - Tool catalog, mapping, and resolution
- `src/taskforce/application/agent_registry.py` - Custom agent registration API
- `src/taskforce/application/gateway.py` - Unified Communication Gateway service
- `src/taskforce/application/profile_loader.py` - Profile YAML loading/resolution (extracted from factory)
- `src/taskforce/application/system_prompt_assembler.py` - System prompt composition (extracted from factory)
- `src/taskforce/application/intent_router.py` - Intent routing for chat
- `src/taskforce/application/skill_manager.py` - Skill lifecycle management
- `src/taskforce/application/skill_service.py` - Skill execution service
- `src/taskforce/application/slash_command_registry.py` - Slash command registry
- `src/taskforce/application/plugin_loader.py` - Plugin loading
- `src/taskforce/application/plugin_discovery.py` - Plugin discovery
- `src/taskforce/application/infrastructure_builder.py` - Infrastructure setup
- `src/taskforce/application/rule_engine.py` - Trigger rule evaluation and persistence (butler)
- `src/taskforce/application/event_router.py` - Event-to-action dispatch (butler)
- `src/taskforce/application/butler_service.py` - Butler lifecycle orchestration (butler)
- `src/taskforce/application/learning_service.py` - Auto-extraction from conversations (butler)
- `src/taskforce/application/epic_orchestrator.py` - Epic orchestration
- `src/taskforce/application/task_complexity_classifier.py` - Auto-epic complexity classification
- `src/taskforce/application/epic_state_store.py` - Epic state persistence
- `src/taskforce/application/sub_agent_spawner.py` - Sub-agent session spawning
- `src/taskforce/application/tracing_facade.py` - Tracing facade

### API
- `src/taskforce/api/server.py` - FastAPI application
- `src/taskforce/api/cli/main.py` - CLI entry point
- `src/taskforce/api/cli/simple_chat.py` - Interactive chat interface
- `src/taskforce/api/cli/commands/` - CLI subcommands (run, chat, epic, tools, skills, sessions, missions, config, butler)
- `src/taskforce/api/cli/commands/butler.py` - Butler daemon CLI commands (butler)
- `src/taskforce/api/butler_daemon.py` - Butler daemon process (butler)
- `src/taskforce/api/routes/` - REST endpoints (execution, agents, sessions, tools, health, gateway)
- `src/taskforce/api/routes/gateway.py` - Unified Communication Gateway routes
- `src/taskforce/api/schemas/` - Request/response schemas

### Extensions
- `src/taskforce_extensions/configs/` - Profile YAML configs (dev, coding_agent, rag_agent, security, butler, orchestration roles)
- `src/taskforce_extensions/infrastructure/communication/` - Communication Gateway components (adapters, senders, stores, registry)
- `src/taskforce_extensions/infrastructure/messaging/` - Message bus adapters
- `src/taskforce_extensions/infrastructure/runtime/` - Runtime tracking (heartbeats, checkpoints)
- `src/taskforce_extensions/plugins/` - Plugin agents

### Examples
- `examples/accounting_agent/` - Full accounting agent with custom tools, skills, rules
- `examples/customer_support_agent/` - Customer support agent example
- `examples/personal_assistant/` - Personal assistant with calendar, email, task tools and skills

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
- **Slash Commands:** `docs/slash-commands.md`
- **C4 Diagrams:** `docs/architecture/c4/` (PlantUML: system context, container, component-level diagrams per layer)
- **ADRs:** `docs/adr/index.md` (10 ADRs: uv, clean architecture, enterprise, multi-agent, epic orchestration, communication providers, unified memory, auto-epic, communication gateway, event-driven butler)
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

**Last Updated:** 2026-02-20
**For Questions:** See `docs/` or create an issue in the repository
