# 2. Requirements

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
