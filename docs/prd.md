# Taskforce - Clean Architecture Migration PRD

**Version:** 1.0  
**Date:** 2025-11-22  
**Author:** John (PM Agent)

---

## 1. Intro Project Analysis and Context

### Analysis Source
**IDE-based fresh analysis** with reference to existing brownfield-architecture.md documentation

### Current Project State

Based on analysis of the Agent V2 codebase (`capstone/agent_v2`):

**Current Capabilities:**
- **ReAct Execution Engine**: Thought → Action → Observation loop orchestrating LLM-driven reasoning
- **TodoList Planning**: LLM-based task decomposition with dependency tracking (`planning/todolist.py`)
- **Tool System**: 11+ tools including Python execution, file I/O, Git operations, web search, RAG semantic search
- **State Management**: File-based session persistence via `statemanager.py` with async I/O
- **Rich CLI Interface**: Typer-based CLI with 8 command groups (run, chat, missions, tools, sessions, rag, config, dev)
- **Multi-Provider LLM Support**: OpenAI and Azure OpenAI via LiteLLM abstraction (`services/llm_service.py`)
- **Agent Specialization**: Factory methods for generic agents and RAG agents with different system prompts
- **Memory System**: Cross-session learning via memory extraction (`memory/memory_manager.py`)

**Current Architecture (PoC Flat Structure):**
```
capstone/agent_v2/
├── agent.py                    # Core ReAct loop + factory (220 lines)
├── agent_factory.py            # Agent construction
├── statemanager.py             # File-based persistence
├── tool.py                     # Base tool class
├── planning/todolist.py        # Planning logic + persistence
├── services/llm_service.py     # LLM abstraction
├── tools/*.py                  # 11+ tool implementations
├── cli/                        # CLI interface (separate concern)
└── agent_service/              # Empty placeholder for microservice
```

**Key Observation:** The `agent_service/` directory structure (with `api/`, `core/`, `db/`, `models/` subdirectories) already exists but contains no implementation files - indicating the structure was scaffolded but the migration has not been executed.

### Available Documentation Analysis

**Available Documentation:**
- ✅ **Tech Stack Documentation**: Fully documented in `docs/brownfield-architecture.md` (Python 3.11, LiteLLM, Typer, Rich, structlog, Azure AI Search)
- ✅ **Source Tree/Architecture**: Comprehensive current-state documentation available (brownfield-architecture.md with 1,345 lines)
- ⚠️ **Coding Standards**: Partially documented via `.cursor/rules/python_coding_rules.mdc` and CLAUDE.md (PEP8, Black/Ruff, functional style, ≤30 line functions)
- ✅ **API Documentation**: Module docstrings and inline comments present in core files
- ⚠️ **External API Documentation**: Azure AI Search integration documented, some tool APIs partially documented
- ❌ **UX/UI Guidelines**: Not applicable (CLI and API only)
- ⚠️ **Technical Debt Documentation**: Scattered comments in brownfield-architecture.md about isolated Python namespaces and tool execution constraints
- ✅ **Clean Architecture Target**: User-provided detailed specification in the conversation (Hexagonal Architecture with core/infrastructure/application/api layers)

**Assessment:** The existing documentation provides excellent "as-is" analysis. The user's provided specification gives a clear "to-be" target architecture. This PRD will bridge the gap by defining the migration path.

### Enhancement Scope Definition

**Enhancement Type:**
- ☑️ **Technology Stack Upgrade** (architectural pattern upgrade)
- ☑️ **Major Feature Modification** (refactoring for production-readiness)

**Enhancement Description:**

Create the **Taskforce production framework** in a new top-level directory (`taskforce/`) by reorganizing and adapting proven code from Agent V2 (`capstone/agent_v2`) into a **production-ready microservice architecture** based on **Clean Architecture / Hexagonal Architecture** principles. The refactoring enforces strict separation of concerns by organizing code into four distinct layers:

1. **Core Layer** (domain logic): Pure business logic with zero dependencies on infrastructure
2. **Infrastructure Layer** (adapters): Database, LLM providers, tool implementations
3. **Application Layer** (use cases): Service orchestration and dependency injection via factory
4. **API Layer** (entrypoints): FastAPI REST API and CLI interfaces

The implementation maximizes code reuse from Agent V2 (≥75% of working logic relocated rather than rewritten) while establishing architectural boundaries that enable independent evolution of the agent engine, persistence layer, tool ecosystem, and API interfaces.

**Impact Assessment:** ☑️ **Major Impact (architectural changes required)**

**Rationale:**
- New directory structure at `taskforce/` with Clean Architecture layers (core, infrastructure, application, api)
- Agent V2 remains untouched - serves as reference implementation and operational fallback
- All existing modules require relocation to appropriate layers with protocol-based interfaces
- File-based `StateManager` coexists with new database-backed `DbStateManager` via shared protocol
- Agent factory evolves into comprehensive dependency injection container
- FastAPI service layer requires full implementation for microservice deployment
- Extensive test suite adapted to new module structure with protocol-based mocking
- **However:** The core ReAct algorithm, TodoList logic, and tool execution semantics remain unchanged - this is code reorganization with maximum reuse, not reimplementation

### Goals and Background Context

**Goals:**
- **G1:** Establish strict architectural boundaries preventing domain logic from depending on infrastructure (database, external APIs)
- **G2:** Enable swappable persistence backends (file-based for dev, PostgreSQL for production) via protocol-based abstractions
- **G3:** Support microservice deployment via production-ready FastAPI REST API with observability (logging, metrics, health checks)
- **G4:** Maintain 100% backward compatibility for CLI users through similar command structure
- **G5:** Improve testability by isolating core domain logic from I/O operations via protocol mocking
- **G6:** Prepare codebase for enterprise deployment with clear extension points for new tools, LLM providers, and persistence adapters

**Background Context:**

The current Agent V2 codebase is a successful **Proof of Concept** demonstrating ReAct agent capabilities with TodoList planning, tool execution, and state management. However, the flat module structure exhibits typical PoC characteristics:

1. **Tightly Coupled Layers**: `agent.py` (domain logic) directly imports `statemanager.py` (infrastructure), making it impossible to swap persistence backends without modifying core logic.

2. **Testability Challenges**: Testing the ReAct loop requires actual file I/O, LLM API calls, and tool execution - no clean seams for mocking.

3. **Circular Dependency Risk**: The factory imports everything, tools import helpers, and helpers import domain classes, creating fragile dependency graphs.

4. **Deployment Inflexibility**: The current structure doesn't support running as a stateless microservice - it assumes local filesystem access for state persistence.

**Why Clean Architecture / Hexagonal Architecture?**

The user correctly identified that for **production-grade enterprise deployment**, the system requires:

- **"Separation of Concerns"**: Core business logic must not know about PostgreSQL, FastAPI, or specific LLM providers
- **Testability**: The domain should be testable with zero external dependencies
- **Swappable Adapters**: Switch from file-based state to database state with configuration changes only
- **Extension Points**: Add MCP tool integration, new LLM providers, or API authentication without touching domain code
- **Team Scalability**: Multiple developers can work on API layer, tool implementations, and core logic independently

