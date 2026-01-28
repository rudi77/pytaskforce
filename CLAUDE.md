# CLAUDE.md - Taskforce Development Guide

**Version:** 1.0
**Date:** 2026-01-03
**Purpose:** Guide for AI-assisted development with Claude Code

---

## Project Overview

**Taskforce** is a production-ready multi-agent orchestration framework built with Clean Architecture principles. It provides autonomous AI agents that plan and execute complex tasks through LLM-driven reasoning (ReAct loop), TodoList decomposition, and extensible tool execution.

### Key Characteristics

- **Architecture:** Clean Architecture (Hexagonal) with strict four-layer separation
- **Language:** Python 3.11
- **Package Manager:** `uv` (NOT pip/venv) - **This is mandatory**
- **Deployment Modes:**
  - CLI (Typer + Rich) for local development
  - REST API (FastAPI) for production microservices
- **Persistence:** File-based (dev) or PostgreSQL (prod) via swappable adapters
- **LLM Integration:** OpenAI and Azure OpenAI via LiteLLM

---

## Documentation Structure

Documentation is maintained **as Markdown in-repo**. Canonical entry points:

| Location | Purpose |
|----------|---------|
| `README.md` | Main user entry point (Quick Start, CLI + API, links into `docs/`) |
| `docs/index.md` | Docs navigation hub |
| `docs/architecture.md` | Stable architecture entry-point (links into `docs/architecture/`) |
| `docs/adr/` | Architecture Decision Records (index: `docs/adr/index.md`) |
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

---

## Clean Architecture: Four-Layer Structure

Taskforce enforces strict architectural boundaries through four distinct layers:

```
taskforce/
├── src/taskforce/
│   ├── core/              # LAYER 1: Pure Domain Logic
│   │   ├── domain/        # Agent, PlanGenerator, Domain Events
│   │   ├── interfaces/    # Protocols (StateManager, LLM, Tool)
│   │   └── prompts/       # System prompts and templates
│   │
│   ├── infrastructure/    # LAYER 2: External Integrations
│   │   ├── persistence/   # File and DB state managers
│   │   ├── llm/           # LiteLLM service (OpenAI, Azure)
│   │   ├── tools/         # Native, RAG, and MCP tools
│   │   └── memory/        # Memory management
│   │
│   ├── application/       # LAYER 3: Use Cases & Orchestration
│   │   ├── factory.py     # Dependency injection
│   │   ├── executor.py    # Execution orchestration
│   │   └── profiles.py    # Configuration management
│   │
│   └── api/               # LAYER 4: Entrypoints
│       ├── cli/           # Typer CLI
│       └── routes/        # FastAPI REST endpoints
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
from taskforce.infrastructure.llm.openai_service import OpenAIService  # Wires infrastructure

# API layer
from taskforce.application.executor import AgentExecutor          # Uses application layer

# ❌ FORBIDDEN
# Core layer - NEVER import infrastructure
from taskforce.infrastructure.persistence.file_state import FileStateManager  # VIOLATION!

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

All layer boundaries use **Python Protocols (PEP 544)** instead of abstract base classes:

```python
# core/interfaces/state.py
from typing import Protocol, Optional, Dict, Any, List

class StateManagerProtocol(Protocol):
    """Protocol for session state persistence."""

    async def save_state(self, session_id: str, state_data: Dict[str, Any]) -> None:
        """Save session state."""
        ...

    async def load_state(self, session_id: str) -> Optional[Dict[str, Any]]:
        """Load session state."""
        ...
```

**Why Protocols?**
- Duck typing - any object matching the interface works
- Easier testing - no inheritance required for mocks
- More Pythonic - leverages structural subtyping

### 2. Dependency Injection via Factory

The `AgentFactory` wires domain objects with infrastructure adapters based on YAML configuration:

```python
# application/factory.py
class AgentFactory:
    def create_agent(self, profile: str = "dev") -> Agent:
        config = ProfileLoader.load(profile)

        # Select adapter based on config
        state_manager = self._create_state_manager(config)
        llm_provider = self._create_llm_provider(config)
        tools = self._create_tools(config)

        # Wire everything together
        return Agent(
            state_manager=state_manager,
            llm_provider=llm_provider,
            tools=tools
        )
```

### 3. ReAct Loop (Reason + Act)

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

**Implementation:** `src/taskforce/core/domain/agent.py`

---

## Development Workflow

### Setup

```bash
# Clone and navigate
cd /home/user/pytaskforce

# Install dependencies (MUST use uv)
uv sync

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
uv run pytest tests/integration/

# With coverage
uv run pytest --cov=taskforce --cov-report=html
```

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

### Running the Agent

```bash
# CLI mode
taskforce run mission "Analyze sales data and create visualization"

