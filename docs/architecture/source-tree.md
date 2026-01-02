# Source Tree Structure

**Version:** 1.0  
**Last Updated:** 2025-11-22  
**Purpose:** Developer reference for Taskforce project directory structure and file organization

---

## Overview

Taskforce follows **Clean Architecture** principles with a four-layer structure organized under `src/taskforce/`. The project uses Python 3.11+ with `uv` package management and is designed for Docker Compose deployment.

---

## Root Directory Structure

```
taskforce/
├── src/taskforce/          # Main application source code (Clean Architecture layers)
├── tests/                  # Test suite (unit, integration, fixtures)
├── docs/                   # Architecture, PRD, stories, QA gates
├── pyproject.toml          # Project metadata, dependencies, tool configuration
├── uv.lock                 # Locked dependency versions (managed by uv)
├── README.md               # Project overview and quick start
├── .env.example            # Environment variable template
├── docker-compose.yml      # Multi-container orchestration (API + PostgreSQL)
├── Dockerfile              # Multi-stage container build
├── alembic.ini             # Database migration configuration
└── htmlcov/                # Test coverage reports (generated)
```

---

## Source Code Structure (`src/taskforce/`)

The source tree follows Clean Architecture with **strict dependency direction** (inward only):

```
src/taskforce/
├── __init__.py
│
├── core/                           # Core Layer (Domain Logic - Zero Dependencies)
│   ├── __init__.py
│   ├── domain/                     # Business entities and logic
│   │   ├── __init__.py
│   │   ├── agent.py                # Agent: ReAct loop orchestration
│   │   ├── plan.py                 # PlanGenerator: TodoList creation/management
│   │   ├── events.py               # Domain Events: Thought, Action, Observation
│   │   └── models.py               # Core data models: TodoItem, ExecutionResult
│   │
│   ├── interfaces/                 # Protocol definitions (PEP 544)
│   │   ├── __init__.py
│   │   ├── state.py                # StateManagerProtocol
│   │   ├── llm.py                  # LLMProviderProtocol
│   │   ├── tools.py                # ToolProtocol
│   │   └── memory.py               # MemoryProtocol (optional)
│   │
│   └── prompts/                    # LLM prompt templates
│       ├── __init__.py
│       ├── react_system.py         # ReAct system prompt
│       ├── plan_generation.py      # TodoList planning prompt
│       └── rag_system.py           # RAG agent system prompt
│
├── infrastructure/                 # Infrastructure Layer (External I/O)
│   ├── __init__.py
│   │
│   ├── persistence/                # State persistence implementations
│   │   ├── __init__.py
│   │   ├── file_state.py           # FileStateManager: JSON file storage (dev)
│   │   ├── db_state.py             # DbStateManager: PostgreSQL storage (prod)
│   │   └── models.py               # SQLAlchemy ORM models
│   │
│   ├── llm/                        # LLM service implementations
│   │   ├── __init__.py
│   │   ├── openai_service.py       # OpenAIService: LiteLLM wrapper
│   │   └── llm_config.yaml         # Model aliases and parameter mappings
│   │
│   ├── tools/                      # Tool implementations
│   │   ├── __init__.py
│   │   ├── base.py                 # BaseTool: Common tool functionality
│   │   │
│   │   ├── native/                 # Core tools (relocated from Agent V2)
│   │   │   ├── __init__.py
│   │   │   ├── python_tool.py      # PythonTool: Isolated code execution
│   │   │   ├── file_tool.py        # FileReadTool, FileWriteTool
│   │   │   ├── git_tool.py         # GitTool: Git operations
│   │   │   ├── github_tool.py      # GitHubTool: GitHub API integration
│   │   │   ├── powershell_tool.py  # PowerShellTool: Shell command execution
│   │   │   ├── web_tool.py         # WebSearchTool, WebFetchTool
│   │   │   ├── llm_tool.py         # LLMTool: Nested LLM calls
│   │   │   └── ask_user_tool.py    # AskUserTool: User interaction
│   │   │
│   │   └── rag/                    # RAG-specific tools
│   │       ├── __init__.py
│   │       ├── semantic_search.py  # SemanticSearchTool: Azure AI Search
│   │       ├── list_documents.py   # ListDocumentsTool
│   │       └── get_document.py     # GetDocumentTool
│   │
│   └── memory/                     # Memory implementations (optional)
│       ├── __init__.py
│       ├── chroma_memory.py        # ChromaDB vector memory
│       └── simple_memory.py        # In-memory cache
│
├── application/                    # Application Layer (Use Cases)
│   ├── __init__.py
│   ├── factory.py                  # AgentFactory: Dependency injection
│   ├── executor.py                 # AgentExecutor: Execution orchestration
│   ├── profiles.py                 # ProfileLoader: YAML config management
│   └── config/                     # Configuration profiles
│       ├── dev.yaml                # Development profile (file-based state)
│       ├── staging.yaml            # Staging profile (database state)
│       └── prod.yaml               # Production profile (database state)
│
└── api/                            # API Layer (External Interfaces)
    ├── __init__.py
    │
    ├── cli/                        # Typer CLI interface
    │   ├── __init__.py
    │   ├── main.py                 # CLI entry point (Typer app)
    │   └── commands/               # Command implementations
    │       ├── __init__.py
    │       ├── run.py              # `taskforce run` commands
    │       ├── chat.py             # `taskforce chat` command
    │       ├── tools.py            # `taskforce tools` commands
    │       ├── sessions.py         # `taskforce sessions` commands
    │       └── config.py           # `taskforce config` commands
    │
    ├── routes/                     # FastAPI REST endpoints
    │   ├── __init__.py
    │   ├── execute.py              # POST /api/v1/execute
    │   ├── sessions.py             # Session management endpoints
    │   └── health.py               # Health check endpoints
    │
    ├── server.py                   # FastAPI application factory
    ├── middleware.py               # Request logging, CORS, etc.
    └── schemas.py                  # Pydantic request/response models
```