The migration to Clean Architecture transforms the codebase from a "working prototype" to an "enterprise-grade microservice" suitable for long-term maintenance and multi-team development. By creating Taskforce as a new framework rather than refactoring Agent V2 in place, we eliminate risk to the operational PoC while applying lessons learned.

### Change Log

| Change | Date | Version | Description | Author |
|--------|------|---------|-------------|--------|
| Initial PRD | 2025-11-22 | 1.0 | Clean Architecture migration planning | John (PM Agent) |

---

## 2. Requirements

**Section Context:** These requirements define how to build the Taskforce framework using the **specific Clean Architecture structure provided**, reorganizing proven code from Agent V2 into the four-layer architecture (`core/`, `infrastructure/`, `application/`, `api/`) with maximum code reuse.

### Functional Requirements

**FR1: Project Structure** - The Taskforce framework shall be created in a new top-level directory `taskforce/` (sibling to `capstone/`) with the following structure:
```
taskforce/
├── pyproject.toml              # Package definition, dependencies, CLI entry point
├── config.yaml                 # Default configuration
├── src/taskforce/
│   ├── core/                   # LAYER 1: Pure Business Logic
│   │   ├── domain/
│   │   │   ├── agent.py        # ReAct state machine (from agent_v2/agent.py)
│   │   │   ├── plan.py         # TodoList domain logic (from planning/todolist.py)
│   │   │   └── events.py       # Event types (Thought, Action, Observation)
│   │   └── interfaces/         # Ports (Protocol definitions)
│   │       ├── state.py        # StateManagerProtocol
│   │       ├── tools.py        # ToolProtocol
│   │       └── llm.py          # LLMProviderProtocol
│   │
│   ├── infrastructure/         # LAYER 2: Adapters & IO
│   │   ├── persistence/
│   │   │   ├── db_state.py     # PostgreSQL StateManager (new)
│   │   │   ├── file_state.py   # File StateManager (from statemanager.py)
│   │   │   ├── db_todolist.py  # PostgreSQL TodoList adapter (new)
│   │   │   └── file_todolist.py # File TodoList adapter (from todolist.py)
│   │   ├── llm/
│   │   │   └── openai_service.py # LLM service (from services/llm_service.py)
│   │   └── tools/
│   │       ├── native/         # Core tools (from tools/*.py)
│   │       ├── mcp/            # MCP client wrapper (future)
│   │       └── rag/            # RAG tools (from tools/rag_*.py)
│   │
│   ├── application/            # LAYER 3: Use Cases & Orchestration
│   │   ├── factory.py          # Dependency injection (from agent_factory.py)
│   │   ├── executor.py         # Service orchestrating ReAct loop
│   │   └── profiles.py         # YAML profile loader
│   │
│   └── api/                    # LAYER 4: Entrypoints
│       ├── server.py           # FastAPI app
│       ├── routes/
│       │   └── execution.py    # Agent execution endpoints
│       ├── deps.py             # FastAPI dependencies
│       └── cli/                # CLI interface (adapted from cli/)
│
└── tests/                      # Mirror of src/ structure
    ├── unit/
    ├── integration/
    └── fixtures/
```

**FR2: Core Domain Layer** - The `src/taskforce/core/domain/` shall contain pure business logic with **zero external dependencies**:
- `agent.py`: Extract ReAct loop from `agent_v2/agent.py:Agent.execute()`, refactored to accept dependencies via protocols defined in `core/interfaces/`
- `plan.py`: Extract TodoList domain logic from `agent_v2/planning/todolist.py` (plan generation, status transitions, dependency validation) with persistence delegated to infrastructure
- `events.py`: Define event types for Thought, Action, Observation used in the ReAct loop

**FR3: Core Interfaces Layer** - The `src/taskforce/core/interfaces/` shall define protocol contracts:
- `state.py`: `StateManagerProtocol` with methods: `save_state()`, `load_state()`, `delete_state()`, `list_sessions()`
- `tools.py`: `ToolProtocol` based on `agent_v2/tool.py` with `name`, `description`, `parameters_schema`, `execute()` 
- `llm.py`: `LLMProviderProtocol` with methods: `complete()`, `generate()`, matching `agent_v2/services/llm_service.py` public API

**FR4: Infrastructure Persistence Layer** - The `src/taskforce/infrastructure/persistence/` shall provide state and plan storage:
- `file_state.py`: **Relocate** `agent_v2/statemanager.py` with minimal changes, implementing `StateManagerProtocol`
- `db_state.py`: **New implementation** for PostgreSQL-backed state storage, implementing same protocol
- `file_todolist.py`: Extract persistence logic from `agent_v2/planning/todolist.py`
- `db_todolist.py`: **New implementation** for database-backed TodoList storage

**FR5: Infrastructure LLM Layer** - The `src/taskforce/infrastructure/llm/openai_service.py` shall:
- **Relocate** `agent_v2/services/llm_service.py` with all existing functionality (model aliases, parameter mapping, retry logic)
- **Implement** `LLMProviderProtocol` from `core/interfaces/llm.py`
- **Preserve** LiteLLM integration, configuration schema, and Azure OpenAI support

**FR6: Infrastructure Tools Layer** - The `src/taskforce/infrastructure/tools/` shall organize tool implementations:
- `native/`: **Copy** all existing tools from `agent_v2/tools/`:
  - `code_tool.py` → `python_tool.py` (PythonTool)
  - `file_tool.py` → `file_tools.py` (FileReadTool, FileWriteTool)
  - `git_tool.py` → `git_tools.py` (GitTool, GitHubTool)
  - `shell_tool.py` → `shell_tool.py` (PowerShellTool)
  - `web_tool.py` → `web_tools.py` (WebSearchTool, WebFetchTool)
  - `llm_tool.py` → `llm_tool.py` (LLMTool)
  - `ask_user_tool.py` → `ask_user_tool.py` (AskUserTool)
- `rag/`: **Copy** RAG tools from `agent_v2/tools/`:
  - `rag_semantic_search_tool.py` → `semantic_search.py`
  - `rag_list_documents_tool.py` → `list_documents.py`
  - `rag_get_document_tool.py` → `get_document.py`
  - `azure_search_base.py` → `azure_search_base.py`
- `mcp/`: **Future placeholder** for Model Context Protocol integration

**FR7: Application Layer** - The `src/taskforce/application/` shall orchestrate the system:
- `factory.py`: **Adapt** `agent_v2/agent_factory.py` to wire domain objects with infrastructure adapters based on configuration profiles
- `executor.py`: **New service** that coordinates ReAct loop execution, wrapping `core/domain/agent.py` with logging, error handling, and state persistence
- `profiles.py`: **New module** to load YAML configuration profiles (dev/staging/prod) specifying which adapters to use

**FR8: API Layer - FastAPI** - The `src/taskforce/api/` shall provide REST API:
- `server.py`: FastAPI application with CORS, middleware, logging configuration
- `routes/execution.py`: Endpoints for `/execute`, `/sessions`, `/sessions/{id}`, `/health`
- `deps.py`: FastAPI dependency injection for database connections, agent factory instances