# With specific profile
taskforce run mission "..." --profile dev
taskforce run mission "..." --profile prod

# Interactive chat
taskforce chat

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

```python
# ✅ GOOD - Pure function in core
def validate_dependencies(plan: TodoList) -> bool:
    """Check for circular dependencies in plan."""
    # Pure logic, no side effects
    ...

# ✅ GOOD - Class for I/O in infrastructure
class DbStateManager:
    """PostgreSQL-backed state persistence."""

    def __init__(self, db_url: str):
        self._engine = create_async_engine(db_url)

    async def save_state(self, session_id: str, state_data: Dict) -> None:
        # Database I/O
        ...
```

### 5. Type Safety: Concrete Types over Dictionaries

- **No magic strings** - Use `Enum`, `Literal`, or class constants
- **Concrete data structures** - Use `dataclass`, `NamedTuple`, or Pydantic `BaseModel` instead of `dict`
- **Typed return values** - Functions return concrete types, not `Dict[str, Any]`

```python
# ❌ AVOID - Magic strings and dictionaries
def get_status(data: dict) -> dict:
    if data["status"] == "success":
        return {"code": 200, "message": "OK"}

# ✅ PREFERRED - Enums and dataclasses
from dataclasses import dataclass
from enum import Enum

class Status(Enum):
    SUCCESS = "success"
    FAILED = "failed"

@dataclass
class StatusResult:
    code: int
    message: str

def get_status(data: RequestData) -> StatusResult:
    if data.status == Status.SUCCESS:
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
│   ├── core/              # Pure domain logic tests (protocol mocks)
│   ├── infrastructure/    # Adapter tests (may use test DB)
│   └── application/       # Service tests (integration-lite)
├── integration/           # End-to-end tests
└── fixtures/              # Shared test data
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

**Infrastructure Tests:**

```python
# tests/integration/test_file_state_manager.py
import pytest
from pathlib import Path
from taskforce.infrastructure.persistence.file_state import FileStateManager

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

Taskforce uses YAML configuration profiles in `configs/`:

```yaml
# configs/dev.yaml
agent:
  type: generic
  planning_strategy: native_react

persistence:
  type: file
  work_dir: ./workspace

llm:
  provider: openai
  model: gpt-4o
  temperature: 0.7

logging:
  level: DEBUG
  format: console
```

```yaml
# configs/prod.yaml
agent:
  type: generic
  planning_strategy: native_react

persistence:
  type: database
  database_url: ${DATABASE_URL}  # From environment

llm:
  provider: azure
  deployment_name: ${AZURE_DEPLOYMENT}
  temperature: 0.5

logging:
  level: WARNING
  format: json
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

---

## Common Patterns and Recipes

### Enabling Long-Term Memory

**Goal:** Add session-persistent memory to an agent profile

**Prerequisites:**
- Node.js v18+ and NPM v9+ installed

**Steps:**

1. **Add MCP Memory Server to profile config:**

```yaml
# configs/your_agent.yaml

profile: your_agent
specialist: coding  # or rag, or custom

persistence:
  type: file
  work_dir: .taskforce_your_agent

# Add this section
mcp_servers:
  - type: stdio
    command: npx
    args:
      - "-y"
      - "@modelcontextprotocol/server-memory"
    env:
      MEMORY_FILE_PATH: ".taskforce_your_agent/.memory/knowledge_graph.jsonl"
    description: "Long-term knowledge graph memory"
```

2. **The agent automatically gains 9 memory tools:**
- `create_entities` - Store new entities (User, Project, Pattern, etc.)
- `create_relations` - Link entities (e.g., "Alice works_on ProjectX")
- `add_observations` - Add facts to entities
- `read_graph` - Retrieve entire knowledge graph
- `search_nodes` - Search for specific entities
- `open_nodes` - Open specific entities by name
- `delete_entities`, `delete_observations`, `delete_relations` - Cleanup

3. **System prompt automatically includes memory guidance:**
- Agent checks memory at conversation start
- Agent monitors for memorable information during execution
- Agent updates memory when learning new facts

**Example Memory Usage:**

```python
# Agent stores user preference
create_entities([{
  "name": "User_Alice",
  "entityType": "User",
  "observations": ["Prefers type hints", "Senior Engineer"]
}])

# Agent links user to project
create_relations([{
  "from": "User_Alice",
  "to": "TaskforceProject",
  "relationType": "contributes_to"
}])

# Later session - agent recalls preference
search_nodes("Alice")  # Finds previous observations
```

**See:** [Long-Term Memory Documentation](docs/features/longterm-memory.md)

---

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

2. **Register in factory:**

```python
# application/factory.py
from taskforce.infrastructure.tools.native.my_tool import MyTool