---

## Test Structure (`tests/`)

Tests mirror the source structure with additional fixtures and integration tests:

```
tests/
├── __init__.py
│
├── unit/                           # Unit tests (isolated components)
│   ├── __init__.py
│   ├── test_agent.py               # Agent ReAct loop tests
│   ├── test_plan.py                # PlanGenerator tests
│   ├── test_file_state.py          # FileStateManager tests
│   ├── test_db_state.py            # DbStateManager tests
│   ├── test_openai_service.py      # OpenAIService tests
│   ├── test_tools_python.py        # PythonTool tests
│   ├── test_tools_file.py          # File tool tests
│   ├── test_factory.py             # AgentFactory tests
│   └── test_package_structure.py   # Project structure validation
│
├── integration/                    # Integration tests (multi-component)
│   ├── __init__.py
│   ├── test_agent_execution.py     # End-to-end agent execution
│   ├── test_cli.py                 # CLI command tests
│   ├── test_api.py                 # FastAPI endpoint tests
│   └── test_database.py            # Database persistence tests
│
└── fixtures/                       # Shared test fixtures
    ├── __init__.py
    ├── mock_llm.py                 # Mock LLM provider
    ├── sample_missions.py          # Test mission descriptions
    └── test_data.py                # Sample TodoLists, states, etc.
```

---

## Documentation Structure (`docs/`)

