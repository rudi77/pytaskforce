# 5. Epic 1: Build Taskforce Production Framework with Clean Architecture

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