**FR9: API Layer - CLI** - The `src/taskforce/api/cli/` shall provide command-line interface:
- **Adapt** structure from `agent_v2/cli/` (main.py, commands/, output_formatter.py, plugin_manager.py)
- **Reuse** Typer command groups: run, chat, tools, sessions, missions, providers, config, dev
- **Modify** to use `application/executor.py` service instead of direct agent instantiation

**FR10: Supporting Components** - The following shall be relocated with minimal modification:
- **Memory system**: `agent_v2/memory/` → `infrastructure/memory/`
- **Prompts**: `agent_v2/prompts/` → `core/prompts/` (system prompts are domain concepts)
- **Replanning**: `agent_v2/replanning.py` → `core/domain/replanning.py` (domain logic)
- **Conversation manager**: `agent_v2/conversation_manager.py` → `core/domain/conversation.py`

### Non-Functional Requirements

**NFR1: Architectural Boundary Enforcement** - Import rules must be enforced via linting:
- ✅ `core/domain/` may ONLY import from `core/interfaces/` (zero infrastructure imports)
- ✅ `infrastructure/` may import from `core/interfaces/` and `core/domain/` (implements protocols)
- ✅ `application/` may import from all layers (wiring layer)
- ✅ `api/` may import from `application/` and `core/interfaces/` (not direct infrastructure)
- ❌ Violations fail CI/CD pipeline