```
docs/
├── architecutre/                   # Architecture documentation (sharded)
│   ├── index.md                    # Architecture document index
│   ├── document-metadata.md        # Version, author, changelog
│   ├── section-1-introduction.md   # Project overview
│   ├── section-2-high-level-architecture.md
│   ├── section-3-tech-stack.md     # Technology decisions
│   ├── section-4-data-models-revised-python.md
│   ├── section-5-components.md     # Component descriptions
│   ├── section-6-external-apis.md  # External integrations
│   ├── section-7-core-workflows.md # Execution flows
│   ├── section-8-security.md       # Security architecture
│   ├── section-9-performance-scalability.md
│   ├── section-10-deployment.md    # Docker Compose setup
│   ├── section-11-testing-strategy.md
│   ├── section-12-open-questions-future-considerations.md
│   ├── section-13-glossary.md
│   ├── coding-standards.md         # Python style guide
│   ├── source-tree.md              # This file
│   └── conclusion.md
│
├── prd/                            # Product Requirements (sharded)
│   ├── index.md
│   ├── 1-intro-project-analysis-and-context.md
│   ├── 2-requirements.md
│   ├── 3-technical-constraints-and-integration-requirements.md
│   ├── 4-epic-and-story-structure.md
│   ├── 5-epic-1-build-taskforce-production-framework-with-clean-architecture.md
│   └── summary.md
│
├── stories/                        # User stories (Epic 1)
│   ├── README.md
│   ├── story-1.1-project-structure.md
│   ├── story-1.2-protocol-interfaces.md
│   ├── story-1.3-core-agent-react.md
│   ├── story-1.4-core-todolist.md
│   ├── story-1.5-infrastructure-file-state.md
│   ├── story-1.6-infrastructure-llm-service.md
│   ├── story-1.7-infrastructure-native-tools.md
│   ├── story-1.8-infrastructure-rag-tools.md
│   ├── story-1.9-application-factory.md
│   ├── story-1.10-application-executor.md
│   ├── story-1.11-api-fastapi.md
│   ├── story-1.12-api-cli.md
│   ├── story-1.13-database-persistence.md
│   └── story-1.14-deployment-infrastructure.md
│
├── qa/                             # Quality gates and assessments
│   ├── gates/
│   │   └── 1.1-project-structure.yml
│   └── assessments/
│
├── architecutre.md                 # Consolidated architecture (legacy)
└── prd.md                          # Consolidated PRD (legacy)
```

---

## Configuration Files

```
taskforce/
├── pyproject.toml                  # Project metadata, dependencies, tool config
│   ├── [project]                   # Name, version, dependencies
│   ├── [project.scripts]           # CLI entry point: `taskforce`
│   ├── [tool.pytest.ini_options]  # Test configuration
│   ├── [tool.black]                # Code formatter settings
│   ├── [tool.ruff]                 # Linter settings
│   └── [tool.mypy]                 # Type checker settings
│
├── uv.lock                         # Locked dependency versions (DO NOT EDIT)
│
├── alembic.ini                     # Database migration configuration
│   └── script_location = alembic/  # Migration scripts directory
│
├── docker-compose.yml              # Multi-container orchestration
│   ├── services:
│   │   ├── postgres                # PostgreSQL 15-alpine
│   │   └── taskforce               # Taskforce API container
│   └── volumes:
│       └── postgres_data           # Database persistence
│
├── Dockerfile                      # Multi-stage container build
│   ├── Stage 1: Builder            # Install dependencies with uv
│   └── Stage 2: Runtime            # Minimal runtime image
│
└── .env.example                    # Environment variable template
    ├── OPENAI_API_KEY              # Required for LLM calls
    ├── DATABASE_URL                # PostgreSQL connection string
    ├── AZURE_SEARCH_ENDPOINT       # Optional (RAG features)
    └── LOG_LEVEL                   # Logging verbosity
```

---

## Database Migrations (`alembic/`)

```
alembic/
├── versions/                       # Migration scripts (auto-generated)
│   ├── 001_initial_schema.py       # Initial tables (sessions, states)
│   ├── 002_add_todolist_table.py   # TodoList persistence
│   └── ...                         # Future migrations
│
├── env.py                          # Alembic environment configuration
├── script.py.mako                  # Migration script template
└── README                          # Migration usage guide
```

---

## Generated/Runtime Directories

These directories are created at runtime and should be in `.gitignore`:

```
taskforce/
├── htmlcov/                        # Test coverage HTML reports (pytest-cov)
├── .pytest_cache/                  # Pytest cache
├── __pycache__/                    # Python bytecode cache
├── .mypy_cache/                    # Mypy type checker cache
├── .ruff_cache/                    # Ruff linter cache
├── agent_work/                     # Runtime work directory (file-based state)
│   ├── states/                     # Session state JSON files (dev profile)
│   ├── todolists/                  # TodoList JSON files (dev profile)
│   └── logs/                       # Application logs
└── .venv/                          # Virtual environment (created by uv)
```

---

## Key File Purposes

### Core Layer Files

| File | Purpose | Key Classes/Functions |
|------|---------|----------------------|
| `core/domain/agent.py` | ReAct loop orchestration | `Agent`, `execute()`, `_generate_thought()`, `_decide_action()` |
| `core/domain/plan.py` | TodoList planning logic | `PlanGenerator`, `generate_plan()`, `validate_dependencies()` |
| `core/domain/events.py` | Domain events | `Thought`, `Action`, `Observation` (dataclasses) |
| `core/domain/models.py` | Core data models | `TodoItem`, `TodoList`, `ExecutionResult`, `TaskStatus` |
| `core/interfaces/state.py` | State persistence protocol | `StateManagerProtocol` (abstract interface) |
| `core/interfaces/llm.py` | LLM provider protocol | `LLMProviderProtocol` (abstract interface) |
| `core/interfaces/tools.py` | Tool execution protocol | `ToolProtocol` (abstract interface) |

### Infrastructure Layer Files

| File | Purpose | Key Classes/Functions |
|------|---------|----------------------|
| `infrastructure/persistence/file_state.py` | File-based state storage | `FileStateManager` (implements `StateManagerProtocol`) |
| `infrastructure/persistence/db_state.py` | PostgreSQL state storage | `DbStateManager` (implements `StateManagerProtocol`) |
| `infrastructure/llm/openai_service.py` | LLM service wrapper | `OpenAIService` (implements `LLMProviderProtocol`) |
| `infrastructure/tools/native/python_tool.py` | Python code execution | `PythonTool` (implements `ToolProtocol`) |
| `infrastructure/tools/native/file_tool.py` | File operations | `FileReadTool`, `FileWriteTool` |
| `infrastructure/tools/rag/semantic_search.py` | Azure AI Search integration | `SemanticSearchTool` |

### Application Layer Files

| File | Purpose | Key Classes/Functions |
|------|---------|----------------------|
| `application/factory.py` | Dependency injection | `AgentFactory`, `create_agent()`, `create_rag_agent()` |
| `application/executor.py` | Execution orchestration | `AgentExecutor`, `execute_mission()`, `execute_mission_streaming()` |
| `application/profiles.py` | Configuration management | `ProfileLoader`, `load_profile()`, `validate_profile()` |

### API Layer Files

| File | Purpose | Key Classes/Functions |
|------|---------|----------------------|
| `api/cli/main.py` | CLI entry point | Typer app, command routing |
| `api/cli/commands/run.py` | Mission execution commands | `run_mission()`, `run_interactive()` |
| `api/server.py` | FastAPI application | `create_app()`, middleware setup |
| `api/routes/execute.py` | Execution endpoints | `POST /api/v1/execute`, `POST /api/v1/execute/stream` |
| `api/routes/sessions.py` | Session management | `GET /api/v1/sessions`, `GET /api/v1/sessions/{id}` |

---

## Dependency Flow (Clean Architecture)

```
┌─────────────────────────────────────────────────────────────┐
│                        API Layer                            │
│  (cli/main.py, routes/*.py, server.py)                     │
│  Depends on: Application Layer                              │
└─────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────┐
│                   Application Layer                         │
│  (factory.py, executor.py, profiles.py)                    │
│  Depends on: Core Layer (protocols + domain)                │
└─────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────┐
│                      Core Layer                             │
│  Domain: agent.py, plan.py, events.py, models.py           │
│  Interfaces: state.py, llm.py, tools.py                    │
│  Depends on: NOTHING (pure business logic)                  │
└─────────────────────────────────────────────────────────────┘
                            ↑
┌─────────────────────────────────────────────────────────────┐
│                 Infrastructure Layer                        │
│  (persistence/*, llm/*, tools/*)                           │
│  Implements: Core protocols                                 │
│  Depends on: External systems (DB, APIs, filesystem)        │
└─────────────────────────────────────────────────────────────┘
```

