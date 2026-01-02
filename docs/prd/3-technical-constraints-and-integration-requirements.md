# 3. Technical Constraints and Integration Requirements

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