**NFR2: Maximum Code Reuse** - At least 75% of working logic from Agent V2 shall be reused through relocation to the appropriate layer:
- **core/domain/**: Extract and refactor (30% new wrapper code, 70% relocated logic)
- **infrastructure/tools/**: Copy with minimal changes (90% code reuse)
- **infrastructure/llm/**: Relocate with protocol wrapper (80% code reuse)
- **infrastructure/persistence/file_*.py**: Relocate with protocol implementation (85% code reuse)

**NFR3: Layer-Specific Testing** - Test structure mirrors source structure:
- `tests/unit/core/`: Pure unit tests with protocol mocks (no I/O)
- `tests/unit/infrastructure/`: Unit tests for adapters (may use test databases)
- `tests/integration/`: End-to-end tests via `application/executor.py`
- Achieve ≥90% coverage in `core/domain/`, ≥80% in `infrastructure/`

**NFR4: Developer Experience** - Setup and usage must be streamlined:
- `cd taskforce && uv sync && taskforce --help` completes in <5 minutes
- CLI commands mirror Agent V2 structure (`taskforce run mission` vs. `agent run mission`)
- Rich terminal output with progress bars and colored status preserved from Agent V2 CLI

**NFR5: Configuration Management** - The `profiles.py` module shall support:
- **Dev profile**: File-based persistence, OpenAI direct, verbose logging
- **Staging profile**: PostgreSQL persistence, Azure OpenAI, structured logging
- **Prod profile**: PostgreSQL with connection pooling, Azure OpenAI, minimal logging
- Profile selection via environment variable `TASKFORCE_PROFILE` or CLI flag `--profile`

**NFR6: Performance Parity** - ReAct loop execution shall maintain Agent V2 performance:
- File-based persistence: Identical performance to Agent V2
- Database persistence: <15% overhead compared to file-based (acceptable for production benefits)
- Tool execution latency: Unchanged (tools relocated as-is)

**NFR7: Documentation Requirements** - Each layer must be documented:
- `core/README.md`: Explanation of domain concepts and protocol contracts
- `infrastructure/README.md`: Guide for implementing new adapters
- `application/README.md`: Configuration and profile system documentation
- `api/README.md`: FastAPI endpoints and CLI commands reference

**NFR8: Deployment Readiness** - The FastAPI service shall support:
- Docker containerization with multi-stage build
- Health checks: `/health` endpoint for liveness/readiness probes
- Graceful shutdown with in-flight request completion
- Structured JSON logging for centralized aggregation
- Horizontal scaling with shared PostgreSQL backend

### Compatibility Requirements

**CR1: State Format Compatibility** - `infrastructure/persistence/file_state.py` (relocated from `statemanager.py`) shall produce identical JSON files to Agent V2, ensuring sessions are portable between frameworks.

**CR2: TodoList Schema Compatibility** - TodoList JSON schema (position, description, acceptance_criteria, dependencies, status, chosen_tool, execution_result) shall remain unchanged in `core/domain/plan.py`.

**CR3: Tool Interface Compatibility** - All tools in `infrastructure/tools/native/` and `infrastructure/tools/rag/` shall maintain their parameter schemas from Agent V2, ensuring mission portability.

**CR4: LLM Configuration Compatibility** - `infrastructure/llm/openai_service.py` shall load Agent V2's `llm_config.yaml` without modification.

**CR5: Environment Variable Alignment** - Taskforce shall use identical environment variable names as Agent V2 (`OPENAI_API_KEY`, `AZURE_OPENAI_API_KEY`, `GITHUB_TOKEN`).

**CR6: CLI Command Structure** - Taskforce CLI (`api/cli/`) shall maintain similar command structure to Agent V2 CLI for user transition ease.

---

## 3. Technical Constraints and Integration Requirements

### Existing Technology Stack

**Languages**: Python 3.11

**Frameworks**:
- **LiteLLM** (1.7.7.0) - Multi-provider LLM orchestration (OpenAI, Azure OpenAI, Anthropic)
- **Typer** (0.9.0+) - Modern CLI framework with Rich integration
- **FastAPI** (0.116.1+) - Async web framework for REST API
- **asyncio** - Built-in async/await patterns for I/O operations
- **structlog** (24.2.0) - Structured logging with JSON and console outputs
- **Pydantic** (2.0.0+) - Data validation and settings management

**Database**: 
- **PostgreSQL** (15+) - Production persistence backend
- **SQLAlchemy** (2.0+) - ORM and database abstraction
- **Alembic** - Database migration management
- **File-based JSON** - Development/local persistence (from Agent V2)

**Infrastructure**:
- **Windows-based development** - PowerShell 7+ for scripting
- **uv package manager** - NOT pip/venv (all installations via `uv sync`)
- **Docker** - Containerization for microservice deployment
- **PostgreSQL connection pooling** - Production-grade connection management

**External Dependencies**:
- **OpenAI API** - Direct LLM access (current in Agent V2)
- **Azure OpenAI API** - Enterprise LLM access via Azure
- **Azure AI Search SDK** (11.4.0+) - RAG semantic search and document retrieval
- **Git/GitHub APIs** - Tool integrations (GitTool, GitHubTool)
- **Web APIs** - HTTP requests via aiohttp (WebSearchTool, WebFetchTool)

### Integration Approach

**Database Integration Strategy**:
- **Development**: File-based persistence via `FileStateManager` (relocated from Agent V2 `statemanager.py`) - zero database dependency for local dev
- **Production**: PostgreSQL via `DbStateManager` implementing same `StateManagerProtocol`
- **Schema Design**: 
  - `sessions` table (session_id, user_id, mission, status, created_at, updated_at)
  - `states` table (session_id, state_json, version, timestamp) - JSONB column for flexibility
  - `todo_lists` table (todolist_id, session_id, plan_json, status, created_at)
  - `execution_history` table (session_id, step_id, thought, action, observation, timestamp)
  - `memories` table (memory_id, context, lesson, tool_name, confidence, created_at)
- **Connection Management**: SQLAlchemy async engine with connection pooling (min=5, max=20)
- **Migration Strategy**: Alembic migrations in `taskforce/alembic/versions/`
- **Adapter Selection**: Configuration-driven via `application/profiles.py` (dev profile uses file, prod uses DB)

**API Integration Strategy**:
- **REST API**: FastAPI endpoints in `api/routes/execution.py` exposing agent execution, session management, health checks
- **Stateless Design**: API handlers use `application/executor.py` service, which retrieves session state from persistence layer
- **Streaming Support**: WebSocket or Server-Sent Events for real-time progress updates during long-running missions
- **Authentication**: JWT-based authentication (future enhancement) - placeholder middleware in `api/middleware.py`
- **CORS**: Configurable CORS for frontend integration

**Frontend Integration Strategy**:
- **CLI as Primary Interface**: Typer-based CLI in `api/cli/` adapted from Agent V2 with Rich formatting
- **REST API as Secondary**: FastAPI service enables future web UI or programmatic integration
- **Shared Executor**: Both CLI and REST API use `application/executor.py` ensuring identical behavior
- **Output Formatting**: CLI uses Rich tables/progress bars; API returns JSON with same data structure

**Testing Integration Strategy**:
- **Unit Tests**: Pure tests for `core/domain/` using protocol mocks (no I/O dependencies)
- **Integration Tests**: Test infrastructure adapters with test database (PostgreSQL in Docker or SQLite in-memory)
- **End-to-End Tests**: Test via CLI commands or API endpoints using `application/executor.py`
- **Test Fixtures**: Shared fixtures in `tests/fixtures/` for sample missions, tool responses, LLM completions
- **Coverage Requirements**: ≥90% for core/domain/, ≥80% for infrastructure/, ≥70% for application/

### Code Organization and Standards

**File Structure Approach**:
- **Layer-based organization**: Four distinct layers (core, infrastructure, application, api) enforce Clean Architecture
- **Protocol-driven interfaces**: All layer boundaries defined by protocols in `core/interfaces/`
- **Single responsibility**: Each module has one clear purpose (e.g., `agent.py` only contains ReAct loop)
- **Test mirroring**: `tests/` directory structure mirrors `src/taskforce/` for easy navigation
- **Configuration separation**: All configs in `taskforce/configs/` (separate from code)

**Naming Conventions**:
- **Modules**: Snake_case (e.g., `state_manager.py`, `openai_service.py`)
- **Classes**: PascalCase (e.g., `StateManagerProtocol`, `DbStateManager`, `AgentFactory`)
- **Functions/methods**: Snake_case (e.g., `save_state()`, `execute_react_loop()`)
- **Constants**: UPPER_SNAKE_CASE (e.g., `MAX_RETRY_ATTEMPTS`, `DEFAULT_TIMEOUT`)
- **Private methods**: Leading underscore (e.g., `_initialize_provider()`, `_validate_config()`)
- **Protocol interfaces**: Suffix with `Protocol` (e.g., `StateManagerProtocol`, `LLMProviderProtocol`)

**Coding Standards**:
- **PEP8 compliance** - Enforced via Black formatter and Ruff linter
- **Type annotations**: All function signatures must include type hints (enforced by mypy)
- **Docstrings**: Required for all modules, classes, and public methods (Google-style docstrings)
- **Function length**: ≤30 lines per function (extract helper functions if needed)
- **Defensive programming**: Validate inputs, handle errors explicitly, avoid silent failures
- **Functional style preferred**: Use pure functions where possible; classes only for stateful components
- **No circular imports**: Enforced via import linting (pylint)
- **Layer import rules**: Core cannot import infrastructure; infrastructure implements core interfaces

**Documentation Standards**:
- **Module docstrings**: Every `.py` file starts with module-level docstring explaining purpose
- **Class docstrings**: Explain class responsibility and usage patterns
- **Method docstrings**: Include Args, Returns, Raises sections for public methods
- **Inline comments**: Explain "why" not "what" (code should be self-documenting for "what")
- **Architecture Decision Records (ADRs)**: Document key architectural choices in `taskforce/docs/adr/`
- **README files**: Each layer (`core/`, `infrastructure/`, `application/`, `api/`) has README explaining its role
- **API documentation**: FastAPI auto-generates OpenAPI spec; add descriptions to endpoints

### Deployment and Operations

**Build Process Integration**:
- **Package manager**: `uv` (NOT pip) - all dependencies managed via `pyproject.toml`
- **Build command**: `uv sync` to install dependencies and create virtual environment
- **Entry points**: Defined in `pyproject.toml`:
  - CLI: `taskforce` command (maps to `taskforce.api.cli.main:app`)
  - API: `taskforce-server` command (maps to `taskforce.api.server:app`)
- **Docker build**: Multi-stage Dockerfile:
  ```dockerfile
  # Stage 1: Builder
  FROM python:3.11-slim as builder
  RUN pip install uv
  COPY pyproject.toml uv.lock ./
  RUN uv sync --frozen
  
  # Stage 2: Runtime
  FROM python:3.11-slim
  COPY --from=builder /app/.venv /app/.venv
  COPY src/ /app/src/
  CMD ["taskforce-server"]
  ```

**Deployment Strategy**:
- **Local Development**: File-based persistence, no database required, run via `taskforce` CLI
- **Staging**: Docker container + PostgreSQL, deployed to staging environment with Azure OpenAI
- **Production**: Kubernetes deployment with:
  - Horizontal Pod Autoscaler (2-10 replicas based on CPU)
  - Shared PostgreSQL database with connection pooling
  - Azure OpenAI integration via private endpoint
  - Persistent volumes for temporary file storage (if needed)
- **Configuration**: Environment-specific via `TASKFORCE_PROFILE` env var (dev/staging/prod)
- **Secrets management**: Environment variables for API keys (not in config files)
- **Database migrations**: Run `alembic upgrade head` before deployment (Kubernetes init container)

**Monitoring and Logging**:
- **Structured logging**: `structlog` with JSON output for production, console output for dev
- **Log levels**: Configurable per profile (dev=DEBUG, staging=INFO, prod=WARNING)
- **Contextual logging**: Every log includes `session_id`, `mission_name`, `user_id` for traceability
- **Key metrics logged**:
  - `agent.mission.started` - Mission execution start
  - `agent.tool.executed` - Tool execution with duration and success/failure
  - `agent.llm.completion` - LLM call with tokens, latency, model
  - `agent.mission.completed` - Mission completion with total duration
- **Observability endpoints**:
  - `/health` - Liveness probe (returns 200 if service running)
  - `/health/ready` - Readiness probe (checks database connectivity)
  - `/metrics` - Prometheus metrics (future enhancement)

**Configuration Management**:
- **Profile-based config**: YAML files in `taskforce/configs/`:
  - `dev.yaml` - Local development (file persistence, OpenAI direct)
  - `staging.yaml` - Staging environment (DB persistence, Azure OpenAI)
  - `prod.yaml` - Production (DB with pooling, Azure OpenAI, minimal logging)
- **Environment variable overrides**: Any config value can be overridden via env vars (e.g., `TASKFORCE_DB_URL`)
- **Secrets externalized**: API keys, DB passwords via environment variables only
- **Validation**: Pydantic models validate configuration on startup with clear error messages
- **Hot-reload**: Configuration changes require restart (no hot-reload to ensure consistency)

### Risk Assessment and Mitigation

**Technical Risks**:

1. **Protocol Interface Overhead** - Adding protocol layers between domain and infrastructure may introduce complexity
   - *Mitigation*: Keep protocols simple with minimal methods; use Python's duck typing flexibility; provide clear documentation and examples

2. **Database Migration Complexity** - Moving from file-based to database persistence introduces schema management overhead
   - *Mitigation*: Use Alembic for version-controlled migrations; maintain backward-compatible schema changes; test migrations thoroughly in staging

3. **Code Relocation Errors** - Moving code between layers risks breaking imports and dependencies
   - *Mitigation*: Use systematic approach (one module at a time); maintain comprehensive test suite; verify tests pass after each relocation

4. **Performance Degradation** - Database persistence and protocol abstraction may slow down ReAct loop
   - *Mitigation*: Benchmark critical paths; use connection pooling; implement caching where appropriate; accept <15% overhead as acceptable trade-off

**Integration Risks**:

1. **Layer Boundary Violations** - Developers may accidentally import infrastructure from core
   - *Mitigation*: Enforce with import linting in CI/CD; provide clear documentation; code review checklist; use dependency injection container

2. **Protocol-Implementation Mismatch** - Implementations may drift from protocol definitions
   - *Mitigation*: Use runtime protocol checking (if needed); comprehensive integration tests; type checking with mypy

3. **Dual Persistence Maintenance** - Maintaining both file-based and DB persistence doubles adapter surface area
   - *Mitigation*: Shared test suite for both adapters; automated tests verify identical behavior; document explicitly which features are supported by each

4. **Agent V2 Compatibility** - Taskforce may drift from Agent V2 behavior during development
   - *Mitigation*: Shared test cases between projects; explicit compatibility requirements; document intentional differences

**Deployment Risks**:

1. **Database Connection Exhaustion** - Multiple agent instances may exhaust PostgreSQL connections
   - *Mitigation*: Connection pooling with appropriate limits; monitor connection usage; implement connection timeout and recycling

2. **Long-Running Mission Interruptions** - Container restarts during missions lose in-progress state
   - *Mitigation*: Persist state after every tool execution; support mission resume from last checkpoint; implement graceful shutdown

3. **Configuration Drift** - Different environments may have incompatible configurations
   - *Mitigation*: Version-controlled config files; automated config validation; staging mirrors production config

4. **Stateless API Limitations** - Some Agent V2 features may assume local filesystem access
   - *Mitigation*: Identify filesystem dependencies early; implement temporary file storage (S3/Azure Blob); document limitations

**Mitigation Strategies**:

- **Incremental Migration**: Build Taskforce layer-by-layer, testing each layer independently before integrating
- **Parallel Testing**: Run same missions in Agent V2 and Taskforce, compare outputs for behavioral parity
- **Rollback Plan**: Maintain Agent V2 as fallback; Taskforce adoption is opt-in initially
- **Comprehensive Documentation**: Document every architectural decision, layer responsibility, and extension point
- **Automated Quality Gates**: CI/CD pipeline enforces import rules, test coverage, type checking before merge

---

## 4. Epic and Story Structure

### Epic Approach

**Epic Structure Decision**: **Single Comprehensive Epic with Sequential Story Implementation**

**Rationale**:

This enhancement involves building a new production framework (Taskforce) by reorganizing and adapting proven code from Agent V2 into a Clean Architecture structure. All work items are tightly coupled and must be implemented in a specific order due to architectural dependencies:

1. **Foundation First**: Core interfaces and domain logic must exist before infrastructure adapters
2. **Bottom-Up Assembly**: Infrastructure adapters depend on protocols; application layer depends on both core and infrastructure
3. **Entrypoints Last**: API and CLI entrypoints require the full stack beneath them

A single epic **"Build Taskforce Production Framework with Clean Architecture"** ensures:
- **Clear dependency chain**: Each story builds on previous work (protocols → domain → infrastructure → application → API)
- **Unified testing strategy**: Tests evolve with the architecture (protocol mocks → adapter tests → integration tests)
- **Architectural coherence**: All stories work toward the same four-layer structure
- **Risk management**: Early stories establish architectural boundaries before moving code
- **Simpler tracking**: Single epic shows progress toward "production-ready framework" goal

**Story Sequencing Strategy**:

1. **Stories 1-2**: Establish project structure and protocol contracts (foundation)
2. **Stories 3-4**: Implement core domain logic (ReAct loop, TodoList planning)
3. **Stories 5-8**: Build infrastructure adapters (persistence, LLM, tools)
4. **Stories 9-10**: Create application layer (factory, executor, profiles)
5. **Stories 11-12**: Implement API entrypoints (FastAPI, CLI)
6. **Stories 13-14**: Add database support, migrations, deployment infrastructure

This sequence minimizes rework and ensures each story delivers testable, verifiable progress.

---

## 5. Epic 1: Build Taskforce Production Framework with Clean Architecture

**Epic Goal**: Create a production-ready agent framework (Taskforce) implementing Clean Architecture principles by reorganizing and adapting proven code from Agent V2 into a four-layer structure (core, infrastructure, application, API), enabling enterprise deployment with swappable persistence backends, testable domain logic, and microservice scalability.

**Integration Requirements**:
- Establish protocol-based interfaces in `core/interfaces/` defining contracts for state management, LLM providers, tools, and TodoList persistence
- Extract domain logic (ReAct loop, TodoList planning) from Agent V2 into `core/domain/` with zero infrastructure dependencies
- Relocate and adapt infrastructure components (StateManager, LLMService, Tools) into `infrastructure/` implementing core protocols
- Build dependency injection layer in `application/` wiring core and infrastructure based on configuration profiles
- Create dual entrypoints (FastAPI REST API, Typer CLI) in `api/` using shared executor service
- Maintain behavioral parity with Agent V2 while establishing architectural boundaries for future extensibility

---

### Story 1.1: Establish Taskforce Project Structure and Dependencies

As a **developer**,
I want **the Taskforce project structure created with proper Python packaging**,
so that **I have a clean foundation for implementing Clean Architecture layers**.

**Acceptance Criteria:**

1. Create `taskforce/` directory at repository root (sibling to `capstone/`)
2. Create `taskforce/pyproject.toml` with project metadata, dependencies (LiteLLM, Typer, FastAPI, structlog, SQLAlchemy, Alembic, pytest), and CLI entry points
3. Create `taskforce/src/taskforce/` with subdirectories: `core/`, `infrastructure/`, `application/`, `api/`
4. Create subdirectory structure:
   - `core/domain/`, `core/interfaces/`, `core/prompts/`
   - `infrastructure/persistence/`, `infrastructure/llm/`, `infrastructure/tools/`, `infrastructure/memory/`
   - `application/` (factory, executor, profiles modules)
   - `api/routes/`, `api/cli/`
5. Create `taskforce/tests/` with `unit/`, `integration/`, `fixtures/` subdirectories
6. Create placeholder `__init__.py` files in all packages
7. Verify `uv sync` successfully installs all dependencies
8. Create `taskforce/README.md` with project overview and setup instructions

**Integration Verification:**

- **IV1: Existing Functionality Verification** - Agent V2 in `capstone/agent_v2` continues to function independently (no import conflicts)
- **IV2: Integration Point Verification** - `uv sync` in `taskforce/` completes successfully with all dependencies resolved
- **IV3: Performance Impact Verification** - N/A (project setup only)

---

### Story 1.2: Define Core Protocol Interfaces

As a **developer**,
I want **protocol interfaces defined for all external dependencies**,
so that **core domain logic can be implemented without infrastructure coupling**.

**Acceptance Criteria:**

1. Create `taskforce/src/taskforce/core/interfaces/state.py` with `StateManagerProtocol`:
   - Methods: `save_state(session_id, state_data)`, `load_state(session_id)`, `delete_state(session_id)`, `list_sessions()`
   - All methods return type-annotated values matching Agent V2 `statemanager.py` signatures
2. Create `taskforce/src/taskforce/core/interfaces/llm.py` with `LLMProviderProtocol`:
   - Methods: `complete(model, messages, **params)`, `generate(model, prompt, **params)`
   - Return types match Agent V2 `services/llm_service.py` public API
3. Create `taskforce/src/taskforce/core/interfaces/tools.py` with `ToolProtocol`:
   - Properties: `name`, `description`, `parameters_schema`
   - Methods: `execute(**params)`, `validate_parameters(params)`
   - Based on Agent V2 `tool.py` abstract base class
4. Create `taskforce/src/taskforce/core/interfaces/todolist.py` with `TodoListManagerProtocol`:
   - Methods: `create_plan(mission)`, `get_plan(todolist_id)`, `update_task_status(task_id, status)`, `save_plan(plan)`
   - Return types use TodoList/TodoItem dataclasses (to be defined in next story)
5. Add comprehensive docstrings to all protocols explaining contract expectations
6. All protocols use Python 3.11 Protocol class (from `typing`)
7. Type hints validated with mypy (zero type errors)

**Integration Verification:**

- **IV1: Existing Functionality Verification** - Agent V2 continues to function (no imports from taskforce yet)
- **IV2: Integration Point Verification** - Protocols can be imported and used in type hints without runtime errors
- **IV3: Performance Impact Verification** - N/A (interface definitions only)

---

### Story 1.3: Implement Core Domain - Agent ReAct Loop

As a **developer**,
I want **the ReAct execution loop extracted from Agent V2 into core domain**,
so that **business logic is testable without infrastructure dependencies**.

**Acceptance Criteria:**

1. Create `taskforce/src/taskforce/core/domain/agent.py` with `Agent` class
2. Extract ReAct loop logic from `capstone/agent_v2/agent.py:Agent.execute()`:
   - Thought generation (LLM call for reasoning)
   - Action decision (tool selection or ask_user or complete)
   - Observation recording (tool execution result)
3. Refactor to accept dependencies via constructor injection:
   - `state_manager: StateManagerProtocol`
   - `llm_provider: LLMProviderProtocol`
   - `tools: List[ToolProtocol]`
   - `todolist_manager: TodoListManagerProtocol`
4. Create `execute(mission: str, session_id: str) -> ExecutionResult` method implementing ReAct loop
5. Preserve Agent V2 execution semantics (same loop termination conditions, same error handling)
6. Create dataclasses for domain events: `Thought`, `Action`, `Observation` in `core/domain/events.py`
7. Unit tests using protocol mocks verify ReAct logic without any I/O

**Integration Verification:**

- **IV1: Existing Functionality Verification** - Agent V2 remains operational (not yet using taskforce agent)
- **IV2: Integration Point Verification** - Unit tests verify identical ReAct behavior using mocked protocols compared to Agent V2 execution traces
- **IV3: Performance Impact Verification** - Unit tests complete in <1 second (pure in-memory logic)

---

### Story 1.4: Implement Core Domain - TodoList Planning

As a **developer**,
I want **TodoList planning logic extracted into core domain**,
so that **plan generation and task management are testable without persistence dependencies**.

**Acceptance Criteria:**

1. Create `taskforce/src/taskforce/core/domain/plan.py` with domain classes and logic
2. Extract from `capstone/agent_v2/planning/todolist.py`:
   - `TodoItem` dataclass (position, description, acceptance_criteria, dependencies, status, chosen_tool, execution_result)
   - `TodoList` dataclass (mission, items, created_at, updated_at)
   - `TaskStatus` enum (PENDING, IN_PROGRESS, COMPLETED, FAILED, SKIPPED)
   - `PlanGenerator` class (LLM-based plan generation logic)
3. Refactor `PlanGenerator` to accept `llm_provider: LLMProviderProtocol` via constructor
4. Preserve all planning algorithms from Agent V2 (dependency validation, LLM prompts for plan generation)
5. Remove all persistence logic (file I/O, JSON serialization) - delegate to infrastructure layer
6. Create `validate_dependencies(plan)` method ensuring no circular dependencies
7. Unit tests with mocked LLM verify plan generation logic without actual LLM calls

**Integration Verification:**

- **IV1: Existing Functionality Verification** - Agent V2 planning continues to work independently
- **IV2: Integration Point Verification** - Generated plans match Agent V2 plan structure (same JSON schema when serialized)
- **IV3: Performance Impact Verification** - Plan validation completes in <100ms for plans with 20 tasks

---

### Story 1.5: Implement Infrastructure - File-Based State Manager

As a **developer**,
I want **file-based state persistence relocated from Agent V2**,
so that **development environments don't require database setup**.

**Acceptance Criteria:**

1. Create `taskforce/src/taskforce/infrastructure/persistence/file_state.py`
2. Relocate code from `capstone/agent_v2/statemanager.py` with minimal changes
3. Implement `StateManagerProtocol` interface
4. Preserve all Agent V2 functionality:
   - Async file I/O (aiofiles)
   - State versioning
   - Atomic writes
   - Session directory structure (`{work_dir}/states/{session_id}.json`)
5. JSON serialization produces byte-identical output to Agent V2
6. Unit tests verify all protocol methods work correctly
7. Integration tests using actual filesystem verify state persistence and retrieval

**Integration Verification:**

- **IV1: Existing Functionality Verification** - Agent V2 `statemanager.py` remains operational (both implementations coexist)
- **IV2: Integration Point Verification** - Taskforce FileStateManager can read session files created by Agent V2
- **IV3: Performance Impact Verification** - State save/load operations match Agent V2 latency (±5%)

---

### Story 1.6: Implement Infrastructure - LLM Service Adapter

As a **developer**,
I want **LLM service relocated from Agent V2 with protocol implementation**,
so that **core domain can make LLM calls via abstraction**.

**Acceptance Criteria:**

1. Create `taskforce/src/taskforce/infrastructure/llm/openai_service.py`
2. Relocate code from `capstone/agent_v2/services/llm_service.py` with minimal changes
3. Implement `LLMProviderProtocol` interface
4. Preserve all Agent V2 functionality:
   - Model aliases (main, fast, powerful, legacy)
   - Parameter mapping (GPT-4 vs GPT-5 params)
   - Retry logic with exponential backoff
   - Token usage logging
   - Azure OpenAI support
5. Configuration via `llm_config.yaml` (same format as Agent V2)
6. Unit tests with mocked LiteLLM verify parameter mapping
7. Integration tests with actual LLM API verify completion requests

**Integration Verification:**

- **IV1: Existing Functionality Verification** - Agent V2 LLMService continues to function independently
- **IV2: Integration Point Verification** - Taskforce LLMService produces identical completion results for same prompts as Agent V2
- **IV3: Performance Impact Verification** - LLM call latency matches Agent V2 (protocol abstraction overhead <1%)

---

### Story 1.7: Implement Infrastructure - Native Tools

As a **developer**,
I want **all native tools copied from Agent V2 into infrastructure layer**,
so that **core domain can execute tools via protocol interface**.

**Acceptance Criteria:**

1. Create `taskforce/src/taskforce/infrastructure/tools/native/` directory
2. Copy tools from `capstone/agent_v2/tools/` with path updates:
   - `code_tool.py` → `python_tool.py` (PythonTool)
   - `file_tool.py` → `file_tools.py` (FileReadTool, FileWriteTool)
   - `git_tool.py` → `git_tools.py` (GitTool, GitHubTool)
   - `shell_tool.py` → `shell_tool.py` (PowerShellTool)
   - `web_tool.py` → `web_tools.py` (WebSearchTool, WebFetchTool)
   - `llm_tool.py` → `llm_tool.py` (LLMTool)
   - `ask_user_tool.py` → `ask_user_tool.py` (AskUserTool)
3. Each tool implements `ToolProtocol` interface
4. Preserve all tool logic: parameter schemas, retry mechanisms, isolated Python execution, timeout handling
5. Update imports to use taskforce paths
6. Unit tests for each tool verify parameter validation
7. Integration tests verify tool execution produces same results as Agent V2 tools

**Integration Verification:**

- **IV1: Existing Functionality Verification** - Agent V2 tools remain operational in `capstone/agent_v2/tools/`
- **IV2: Integration Point Verification** - Taskforce tools produce identical outputs for identical inputs compared to Agent V2 tools
- **IV3: Performance Impact Verification** - Tool execution time matches Agent V2 (±5%)

---

### Story 1.8: Implement Infrastructure - RAG Tools

As a **developer**,
I want **RAG tools copied from Agent V2 into infrastructure layer**,
so that **RAG agent capabilities are available in Taskforce**.

**Acceptance Criteria:**

1. Create `taskforce/src/taskforce/infrastructure/tools/rag/` directory
2. Copy RAG tools from `capstone/agent_v2/tools/`:
   - `rag_semantic_search_tool.py` → `semantic_search.py`
   - `rag_list_documents_tool.py` → `list_documents.py`
   - `rag_get_document_tool.py` → `get_document.py`
   - `azure_search_base.py` → `azure_search_base.py` (shared Azure AI Search client)
3. Each RAG tool implements `ToolProtocol` interface
4. Preserve all Azure AI Search integration logic (semantic search, document retrieval, security filtering)
5. Update imports to use taskforce paths
6. Unit tests with mocked Azure Search client verify query construction
7. Integration tests with test Azure Search index verify search functionality

**Integration Verification:**

- **IV1: Existing Functionality Verification** - Agent V2 RAG tools continue to function in `capstone/agent_v2/tools/`
- **IV2: Integration Point Verification** - Taskforce RAG tools produce identical search results for identical queries compared to Agent V2 RAG tools
- **IV3: Performance Impact Verification** - Search latency matches Agent V2 (±5%)

---

### Story 1.9: Implement Application Layer - Agent Factory

As a **developer**,
I want **dependency injection factory adapting Agent V2 factory logic**,
so that **agents can be constructed with different infrastructure adapters based on configuration**.

**Acceptance Criteria:**

1. Create `taskforce/src/taskforce/application/factory.py` with `AgentFactory` class
2. Adapt logic from `capstone/agent_v2/agent_factory.py`
3. Factory methods:
   - `create_agent(profile: str) -> Agent` - Creates generic agent
   - `create_rag_agent(profile: str) -> Agent` - Creates RAG agent
4. Configuration-driven adapter selection:
   - Read profile YAML (dev/staging/prod)
   - Instantiate appropriate persistence adapter (FileStateManager or DbStateManager)
   - Instantiate LLM provider (OpenAI or Azure OpenAI)
   - Register tools based on agent type
5. Preserve Agent V2 agent construction logic (system prompt selection, tool registration)
6. Support both Agent V2 factory methods for backward compatibility
7. Unit tests verify correct adapter wiring for each profile

**Integration Verification:**

- **IV1: Existing Functionality Verification** - Agent V2 factory continues to work independently
- **IV2: Integration Point Verification** - Agents created by Taskforce factory behave identically to Agent V2 agents (verified via integration tests)
- **IV3: Performance Impact Verification** - Agent construction time <200ms regardless of profile

---

### Story 1.10: Implement Application Layer - Executor Service

As a **developer**,
I want **a service layer orchestrating agent execution**,
so that **both CLI and API can use the same execution logic**.

**Acceptance Criteria:**

1. Create `taskforce/src/taskforce/application/executor.py` with `AgentExecutor` class
2. Implement `execute_mission(mission: str, profile: str, session_id: Optional[str]) -> ExecutionResult` method
3. Orchestration logic:
   - Use AgentFactory to create agent based on profile
   - Load or create session state
   - Execute agent ReAct loop
   - Persist state after each step
   - Handle errors and logging
4. Provide streaming progress updates via callback or async generator
5. Comprehensive structured logging for observability
6. Error handling with clear error messages
7. Unit tests with mocked factory and agent verify orchestration logic

**Integration Verification:**

- **IV1: Existing Functionality Verification** - Agent V2 execution continues independently
- **IV2: Integration Point Verification** - Executor produces same mission results as Agent V2 for identical missions
- **IV3: Performance Impact Verification** - Execution overhead from executor layer <50ms per mission

---

### Story 1.11: Implement API Layer - FastAPI REST Service

As a **developer**,
I want **a FastAPI REST API exposing agent execution**,
so that **Taskforce can be deployed as a microservice**.

**Acceptance Criteria:**

1. Create `taskforce/src/taskforce/api/server.py` with FastAPI app
2. Create `taskforce/src/taskforce/api/routes/execution.py` with endpoints:
   - `POST /execute` - Execute agent mission (returns session_id, streams progress)
   - `GET /sessions` - List all sessions
   - `GET /sessions/{session_id}` - Get session details and state
   - `POST /sessions` - Create new session
   - `GET /health` - Health check (liveness probe)
   - `GET /health/ready` - Readiness check (verifies DB connectivity)
3. Endpoints use `AgentExecutor` service from application layer
4. Support for Server-Sent Events or WebSocket for streaming progress
5. Proper HTTP status codes and error responses
6. CORS middleware configuration
7. OpenAPI documentation auto-generated by FastAPI
8. Integration tests via TestClient verify all endpoints

**Integration Verification:**

- **IV1: Existing Functionality Verification** - Agent V2 CLI continues to function
- **IV2: Integration Point Verification** - API-executed missions produce same results as CLI-executed missions
- **IV3: Performance Impact Verification** - API overhead <100ms per request (excluding actual mission execution time)

---

### Story 1.12: Implement API Layer - CLI Interface

As a **developer**,
I want **a Typer CLI adapted from Agent V2**,
so that **developers can use Taskforce via command line**.

**Acceptance Criteria:**

1. Create `taskforce/src/taskforce/api/cli/` directory
2. Adapt structure from `capstone/agent_v2/cli/`:
   - `main.py` - CLI entry point with Typer app
   - `commands/run.py` - Execute missions
   - `commands/chat.py` - Interactive chat mode
   - `commands/tools.py` - List/inspect tools
   - `commands/sessions.py` - Session management
   - `commands/missions.py` - Mission management
   - `commands/config.py` - Configuration commands
3. All commands use `AgentExecutor` service from application layer
4. Preserve Rich terminal output (colored status, progress bars, tables)
5. CLI entry point defined in `pyproject.toml`: `taskforce` command
6. Support for `--profile` flag to select configuration profile
7. Integration tests via CliRunner verify all commands

**Integration Verification:**

- **IV1: Existing Functionality Verification** - Agent V2 CLI (`agent` command) continues to work
- **IV2: Integration Point Verification** - Taskforce CLI (`taskforce` command) produces same outputs as Agent V2 CLI for comparable commands
- **IV3: Performance Impact Verification** - CLI command response time matches Agent V2 (±10%)

---

### Story 1.13: Implement Database Persistence and Migrations

As a **developer**,
I want **PostgreSQL-backed state persistence with Alembic migrations**,
so that **Taskforce can be deployed in production with shared database**.

**Acceptance Criteria:**

1. Create `taskforce/src/taskforce/infrastructure/persistence/db_state.py` with `DbStateManager` implementing `StateManagerProtocol`
2. Create `taskforce/src/taskforce/infrastructure/persistence/db_todolist.py` with `DbTodoListManager` implementing `TodoListManagerProtocol`
3. SQLAlchemy models in `taskforce/src/taskforce/infrastructure/persistence/models.py`:
   - `Session` table (session_id PK, user_id, mission, status, timestamps)
   - `State` table (session_id FK, state_json JSONB, version, timestamp)
   - `TodoList` table (todolist_id PK, session_id FK, plan_json JSONB, status, timestamps)
   - `ExecutionHistory` table (session_id FK, step_id, thought, action, observation, timestamp)
   - `Memory` table (memory_id PK, context, lesson, tool_name, confidence, timestamp)
4. Alembic migration setup in `taskforce/alembic/`:
   - Initial migration creating all tables
   - Indexes on session_id, user_id, timestamp columns
5. Connection pooling configuration (min=5, max=20 connections)
6. Database URL configuration via environment variable or profile YAML
7. Integration tests with test PostgreSQL database verify CRUD operations

**Integration Verification:**

- **IV1: Existing Functionality Verification** - File-based persistence continues to work (dev profile)
- **IV2: Integration Point Verification** - Database persistence produces same behavior as file persistence (verified via shared test suite)
- **IV3: Performance Impact Verification** - Database operations complete in <50ms for state save/load (acceptable overhead)

---

### Story 1.14: Add Deployment Infrastructure and Documentation

As a **developer**,
I want **Docker containerization and comprehensive documentation**,
so that **Taskforce can be deployed to production environments**.

**Acceptance Criteria:**

1. Create `taskforce/Dockerfile` with multi-stage build (builder + runtime)
2. Create `taskforce/docker-compose.yml` for local development (taskforce service + postgres)
3. Create `taskforce/.dockerignore` excluding unnecessary files
4. Create configuration profiles:
   - `configs/dev.yaml` - File persistence, OpenAI, debug logging
   - `configs/staging.yaml` - PostgreSQL, Azure OpenAI, info logging
   - `configs/prod.yaml` - PostgreSQL with pooling, Azure OpenAI, warning logging
5. Update `taskforce/README.md` with:
   - Architecture overview with layer diagram
   - Setup instructions (local dev, Docker, production)
   - Configuration guide (profiles, environment variables)
   - Usage examples (CLI commands, API calls)
6. Create `taskforce/docs/architecture.md` with Clean Architecture explanation
7. Create `taskforce/docs/deployment.md` with Kubernetes deployment guide
8. Verify Docker build succeeds and container runs successfully

**Integration Verification:**

- **IV1: Existing Functionality Verification** - Agent V2 deployment remains independent
- **IV2: Integration Point Verification** - Dockerized Taskforce executes missions identically to local Taskforce
- **IV3: Performance Impact Verification** - Container startup time <10 seconds, ready to accept requests

---

## Summary

This PRD defines a comprehensive plan to build the **Taskforce production framework** by reorganizing and adapting proven code from Agent V2 into a Clean Architecture structure. The single epic with **14 sequenced stories** ensures:

- **Architectural Excellence**: Four-layer Clean Architecture (core, infrastructure, application, API) with protocol-based boundaries
- **Maximum Code Reuse**: ≥75% of Agent V2 logic relocated rather than rewritten, reducing risk and accelerating delivery
- **Zero Risk to Agent V2**: All work in new `taskforce/` directory; Agent V2 remains operational as reference and fallback
- **Production Readiness**: Database persistence, FastAPI microservice, Docker containerization, comprehensive logging
- **Developer Experience**: Modern CLI with Rich output, clear documentation, simple setup (`uv sync`)
- **Testability**: Protocol-based mocking enables pure unit tests for core domain logic
- **Extensibility**: Clear extension points for new tools, LLM providers, and persistence adapters

The framework achieves the original goals:
- ✅ **G1**: Strict architectural boundaries (core cannot import infrastructure)
- ✅ **G2**: Swappable persistence (file for dev, PostgreSQL for prod)
- ✅ **G3**: Microservice deployment via FastAPI with observability
- ✅ **G4**: 100% backward compatibility for CLI users (similar command structure)
- ✅ **G5**: Testability via protocol mocks and isolated domain logic
- ✅ **G6**: Enterprise-ready with clear extension points and documentation

**Next Steps**: Begin implementation with Story 1.1 (project structure), establishing the foundation for all subsequent work.