**Key Principle:** Dependencies point **inward only**. Core never depends on Infrastructure. Infrastructure implements Core protocols.

---

## Import Conventions

### Correct Import Patterns

```python
# API Layer imports Application Layer
from taskforce.application.factory import AgentFactory
from taskforce.application.executor import AgentExecutor

# Application Layer imports Core protocols and domain
from taskforce.core.interfaces.state import StateManagerProtocol
from taskforce.core.domain.agent import Agent

# Infrastructure implements Core protocols
from taskforce.core.interfaces.state import StateManagerProtocol
from taskforce.infrastructure.persistence.file_state import FileStateManager

# Core domain NEVER imports Infrastructure
# ❌ WRONG: from taskforce.infrastructure.persistence.file_state import FileStateManager
# ✅ RIGHT: from taskforce.core.interfaces.state import StateManagerProtocol
```

### Absolute vs Relative Imports

- **Prefer absolute imports** for clarity: `from taskforce.core.domain.agent import Agent`
- **Relative imports allowed** within same package: `from .agent import Agent` (within `core/domain/`)

---

## File Naming Conventions

| Pattern | Purpose | Example |
|---------|---------|---------|
| `{name}_tool.py` | Tool implementations | `python_tool.py`, `git_tool.py` |
| `{name}_service.py` | Service implementations | `openai_service.py` |
| `{name}_manager.py` | Manager/coordinator classes | `file_state.py` (FileStateManager) |
| `test_{name}.py` | Unit tests | `test_agent.py`, `test_file_state.py` |
| `{name}.yaml` | Configuration files | `dev.yaml`, `llm_config.yaml` |
| `{version}_{description}.py` | Migration scripts | `001_initial_schema.py` |

---

## Environment-Specific Configurations

### Development (`application/config/dev.yaml`)

```yaml
profile: dev
state_manager: file
state_dir: ./agent_work/states
llm_provider: openai
tools:
  - python
  - file
  - git
  - web
log_level: DEBUG
```

### Production (`application/config/prod.yaml`)

```yaml
profile: prod
state_manager: database
database_url: ${DATABASE_URL}  # From environment variable
llm_provider: openai
tools:
  - python
  - file
  - git
  - github
  - web
  - powershell
log_level: INFO
```

---

## Package Entry Points

### CLI Entry Point

Defined in `pyproject.toml`:

```toml
[project.scripts]
taskforce = "taskforce.api.cli.main:app"
```

Enables command: `taskforce run mission "Analyze CSV file"`

### Programmatic API

```python
from taskforce.application.factory import AgentFactory

# Create agent with dev profile
factory = AgentFactory()
agent = factory.create_agent(profile="dev")

# Execute mission
result = await agent.execute(mission="Analyze data.csv", session_id="my-session")
```

---

## Code Reuse from Agent V2

**Source Location:** `capstone/agent_v2/`  
**Target Location:** `taskforce/src/taskforce/`

| Agent V2 File | Taskforce Destination | Refactoring Required |
|---------------|----------------------|---------------------|
| `agent.py` | `core/domain/agent.py` | Extract ReAct loop, remove infrastructure deps |
| `planning/todolist.py` | `core/domain/plan.py` | Rename class, extract LLM dependency |
| `statemanager.py` | `infrastructure/persistence/file_state.py` | Implement `StateManagerProtocol` |
| `tools/*.py` | `infrastructure/tools/native/*.py` | Implement `ToolProtocol` |
| `cli/main.py` | `api/cli/main.py` | Adapt to new factory pattern |