class AgentFactory:
    def _create_tools(self, config: dict) -> List[ToolProtocol]:
        tools = [
            # ... existing tools
            MyTool(),
        ]
        return tools
```

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

    async def save_state(self, session_id: str, state_data: Dict[str, Any]) -> None:
        # Implementation...
        pass

    async def load_state(self, session_id: str) -> Optional[Dict[str, Any]]:
        # Implementation...
        pass

    async def delete_state(self, session_id: str) -> None:
        # Implementation...
        pass

    async def list_sessions(self) -> List[str]:
        # Implementation...
        pass
```

2. **Add to factory:**

```python
# application/factory.py
def _create_state_manager(self, config: dict) -> StateManagerProtocol:
    persistence_type = config.get("persistence", {}).get("type")

    if persistence_type == "my_custom":
        return MyStateManager(**config["persistence"])
    # ... other types
```

---

## Important Implementation Notes

### 1. Async/Await Patterns

- **ALL I/O operations must be async** - file, database, HTTP, LLM calls
- Use `asyncio.gather()` for parallel operations
- Use `async with` for resource management

```python
# ✅ GOOD - Async I/O
async def process_files(file_paths: List[str]) -> List[str]:
    async with aiofiles.open(file_paths[0]) as f:
        content = await f.read()
    return content

# ❌ BAD - Blocking I/O
def process_files(file_paths: List[str]) -> List[str]:
    with open(file_paths[0]) as f:  # Blocks event loop!
        content = f.read()
```

### 2. State Versioning

All state changes include version tracking for optimistic locking:

```python
state_data = {
    "mission": "...",
    "steps": [...],
    "version": 5  # Increment on each save
}
```

### 3. Structured Logging

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

### 4. Tool Execution Isolation

Python tools run in isolated namespaces to prevent cross-contamination:

```python
# infrastructure/tools/native/python_tool.py
def execute(self, code: str) -> Dict[str, Any]:
    namespace = {}  # Isolated namespace
    exec(code, namespace)  # Don't pollute global scope
    return namespace.get("result")
```

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
- `src/taskforce/core/domain/plan.py` - TodoList planning logic
- `src/taskforce/core/domain/events.py` - Domain events

### Protocols
- `src/taskforce/core/interfaces/state.py` - State persistence protocol
- `src/taskforce/core/interfaces/llm.py` - LLM provider protocol
- `src/taskforce/core/interfaces/tools.py` - Tool execution protocol

### Infrastructure
- `src/taskforce/infrastructure/persistence/file_state.py` - File-based state
- `src/taskforce/infrastructure/persistence/db_state.py` - Database state
- `src/taskforce/infrastructure/llm/litellm_service.py` - LLM service
- `src/taskforce/infrastructure/tools/native/*.py` - Native tools

### Application
- `src/taskforce/application/factory.py` - Dependency injection
- `src/taskforce/application/executor.py` - Execution orchestration
- `src/taskforce/application/profiles.py` - Configuration loading

### API
- `src/taskforce/api/server.py` - FastAPI application
- `src/taskforce/api/cli/main.py` - CLI entry point

---

## Additional Resources

- **Docs Hub:** `docs/index.md`
- **Architecture:** `docs/architecture.md` (entry) → `docs/architecture/` (sharded pages)
- **CLI Guide:** `docs/cli.md`
- **API Guide:** `docs/api.md`
- **Profiles & Config:** `docs/profiles.md`
- **Testing:** `docs/testing.md`
- **ADRs:** `docs/adr/index.md`
- **PRD:** `docs/prd.md`
- **Stories:** `docs/stories/`
- **Coding Standards:** `docs/architecture/coding-standards.md`

---

## Quick Reference: Do's and Don'ts

### ✅ DO

- Use `uv` for all package management
- Follow the four-layer architecture strictly
- Write protocol-compatible implementations
- Add comprehensive docstrings
- Write tests for all new functionality
- Use type annotations everywhere
- Use concrete types (`dataclass`, Pydantic) instead of `dict`
- Use `Enum` or constants instead of magic strings
- Keep functions ≤30 lines
- Log with structured context
- Make everything async for I/O
- **Update docs when changing CLI/API/config** (see Documentation Upkeep Rule above)

### ❌ DON'T

- Import infrastructure in core domain
- Use `pip` or `venv` (use `uv` only)
- Create circular dependencies between layers
- Write blocking I/O (use async)
- Catch generic `Exception` without re-raising
- Skip type annotations
- Use `Dict[str, Any]` for structured data (use dataclasses/Pydantic)
- Use magic strings (use Enum or constants)
- Create God objects or classes
- Log sensitive data (API keys, passwords)
- Hardcode configuration values

---

**Last Updated:** 2026-01-28
**For Questions:** See `docs/` or create an issue in the repository