**Reuse Target:** ≥75% of Agent V2 code relocated and adapted to Clean Architecture.

---

## Critical Paths for Developers

### Adding a New Tool

1. Create `infrastructure/tools/native/{tool_name}_tool.py`
2. Implement `ToolProtocol` interface
3. Register in `application/factory.py` tool registry
4. Add tests in `tests/unit/test_tools_{tool_name}.py`
5. Update `docs/architecutre/section-5-components.md`

### Adding a New Configuration Profile

1. Create `application/config/{profile_name}.yaml`
2. Define state_manager, llm_provider, tools, log_level
3. Test with: `taskforce --profile {profile_name} run mission "Test"`

### Database Schema Changes

1. Generate migration: `alembic revision --autogenerate -m "Description"`
2. Review generated script in `alembic/versions/`
3. Apply migration: `alembic upgrade head`
4. Update `infrastructure/persistence/models.py` if needed

---

## Windows-Specific Considerations

**Platform:** Windows 10/11 with PowerShell 7+

### Path Handling

- Use `pathlib.Path` for cross-platform compatibility
- Avoid hardcoded `/` separators (use `Path.joinpath()`)
- Example: `Path(work_dir) / "states" / f"{session_id}.json"`

### PowerShell Tool

- `infrastructure/tools/native/powershell_tool.py` uses `subprocess` with `pwsh.exe`
- Avoid shell substitutions that don't work with `subprocess` on Windows
- Use `shell=False` and pass command as list: `["pwsh", "-Command", "..."]`

### Package Management

- **HARD CONSTRAINT:** Use `uv` (not pip/venv)
- Activate venv: `.\.venv\Scripts\Activate.ps1`
- Install deps: `uv sync`

---

## Quick Reference Commands

### Development Setup

```powershell
# Clone and setup
cd taskforce
uv venv .venv
.\.venv\Scripts\Activate.ps1
uv sync

# Run tests
uv run -m pytest tests/ -v

# Run CLI
taskforce --help
taskforce run mission "Analyze data.csv"
```

### Docker Compose

```powershell
# Start services (API + PostgreSQL)
docker-compose up -d

# View logs
docker-compose logs -f taskforce

# Run migrations
docker-compose exec taskforce alembic upgrade head

# Stop services
docker-compose down
```

### Code Quality

```powershell
# Format code
black src/ tests/

# Lint code
ruff check src/ tests/

# Type check
mypy src/

# Run all checks
black src/ tests/ && ruff check src/ tests/ && mypy src/ && pytest
```

---

## Related Documentation

- **Architecture Overview:** `docs/architecutre/section-2-high-level-architecture.md`
- **Component Details:** `docs/architecutre/section-5-components.md`
- **Tech Stack Decisions:** `docs/architecutre/section-3-tech-stack.md`
- **Coding Standards:** `docs/architecutre/coding-standards.md`
- **Deployment Guide:** `docs/architecutre/section-10-deployment.md`
- **Testing Strategy:** `docs/architecutre/section-11-testing-strategy.md`

---

## Glossary

- **Clean Architecture:** Four-layer architecture pattern (Core, Infrastructure, Application, API) with inward-only dependencies
- **Protocol (PEP 544):** Python structural subtyping (duck typing with type hints) for interface definitions
- **ReAct Loop:** Reason + Act execution pattern (Thought → Action → Observation)
- **TodoList:** Structured plan with dependencies, generated by LLM from mission description
- **State Manager:** Component responsible for session state persistence (file-based or database)
- **Tool:** Executable capability with name, description, parameters schema, and execute method
- **Profile:** Configuration preset (dev/staging/prod) defining infrastructure adapters and settings
- **uv:** Fast Python package manager (replacement for pip/venv) - HARD CONSTRAINT for this project

---

**For Questions or Clarifications:**  
Refer to architecture documentation in `docs/architecutre/` or user stories in `docs/stories/`.


