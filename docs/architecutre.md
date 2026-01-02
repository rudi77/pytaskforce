🏗️ **Taskforce Architecture Document Creation**

**Mode:** Interactive  
**Output File:** `taskforce/docs/architecture.md`  
**Template:** Architecture Document v2.0

---

## Section 1: Introduction

Based on the comprehensive PRD and Agent V2 brownfield analysis, here's the introductory section:

---

### **Taskforce Architecture Document**

**Version:** 1.0  
**Date:** 2025-11-22  
**Author:** Winston (Architect Agent)

This document outlines the overall project architecture for **Taskforce**, a production-ready ReAct agent framework implementing Clean Architecture principles. Its primary goal is to serve as the guiding architectural blueprint for AI-driven development, ensuring consistency and adherence to chosen patterns and technologies.

**Relationship to Frontend Architecture:** Taskforce is a backend framework/microservice platform with CLI and REST API interfaces. There is no traditional frontend UI component. The "user interface" consists of:
- **Typer-based CLI** for direct command-line interaction
- **FastAPI REST API** for programmatic access and potential future web UI integration

Core technology stack choices documented herein are definitive for the entire project.

---

### **Starter Template or Existing Project**

**Source Project:** Agent V2 (`capstone/agent_v2`)

**Relationship:** Taskforce is **NOT a refactoring** of Agent V2, but rather a **greenfield implementation** in a new directory (`taskforce/`) that **reuses proven code** (≥75% of working logic) from Agent V2 by relocating and adapting it into Clean Architecture layers.

**Key Constraints from Agent V2:**
- **Technology Stack**: Python 3.11, LiteLLM, Typer, Rich, structlog, FastAPI, SQLAlchemy, Alembic (inherited from Agent V2)
- **Package Manager**: `uv` (NOT pip/venv) - this is a hard constraint
- **Platform**: Windows-first development with PowerShell 7+ support
- **Core Algorithm**: ReAct (Reason + Act) execution loop - proven implementation to be extracted and refactored
- **Tool Semantics**: Isolated Python execution namespaces, retry logic, timeout handling - must be preserved
- **Configuration Format**: YAML-based configuration files - maintain compatibility

**What Changes Architecturally:**
- **Four-Layer Structure**: Core → Infrastructure → Application → API (replacing flat PoC structure)
- **Protocol-Based Interfaces**: All cross-layer dependencies via Python protocols (PEP 544)
- **Swappable Adapters**: File-based (dev) and PostgreSQL (prod) persistence via shared protocols
- **Microservice Ready**: FastAPI REST API for stateless deployment with horizontal scaling
- **Dependency Injection**: AgentFactory wires domain objects with infrastructure adapters based on configuration profiles

**What Doesn't Change:**
- ReAct loop algorithm and execution semantics
- TodoList planning logic and LLM prompts
- Tool implementations and parameter schemas
- LLM service integration (LiteLLM abstraction)
- CLI command structure (similar to Agent V2 for user familiarity)

---

### **Change Log**

| Date | Version | Description | Author |
|------|---------|-------------|--------|
| 2025-11-22 | 1.0 | Initial architecture document for Taskforce Clean Architecture implementation | Winston (Architect) |

---

### **Rationale:**

**Trade-offs:**
1. **Greenfield vs. Refactoring**: Chose greenfield in new directory to eliminate risk to operational Agent V2, but requires code relocation effort
2. **Code Reuse Target (≥75%)**: Aggressive reuse goal to accelerate delivery, but may carry forward some Agent V2 technical debt (mitigated by planned layer boundaries)
3. **Protocol-Based Interfaces**: More flexible than abstract base classes (duck typing) but less explicit in class hierarchies

**Key Assumptions:**
- Agent V2 architecture doc and PRD provide complete requirements specification
- Python 3.11 protocols (PEP 544) are well-understood by development team
- PostgreSQL is acceptable production database (per PRD)
- ≥75% code reuse is achievable while maintaining architectural boundaries

**Decisions Requiring Validation:**
- Four-layer Clean Architecture vs. three-layer (could merge application and API) - chose four for maximum separation
- Protocol vs. ABC for interfaces - chose protocols for flexibility
- Monorepo at taskforce/ root vs. separate repos - chose single repo for simplicity

---

## Section 2: High Level Architecture

### **Technical Summary**

Taskforce is a **production-ready ReAct agent framework** implementing **Clean Architecture (Hexagonal Architecture)** principles with strict four-layer separation. The system enables autonomous AI agents to plan and execute complex tasks through LLM-driven reasoning (ReAct loop), TodoList decomposition, and extensible tool execution. The architecture supports **dual deployment modes**: local development via CLI with file-based persistence, and production microservice deployment via FastAPI REST API with PostgreSQL persistence. Core business logic (ReAct loop, planning algorithms) is isolated in the domain layer with zero infrastructure dependencies, enabling protocol-based testing and swappable adapters for persistence (file/database), LLM providers (OpenAI/Azure), and tool implementations. This architecture achieves PRD goals by: (G1) enforcing architectural boundaries via protocol-based interfaces, (G2) enabling adapter swapping through dependency injection, (G3) supporting stateless microservice deployment via FastAPI, (G4) maintaining CLI compatibility with Agent V2, (G5) improving testability through protocol mocking, and (G6) establishing clear extension points for new tools and providers.

---

### **High Level Overview**

**1. Architectural Style:** **Clean Architecture (Ports & Adapters / Hexagonal Architecture)** with strict four-layer separation:
   - **Core Layer** (domain logic): Pure Python business logic with zero external dependencies
   - **Infrastructure Layer** (adapters): I/O implementations (database, LLM, tools, file system)
   - **Application Layer** (use cases): Orchestration services and dependency injection
   - **API Layer** (entrypoints): User-facing interfaces (CLI, REST API)

**2. Repository Structure:** **Monorepo** at `taskforce/` root (from PRD decision)
   - Single Python package with four layer subdirectories
   - Managed by `uv` package manager
   - Tests mirror source structure (`tests/unit/`, `tests/integration/`)

**3. Service Architecture:** **Hybrid deployment model**
   - **Development Mode**: Standalone CLI application with file-based persistence (zero infrastructure dependencies)
   - **Production Mode**: Stateless FastAPI microservice with PostgreSQL persistence (horizontal scaling, health checks, observability)
   - **Shared Core**: Both modes use identical domain logic via dependency injection

**4. Primary Data Flow:**
   ```
   User Input (CLI/API) 
     → AgentExecutor (orchestration)
       → Agent.execute() (ReAct loop)
         → LLMProvider.complete() (thought generation)
         → Tool.execute() (action execution)
         → StateManager.save_state() (observation persistence)
       → TodoListManager (planning)
     → ExecutionResult (output)
   ```

**5. Key Architectural Decisions:**

   - **Protocol-Based Interfaces**: All cross-layer dependencies via Python protocols (PEP 544) rather than abstract base classes, enabling duck typing and easier testing
   
   - **Dependency Injection via Factory**: AgentFactory reads YAML configuration profiles (dev/staging/prod) and wires appropriate adapters at runtime
   
   - **Dual Persistence Strategy**: File-based (development) and PostgreSQL (production) implement same `StateManagerProtocol`, allowing seamless switching via configuration
   
   - **Code Reuse from Agent V2**: ≥75% of working logic relocated rather than rewritten, focusing architectural effort on layer boundaries and protocol definitions
   
   - **Async-First Design**: All I/O operations use async/await patterns (aiofiles, asyncpg, async SQLAlchemy) for performance and scalability

---

### **High Level Project Diagram**

```mermaid
graph TB
    subgraph "API Layer (Entrypoints)"
        CLI[Typer CLI<br/>commands: run, chat, tools, sessions]
        REST[FastAPI REST API<br/>endpoints: /execute, /sessions, /health]
    end
    
    subgraph "Application Layer (Orchestration)"
        EXEC[AgentExecutor<br/>Mission execution orchestration]
        FACTORY[AgentFactory<br/>Dependency injection & wiring]
        PROFILES[ProfileLoader<br/>YAML config management]
    end
    
    subgraph "Core Layer (Domain Logic)"
        AGENT[Agent<br/>ReAct loop execution]
        PLAN[PlanGenerator<br/>TodoList planning]
        EVENTS[Domain Events<br/>Thought, Action, Observation]
    end
    
    subgraph "Core Interfaces (Protocols)"
        STATE_PROTO[StateManagerProtocol]
        LLM_PROTO[LLMProviderProtocol]
        TOOL_PROTO[ToolProtocol]
        TODO_PROTO[TodoListManagerProtocol]
    end
    
    subgraph "Infrastructure Layer (Adapters)"
        FILE_STATE[FileStateManager<br/>JSON persistence]
        DB_STATE[DbStateManager<br/>PostgreSQL persistence]
        LLM_SVC[OpenAIService<br/>LiteLLM integration]
        TOOLS[Native Tools<br/>Python, File, Git, Shell, Web]
        RAG_TOOLS[RAG Tools<br/>Azure AI Search]
        MEMORY[MemoryManager<br/>Cross-session learning]
    end
    
    subgraph "External Systems"
        OPENAI[OpenAI API]
        AZURE_OPENAI[Azure OpenAI]
        AZURE_SEARCH[Azure AI Search]
        POSTGRES[(PostgreSQL)]
        FILESYSTEM[File System]
    end
    
    %% API Layer connections
    CLI --> EXEC
    REST --> EXEC
    
    %% Application Layer connections
    EXEC --> FACTORY
    FACTORY --> PROFILES
    FACTORY --> AGENT
    
    %% Core Layer connections
    AGENT --> STATE_PROTO
    AGENT --> LLM_PROTO
    AGENT --> TOOL_PROTO
    AGENT --> TODO_PROTO
    PLAN --> LLM_PROTO
    
    %% Protocol implementations
    STATE_PROTO -.implements.-> FILE_STATE
    STATE_PROTO -.implements.-> DB_STATE
    LLM_PROTO -.implements.-> LLM_SVC
    TOOL_PROTO -.implements.-> TOOLS
    TOOL_PROTO -.implements.-> RAG_TOOLS
    TODO_PROTO -.implements.-> FILE_STATE
    TODO_PROTO -.implements.-> DB_STATE
    
    %% Infrastructure to External
    FILE_STATE --> FILESYSTEM
    DB_STATE --> POSTGRES
    LLM_SVC --> OPENAI
    LLM_SVC --> AZURE_OPENAI
    RAG_TOOLS --> AZURE_SEARCH
    
    %% Styling
    classDef coreLayer fill:#e1f5ff,stroke:#0288d1,stroke-width:2px
    classDef infraLayer fill:#fff3e0,stroke:#f57c00,stroke-width:2px
    classDef appLayer fill:#f3e5f5,stroke:#7b1fa2,stroke-width:2px
    classDef apiLayer fill:#e8f5e9,stroke:#388e3c,stroke-width:2px
    classDef external fill:#fce4ec,stroke:#c2185b,stroke-width:2px
    
    class AGENT,PLAN,EVENTS coreLayer
    class STATE_PROTO,LLM_PROTO,TOOL_PROTO,TODO_PROTO coreLayer
    class FILE_STATE,DB_STATE,LLM_SVC,TOOLS,RAG_TOOLS,MEMORY infraLayer
    class EXEC,FACTORY,PROFILES appLayer
    class CLI,REST apiLayer
    class OPENAI,AZURE_OPENAI,AZURE_SEARCH,POSTGRES,FILESYSTEM external
```

---

### **Architectural and Design Patterns**

**Core Patterns:**

- **Clean Architecture (Hexagonal Architecture):** Four-layer separation with dependency inversion - domain logic at center, infrastructure at edges. _Rationale:_ Achieves PRD Goal G1 (strict architectural boundaries) and G5 (testability via protocol mocking). Enables independent evolution of business logic, persistence, and API layers.

- **Dependency Injection via Factory Pattern:** AgentFactory constructs agent instances by reading configuration profiles and wiring appropriate adapters. _Rationale:_ Achieves PRD Goal G2 (swappable persistence backends) and G6 (clear extension points). Centralized wiring makes dependency graph explicit and testable.

- **Protocol-Based Interfaces (Ports):** All layer boundaries defined by Python protocols (PEP 544) rather than abstract base classes. _Rationale:_ Enables structural subtyping (duck typing) without inheritance constraints. Simplifies testing via protocol-compatible mocks. More Pythonic than ABC-based inheritance.

- **Adapter Pattern:** Infrastructure layer provides multiple implementations of core protocols (FileStateManager vs DbStateManager, both implementing StateManagerProtocol). _Rationale:_ Achieves PRD Goal G2 (swappable backends). Dev environment uses file adapters, production uses database adapters, with zero domain logic changes.

- **Repository Pattern (for Persistence):** StateManager and TodoListManager abstract data access logic, isolating domain from persistence details. _Rationale:_ Enables database migration flexibility. Supports both file-based and relational persistence through same interface.

**Communication Patterns:**

- **ReAct Loop (Reason + Act):** Iterative cycle of Thought (LLM reasoning) → Action (tool execution) → Observation (result recording). _Rationale:_ Proven pattern from Agent V2. Enables autonomous task execution with explainable decision-making. Core to agent intelligence.

- **Synchronous Request-Response (REST API):** FastAPI endpoints for `/execute`, `/sessions` with JSON request/response. _Rationale:_ Standard microservice pattern. Enables programmatic access and future web UI integration. Supports observability (health checks, metrics).

- **Event-Driven (Internal):** Domain events (Thought, Action, Observation) flow through ReAct loop, enabling progress callbacks and streaming updates. _Rationale:_ Decouples execution logic from progress reporting. Enables both CLI (Rich progress bars) and API (Server-Sent Events) interfaces.

**Code Organization Patterns:**

- **Domain-Driven Design (Lite):** Core domain entities (Agent, TodoList, TodoItem) encapsulate business logic. _Rationale:_ Keeps planning algorithms and execution semantics close to domain concepts. Avoids anemic domain model anti-pattern.

- **Service Layer Pattern:** AgentExecutor coordinates ReAct loop execution with logging, error handling, state persistence. _Rationale:_ Shared orchestration logic between CLI and API entrypoints. Single source of truth for execution workflow.

- **Strategy Pattern (Tool Execution):** Each tool implements ToolProtocol with polymorphic `execute()` method. Agent selects and invokes tools dynamically based on action decisions. _Rationale:_ Extensibility - new tools added without modifying agent core. Supports 11+ native tools plus RAG tools.

**Data Patterns:**

- **JSONB for Flexibility (PostgreSQL):** State and TodoList data stored as JSONB columns with relational metadata. _Rationale:_ Preserves schema compatibility with file-based JSON format. Allows evolution of state structure without migrations. Enables JSON query operators.

- **Optimistic Locking (State Versioning):** State snapshots include version numbers for detecting concurrent modifications. _Rationale:_ Prevents lost updates in production environment with multiple agent instances. Inherited from Agent V2 design.

- **Immutable Domain Events:** Thought, Action, Observation events are immutable dataclasses. _Rationale:_ Simplifies reasoning about execution history. Enables event replay for debugging.

---

### **Rationale:**

**Trade-offs Made:**

1. **Four Layers vs. Three**: Chose separate Application and API layers (vs. merging them) to isolate orchestration logic (AgentExecutor) from entrypoint concerns (CLI/REST). Trade-off: More directories and layers to understand, but clearer separation enables independent testing and evolution.

2. **Protocol vs. Abstract Base Classes**: Protocols enable duck typing without inheritance, but class hierarchy is less explicit. Trade-off: Gained flexibility for testing (any object matching protocol works), lost explicit "implements" relationships in code.

3. **Dual Persistence Strategy**: Maintaining both file and database adapters doubles persistence code surface area. Trade-off: Development simplicity (no database required locally) vs. maintenance burden (two implementations to keep in sync).

4. **Code Reuse from Agent V2**: Aggressive ≥75% reuse goal may carry forward technical debt. Trade-off: Faster delivery and proven logic vs. potential architectural compromises inherited from PoC structure.

**Key Assumptions:**

- ReAct algorithm from Agent V2 is production-ready (validated: PRD states "proven implementation")
- Python 3.11 protocols are mature (validated: PEP 544 since Python 3.8)
- Team familiar with Clean Architecture concepts (needs validation: training may be required)
- Four-layer structure won't cause confusion (needs validation: may require architecture onboarding)

**Decisions Requiring Validation:**

- **Is four-layer complexity justified?** Could we merge Application + API into single "Service" layer?
- **Protocol testing strategy:** How do we verify implementations satisfy protocols at runtime?
- **Database schema evolution:** JSONB gives flexibility - do we need formal schema versioning?

🏗️ **Proceeding to Tech Stack...**

---

## Section 3: Tech Stack

### **Cloud Infrastructure**

- **Provider:** **Hybrid** (Development: Local filesystem | Production: Cloud-agnostic via containerization)
- **Key Services:** 
  - PostgreSQL (managed service: AWS RDS / Azure Database / Google Cloud SQL)
  - Container Orchestration: Kubernetes (any cloud provider)
  - Optional: Azure OpenAI (if Azure-specific LLM features needed)
  - Optional: Azure AI Search (for RAG capabilities)
- **Deployment Regions:** 
  - Development: Local
  - Staging/Production: Cloud provider regions per organizational requirements
  - _Note: Architecture is cloud-agnostic via Docker/Kubernetes - provider flexibility maintained_

---

### **Technology Stack Table**

| Category | Technology | Version | Purpose | Rationale |
|----------|-----------|---------|---------|-----------|
| **Language** | Python | 3.11+ | Primary development language | Required minimum version for Agent V2 compatibility; excellent async support, type hints, dataclasses |
| **Package Manager** | uv | latest | Dependency management | **HARD CONSTRAINT** from Agent V2; NOT pip/venv; faster than pip, better dependency resolution |
| **LLM Orchestration** | LiteLLM | 1.7.7.0 | Multi-provider LLM abstraction | Unified interface for OpenAI, Azure OpenAI, Anthropic; proven in Agent V2; parameter mapping for GPT-4/GPT-5 |
| **CLI Framework** | Typer | 0.9.0+ | Command-line interface | Modern CLI with auto-completion, argument validation; integrates with Rich for terminal UI |
| **Terminal UI** | Rich | 13.0.0+ | CLI output formatting | Colored output, progress bars, tables, syntax highlighting; essential for developer experience |
| **Web Framework** | FastAPI | 0.116.1+ | REST API microservice | Async support, auto-generated OpenAPI docs, Pydantic validation, high performance |
| **Async I/O** | aiofiles | 23.2.1 | Async file operations | File-based state manager requires async file I/O for performance |
| **Structured Logging** | structlog | 24.2.0 | Application logging | JSON/console logging with context; production observability; correlation IDs |
| **Configuration** | Pydantic | 2.0.0+ | Data validation and settings | Type-safe configuration management; validates YAML profiles at startup |
| **Configuration** | Pydantic Settings | 2.0.0+ | Environment variable management | Environment variable overrides for config; 12-factor app compliance |
| **Database** | PostgreSQL | 15+ | Production persistence | JSONB support for flexible state storage; strong consistency; proven at scale |
| **ORM** | SQLAlchemy | 2.0+ | Database abstraction | Async support, robust migrations, flexible querying; industry standard |
| **Migrations** | Alembic | 1.13+ | Database schema management | Version-controlled schema migrations; integrates with SQLAlchemy |
| **Database Driver** | asyncpg | 0.29+ | PostgreSQL async driver | High-performance async PostgreSQL driver for SQLAlchemy |
| **RAG Search** | Azure AI Search SDK | 11.4.0+ | Semantic search and document retrieval | Vector search capabilities; security filtering; proven in Agent V2 RAG agents |
| **HTTP Client** | aiohttp | 3.9+ | Async HTTP requests | Used by web tools (WebSearchTool, WebFetchTool); async-first design |
| **Testing Framework** | pytest | 8.4.2+ | Unit and integration testing | De facto Python testing standard; extensive plugin ecosystem |
| **Async Testing** | pytest-asyncio | 0.23+ | Async test support | Enables testing of async functions and coroutines |
| **Test Coverage** | pytest-cov | 4.1+ | Code coverage reporting | Measures test coverage; enforces ≥90% for core domain |
| **Linting** | Ruff | 0.1.0+ | Fast Python linter | Extremely fast linter; replaces Flake8, isort, pydocstyle; PEP8 enforcement |
| **Formatting** | Black | 23.0+ | Code formatting | Opinionated formatter; zero config; ensures consistent style |
| **Type Checking** | mypy | 1.7+ | Static type analysis | Validates type hints; catches type errors before runtime; protocol compatibility |
| **Containerization** | Docker | 24.0+ | Application packaging | Multi-stage builds for optimization; production deployment |
| **Container Orchestration** | Kubernetes | 1.28+ | Production orchestration | Horizontal scaling, health checks, rolling updates; cloud-agnostic |
| **Process Manager** | uvicorn | 0.25+ | ASGI server | FastAPI application server; async request handling; worker management |
| **Monitoring** | structlog (JSON output) | 24.2.0 | Structured logging | JSON logs for centralized aggregation (ELK, Splunk, Datadog) |
| **YAML Parsing** | PyYAML | 6.0+ | Configuration file parsing | Loads YAML profiles (dev/staging/prod configs) |
| **Data Validation** | Pydantic | 2.0.0+ | Runtime data validation | Validates API requests, configuration, data models; type coercion |

---

### **Rationale:**

**Technology Selection Philosophy:**

1. **Proven Stack from Agent V2**: Inherited core technologies (Python 3.11, LiteLLM, Typer, Rich, structlog) because they're battle-tested in the PoC. Trade-off: Less flexibility to choose alternatives vs. reduced risk from proven components.

2. **Async-First Design**: All I/O operations use async/await (aiofiles, asyncpg, aiohttp). Rationale: Production scalability requires non-blocking I/O. FastAPI's async support enables high concurrency. Trade-off: More complex programming model vs. performance gains.

3. **PostgreSQL over NoSQL**: Chose relational database with JSONB for flexibility. Rationale: Session state requires strong consistency (multiple agents accessing same session). JSONB columns provide schema flexibility while maintaining relational integrity. Trade-off: More operational overhead than managed NoSQL vs. consistency guarantees.

4. **SQLAlchemy 2.0+ (async)**: Chose ORM over raw SQL. Rationale: Abstracts database dialect differences, enables migrations via Alembic, provides type-safe queries. Version 2.0 added full async support. Trade-off: Performance overhead of ORM vs. developer productivity.

5. **Cloud-Agnostic Architecture**: Docker + Kubernetes instead of cloud-specific services (AWS Lambda, Azure Functions). Rationale: Maintains flexibility to deploy anywhere. Enables local dev environment parity. Trade-off: Don't get cloud-specific optimizations (serverless scaling, managed services) vs. vendor lock-in avoidance.

6. **Ruff over Flake8/isort**: Modern, extremely fast linter. Rationale: 10-100x faster than traditional tools, consolidates multiple linters. Trade-off: Relatively new tool (less mature) vs. dramatic speed improvements.

7. **uv Package Manager (HARD CONSTRAINT)**: Required for Agent V2 compatibility. Rationale: Faster than pip, better dependency resolution, proven in existing codebase. Team already familiar. Trade-off: Less widespread adoption than pip vs. performance benefits.

**Version Pinning Strategy:**

- All versions explicitly pinned (not "latest") for reproducibility
- LTS versions preferred (Python 3.11, PostgreSQL 15, Node 20 for future JS tooling)
- Regular dependency updates via automated security scanning

**Key Assumptions:**

- Team familiar with async Python (asyncio, aiofiles, asyncpg) - **needs validation**
- PostgreSQL operational expertise available for production - **needs validation**
- Azure AI Search available for RAG features (optional) - **confirmed via PRD**
- Kubernetes cluster available for production (or willing to set up) - **needs validation**

**Technology NOT Selected (and Why):**

- ❌ **MongoDB**: Rejected in favor of PostgreSQL - need strong consistency for state management
- ❌ **GraphQL**: Rejected in favor of REST - simpler for CLI-first architecture, REST sufficient for current needs
- ❌ **Redis**: Deferred - caching can be added later if needed; premature optimization
- ❌ **Serverless (AWS Lambda)**: Rejected in favor of Docker/Kubernetes - need longer execution times for complex missions, avoid vendor lock-in
- ❌ **Django**: Rejected in favor of FastAPI - need async support, lighter weight for API-only service

**Critical Questions Requiring User Validation:**

1. **PostgreSQL Operational Readiness**: Does team have experience operating PostgreSQL in production? If not, consider managed service (AWS RDS, Azure Database).
2. **Kubernetes Complexity**: Is team prepared for Kubernetes operational overhead? Alternative: Start with Docker Compose, migrate to K8s later.
3. **Azure AI Search Dependency**: RAG features require Azure AI Search - is Azure commitment acceptable? Alternative: Abstract search behind protocol for provider flexibility.
4. **Python 3.11 Minimum**: Can production environment support Python 3.11+? (Released Oct 2022, generally available).

🏗️ **Executing: Critique and Refine**

---

### **Critical Analysis of Tech Stack**

**User Feedback Integration:**
- **Deployment Platform**: Docker Compose (immediate) → Kubernetes (future migration path)
- **PostgreSQL Deployment**: Containerized in docker-compose (not managed cloud service)

**Critique and Refinements:**

**1. Cloud Infrastructure Section - NEEDS REVISION**

**Issue:** Current cloud infrastructure section assumes production cloud deployment, but user wants Docker Compose environment.

**Refined Approach:**
```
- **Provider:** Local/Self-Hosted (Docker Compose)
- **Key Services:** 
  - PostgreSQL: Docker container (official postgres:15-alpine image)
  - Taskforce API: Docker container (custom build from Dockerfile)
  - Future: Azure AI Search (external SaaS for RAG, optional)
- **Deployment Strategy:** 
  - **Phase 1 (Current):** Docker Compose multi-container environment
  - **Phase 2 (Future):** Kubernetes migration path maintained via container-first design
- **Orchestration:** docker-compose.yml with service dependencies, health checks, volumes
```

**2. Container Orchestration Row - UPDATE PRIORITY**

**Current:** Lists Kubernetes 1.28+ as immediate technology
**Refined:** Docker Compose as primary, Kubernetes as migration target

| Category | Technology | Version | Purpose | Rationale |
|----------|-----------|---------|---------|-----------|
| **Container Orchestration** | Docker Compose | 2.23+ | Multi-container local/staging deployment | Simpler than Kubernetes; sufficient for initial deployment; enables local development parity with staging/production |
| **Future Orchestration** | Kubernetes | 1.28+ | Production scalability (future) | Migration path for horizontal scaling; container-first design ensures K8s compatibility when needed |

**3. PostgreSQL Deployment - CLARIFY APPROACH**

**Current:** Assumes managed PostgreSQL service
**Refined:** Containerized PostgreSQL with considerations

**Add to Tech Stack Notes:**
- **PostgreSQL Container**: `postgres:15-alpine` official image
- **Data Persistence**: Docker volume for `/var/lib/postgresql/data`
- **Configuration**: Environment variables for database name, user, password
- **Backup Strategy**: Volume backup scripts in `scripts/backup-db.sh`
- **Performance Tuning**: Custom postgresql.conf mounted via volume for production-like settings

**Operational Considerations:**
```yaml
# docker-compose.yml PostgreSQL service
postgres:
  image: postgres:15-alpine
  environment:
    POSTGRES_DB: taskforce
    POSTGRES_USER: taskforce
    POSTGRES_PASSWORD: ${DB_PASSWORD}
  volumes:
    - postgres_data:/var/lib/postgresql/data
    - ./postgres.conf:/etc/postgresql/postgresql.conf
  ports:
    - "5432:5432"
  healthcheck:
    test: ["CMD-SHELL", "pg_isready -U taskforce"]
    interval: 10s
    timeout: 5s
    retries: 5
```

**4. Additional Technologies for Docker Compose Environment**

**Add to Tech Stack:**

| Category | Technology | Version | Purpose | Rationale |
|----------|-----------|---------|---------|-----------|
| **Container Platform** | Docker | 24.0+ | Container runtime | Industry standard; multi-stage builds for optimization; local dev parity |
| **Service Orchestration** | Docker Compose | 2.23+ | Multi-container management | Defines service dependencies, networks, volumes; single command deployment |
| **Database Admin** | pgAdmin (optional) | latest | PostgreSQL management UI | Containerized admin tool for database inspection; useful for development |

**5. Monitoring/Observability - SIMPLIFY FOR DOCKER COMPOSE**

**Current:** Assumes cloud-based log aggregation
**Refined:** Container-native logging

**Add to Tech Stack:**

| Category | Technology | Version | Purpose | Rationale |
|----------|-----------|---------|---------|-----------|
| **Log Aggregation** | Docker logs (Phase 1) | - | Container log collection | Built-in Docker logging; `docker-compose logs -f taskforce` for streaming |
| **Future Logging** | ELK Stack (Phase 2) | - | Centralized logging (future) | Elasticsearch, Logstash, Kibana in docker-compose when needed |

**6. Development Workflow - ENHANCED FOR DOCKER COMPOSE**

**Add Section: Development Environment Setup**

```bash
# Prerequisites
- Docker 24.0+
- Docker Compose 2.23+
- uv (installed via: pip install uv)

# Initial Setup
cd taskforce
cp .env.example .env  # Configure environment variables

# Start all services (API + PostgreSQL)
docker-compose up -d

# View logs
docker-compose logs -f taskforce

# Run database migrations
docker-compose exec taskforce alembic upgrade head

# Stop services
docker-compose down

# Development with hot-reload
docker-compose up --build  # Rebuild after code changes
```

**7. Database Connection Configuration**

**Update**: Database URL configuration for containerized PostgreSQL

```python
# Development (direct connection)
DATABASE_URL=postgresql+asyncpg://taskforce:taskforce@localhost:5432/taskforce

# Docker Compose (service name as host)
DATABASE_URL=postgresql+asyncpg://taskforce:taskforce@postgres:5432/taskforce

# Production (future K8s)
DATABASE_URL=postgresql+asyncpg://user:pass@db-service:5432/taskforce
```

**8. CI/CD Adjustments**

**Consider**: Docker Compose for CI/CD testing

```yaml
# .github/workflows/ci.yaml or similar
test:
  runs-on: ubuntu-latest
  steps:
    - uses: actions/checkout@v4
    - name: Start services
      run: docker-compose up -d
    - name: Run tests
      run: docker-compose exec -T taskforce pytest
    - name: Cleanup
      run: docker-compose down
```

---

### **Revised Cloud Infrastructure Section**

**Deployment Architecture:**

- **Platform:** Docker Compose (multi-container orchestration)
- **Environment:** Self-hosted (local, staging, production all via docker-compose)
- **Key Services:** 
  - **Taskforce API**: Custom container (`taskforce:latest`)
  - **PostgreSQL**: Official container (`postgres:15-alpine`)
  - **Optional: pgAdmin**: Database admin UI (`dpage/pgadmin4`)
  - **External: Azure AI Search**: SaaS for RAG capabilities (not containerized)
- **Migration Path:** Container-first design ensures Kubernetes compatibility for future scaling needs without architecture changes

---

### **Trade-offs of Docker Compose Approach**

**Advantages:**
✅ **Simplicity**: Single `docker-compose up` command deploys entire stack
✅ **Local Development Parity**: Dev environment identical to staging/production
✅ **Lower Operational Overhead**: No Kubernetes cluster to manage
✅ **Faster Iteration**: Quick rebuild and restart cycles
✅ **Cost Effective**: Run on single VM or bare metal, no orchestration platform costs
✅ **Easier Debugging**: Direct container access, simpler networking

**Limitations:**
⚠️ **No Automatic Scaling**: Manual intervention to add replicas
⚠️ **Single Host**: All containers on one machine (no distributed deployment)
⚠️ **Basic Health Checks**: Docker Compose health checks less sophisticated than K8s probes
⚠️ **Manual Load Balancing**: Need nginx/traefik for multi-replica load balancing
⚠️ **Limited Observability**: No built-in metrics/tracing (need to add manually)

**Mitigation Strategy for Limitations:**
- Design stateless API (enables easy K8s migration later)
- Use container health checks and restart policies
- Implement structured logging (JSON) for future log aggregation
- Document Kubernetes migration path in deployment guide (Story 1.14)

---

### **Updated Technology Stack Table**

| Category | Technology | Version | Purpose | Rationale |
|----------|-----------|---------|---------|-----------|
| **Language** | Python | 3.11+ | Primary development language | Required minimum version for Agent V2 compatibility; excellent async support, type hints, dataclasses |
| **Package Manager** | uv | latest | Dependency management | **HARD CONSTRAINT** from Agent V2; NOT pip/venv; faster than pip, better dependency resolution |
| **Container Platform** | Docker | 24.0+ | Container runtime | Multi-stage builds for optimization; local dev parity; industry standard |
| **Service Orchestration** | Docker Compose | 2.23+ | Multi-container management | Defines service dependencies, networks, volumes; single command deployment |
| **LLM Orchestration** | LiteLLM | 1.7.7.0 | Multi-provider LLM abstraction | Unified interface for OpenAI, Azure OpenAI, Anthropic; proven in Agent V2; parameter mapping for GPT-4/GPT-5 |
| **CLI Framework** | Typer | 0.9.0+ | Command-line interface | Modern CLI with auto-completion, argument validation; integrates with Rich for terminal UI |
| **Terminal UI** | Rich | 13.0.0+ | CLI output formatting | Colored output, progress bars, tables, syntax highlighting; essential for developer experience |
| **Web Framework** | FastAPI | 0.116.1+ | REST API microservice | Async support, auto-generated OpenAPI docs, Pydantic validation, high performance |
| **ASGI Server** | uvicorn | 0.25+ | FastAPI application server | Async request handling; worker management; production-ready |
| **Async I/O** | aiofiles | 23.2.1 | Async file operations | File-based state manager requires async file I/O for performance |
| **Structured Logging** | structlog | 24.2.0 | Application logging | JSON/console logging with context; production observability; correlation IDs |
| **Configuration** | Pydantic | 2.0.0+ | Data validation and settings | Type-safe configuration management; validates YAML profiles at startup |
| **Configuration** | Pydantic Settings | 2.0.0+ | Environment variable management | Environment variable overrides for config; 12-factor app compliance |
| **Database** | PostgreSQL | 15 (alpine) | Production persistence | JSONB support for flexible state storage; strong consistency; containerized deployment |
| **ORM** | SQLAlchemy | 2.0+ | Database abstraction | Async support, robust migrations, flexible querying; industry standard |
| **Migrations** | Alembic | 1.13+ | Database schema management | Version-controlled schema migrations; integrates with SQLAlchemy |
| **Database Driver** | asyncpg | 0.29+ | PostgreSQL async driver | High-performance async PostgreSQL driver for SQLAlchemy |
| **RAG Search** | Azure AI Search SDK | 11.4.0+ | Semantic search and document retrieval | Vector search capabilities; security filtering; proven in Agent V2 RAG agents |
| **HTTP Client** | aiohttp | 3.9+ | Async HTTP requests | Used by web tools (WebSearchTool, WebFetchTool); async-first design |
| **Testing Framework** | pytest | 8.4.2+ | Unit and integration testing | De facto Python testing standard; extensive plugin ecosystem |
| **Async Testing** | pytest-asyncio | 0.23+ | Async test support | Enables testing of async functions and coroutines |
| **Test Coverage** | pytest-cov | 4.1+ | Code coverage reporting | Measures test coverage; enforces ≥90% for core domain |
| **Linting** | Ruff | 0.1.0+ | Fast Python linter | Extremely fast linter; replaces Flake8, isort, pydocstyle; PEP8 enforcement |
| **Formatting** | Black | 23.0+ | Code formatting | Opinionated formatter; zero config; ensures consistent style |
| **Type Checking** | mypy | 1.7+ | Static type analysis | Validates type hints; catches type errors before runtime; protocol compatibility |
| **Log Aggregation** | Docker logs | built-in | Container log collection | Built-in Docker logging; `docker-compose logs` for streaming |
| **YAML Parsing** | PyYAML | 6.0+ | Configuration file parsing | Loads YAML profiles (dev/staging/prod configs) |
| **Future Orchestration** | Kubernetes | 1.28+ | Production scalability (future) | Migration path for horizontal scaling; container-first design ensures compatibility |

---

### **Key Changes Summary**

1. ✅ **Added Docker Compose** as primary orchestration (not Kubernetes)
2. ✅ **PostgreSQL containerized** (`postgres:15-alpine`) not managed service
3. ✅ **Simplified cloud infrastructure** to self-hosted Docker Compose
4. ✅ **Added container-specific technologies** (Docker, Docker Compose)
5. ✅ **Documented Kubernetes as future migration path** (maintains architecture flexibility)
6. ✅ **Updated deployment strategy** throughout document
7. ✅ **Clarified development workflow** for Docker Compose environment


🏗️ **Correcting Data Models - Python Notation**

You're absolutely right! This is a Python backend. Let me revise with proper Python dataclasses and type hints:

---

## Section 4: Data Models (REVISED - Python)

Based on the PRD requirements and ReAct agent architecture, here are the core data models for Taskforce:

---

### **Session**

**Purpose:** Represents a single agent execution session with a specific mission. Sessions track the overall state of mission execution and serve as the primary organizational unit for agent work.

**Key Attributes:**
- `session_id`: str (UUID) - Unique identifier for the session
- `user_id`: Optional[str] - User who initiated the session (for multi-tenant scenarios)
- `mission`: str - The mission description provided by the user
- `status`: str - Current status (pending, in_progress, completed, failed)
- `created_at`: datetime - When the session was created
- `updated_at`: datetime - Last modification timestamp
- `profile`: str - Configuration profile used (dev, staging, prod)

**Python Dataclass:**
```python
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional
from enum import Enum

class SessionStatus(Enum):
    """Session execution status."""
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"

@dataclass
class Session:
    """Agent execution session."""
    session_id: str
    mission: str
    status: SessionStatus
    profile: str = "dev"
    user_id: Optional[str] = None
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)
```

**Relationships:**
- One-to-many with State (session has multiple state snapshots)
- One-to-many with TodoList (session has multiple plans, typically one active)
- One-to-many with ExecutionHistory (session has multiple execution steps)

---

### **State**

**Purpose:** Represents a versioned snapshot of session state at a point in time. Enables state recovery, auditing, and supports optimistic locking for concurrent access.

**Key Attributes:**
- `state_id`: int (auto-increment) - Internal database identifier
- `session_id`: str (FK) - Associated session
- `state_json`: Dict[str, Any] - Complete state data as flexible JSONB
- `version`: int - State version number for optimistic locking
- `timestamp`: datetime - When this state snapshot was created

**Python Dataclass:**
```python
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, Optional

@dataclass
class State:
    """Versioned session state snapshot."""
    session_id: str
    state_json: Dict[str, Any]
    version: int = 1
    state_id: Optional[int] = None  # Assigned by database
    timestamp: datetime = field(default_factory=datetime.utcnow)
    
    # Common state_json structure (not enforced, flexible JSONB):
    # {
    #     "mission": str,
    #     "status": str,
    #     "answers": dict,
    #     "pending_question": Optional[str],
    #     "todolist_id": Optional[str],
    #     "current_step": Optional[int],
    #     ... extensible
    # }
```

**Relationships:**
- Many-to-one with Session (multiple states belong to one session)

---

### **TodoList**

**Purpose:** Represents a generated plan for accomplishing a mission. Contains structured task decomposition with dependencies and acceptance criteria.

**Key Attributes:**
- `todolist_id`: str (UUID) - Unique identifier for the plan
- `session_id`: str (FK) - Associated session
- `mission`: str - Mission this plan addresses
- `items`: List[TodoItem] - List of tasks (stored as JSONB in database)
- `status`: str - Plan status (active, completed, abandoned)
- `created_at`: datetime - When plan was generated
- `updated_at`: datetime - Last modification timestamp

**Python Dataclass:**
```python
from dataclasses import dataclass, field
from datetime import datetime
from typing import List
from enum import Enum

class PlanStatus(Enum):
    """TodoList plan status."""
    ACTIVE = "active"
    COMPLETED = "completed"
    ABANDONED = "abandoned"

@dataclass
class TodoList:
    """Mission execution plan."""
    todolist_id: str
    session_id: str
    mission: str
    items: List['TodoItem']
    status: PlanStatus = PlanStatus.ACTIVE
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)
```

**Relationships:**
- Many-to-one with Session (plan belongs to one session)
- One-to-many with TodoItem (conceptually, stored as JSONB array)

---

### **TodoItem**

**Purpose:** Individual task within a TodoList. Represents a single executable step with clear acceptance criteria and dependency tracking.

**Key Attributes:**
- `position`: int - Ordinal position in the plan (0-indexed)
- `description`: str - Human-readable task description
- `acceptance_criteria`: List[str] - Criteria for task completion
- `dependencies`: List[int] - Positions of tasks this depends on
- `status`: TaskStatus - Task execution status
- `chosen_tool`: Optional[str] - Tool selected for execution
- `execution_result`: Optional[Dict] - Tool execution result details

**Python Dataclass:**
```python
from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any
from enum import Enum

class TaskStatus(Enum):
    """Task execution status."""
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"

@dataclass
class ExecutionResult:
    """Result of tool execution."""
    success: bool
    output: Optional[Any] = None
    error: Optional[str] = None
    duration_ms: Optional[float] = None

@dataclass
class TodoItem:
    """Single task in a TodoList."""
    position: int
    description: str
    acceptance_criteria: List[str]
    dependencies: List[int] = field(default_factory=list)
    status: TaskStatus = TaskStatus.PENDING
    chosen_tool: Optional[str] = None
    execution_result: Optional[ExecutionResult] = None
```

**Relationships:**
- Many-to-one with TodoList (stored as part of plan JSONB)
- Self-referential dependencies (one TodoItem depends on others via position indices)

---

### **ExecutionHistory**

**Purpose:** Detailed step-by-step record of ReAct loop execution. Captures thought (reasoning), action (decision), and observation (result) for each iteration.

**Key Attributes:**
- `history_id`: int (auto-increment) - Internal identifier
- `session_id`: str (FK) - Associated session
- `step_id`: int - Step number in execution sequence
- `thought`: Optional[str] - LLM-generated reasoning/rationale
- `action`: Optional[str] - Action decision (tool name, ask_user, complete)
- `observation`: Optional[str] - Result of action execution
- `timestamp`: datetime - When this step occurred

**Python Dataclass:**
```python
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

@dataclass
class ExecutionHistory:
    """ReAct loop execution step record."""
    session_id: str
    step_id: int
    thought: Optional[str] = None
    action: Optional[str] = None
    observation: Optional[str] = None
    history_id: Optional[int] = None  # Assigned by database
    timestamp: datetime = field(default_factory=datetime.utcnow)
```

**Relationships:**
- Many-to-one with Session (execution steps belong to one session)

---

### **Memory**

**Purpose:** Cross-session learned lessons extracted from successful task executions. Enables agent to learn from experience and improve over time.

**Key Attributes:**
- `memory_id`: str (UUID) - Unique identifier
- `context`: str - Description of situation type (2-3 sentences)
- `what_failed`: Optional[str] - What approach didn't work
- `what_worked`: str - What approach succeeded
- `lesson`: str - Generalizable takeaway for future tasks
- `tool_name`: Optional[str] - Primary tool involved (if relevant)
- `confidence`: float - Confidence score (0.0-1.0)
- `created_at`: datetime - When memory was extracted

**Python Dataclass:**
```python
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

@dataclass
class Memory:
    """Cross-session learned lesson."""
    memory_id: str
    context: str
    what_worked: str
    lesson: str
    confidence: float  # 0.0 to 1.0
    what_failed: Optional[str] = None
    tool_name: Optional[str] = None
    created_at: datetime = field(default_factory=datetime.utcnow)
```

**Relationships:**
- No direct relationships (cross-session knowledge base)
- Queried by tool_name or context similarity for retrieval

---

### **Domain Events (ReAct Loop)**

**Purpose:** Immutable domain events representing key moments in ReAct execution. Used for progress tracking and streaming updates.

**Python Dataclasses:**
```python
from dataclasses import dataclass
from datetime import datetime
from typing import Optional, Any

@dataclass(frozen=True)
class Thought:
    """LLM-generated reasoning event."""
    session_id: str
    step_id: int
    content: str
    timestamp: datetime

@dataclass(frozen=True)
class Action:
    """Action decision event."""
    session_id: str
    step_id: int
    action_type: str  # tool_call, ask_user, complete, replan
    action_data: dict
    timestamp: datetime

@dataclass(frozen=True)
class Observation:
    """Action result event."""
    session_id: str
    step_id: int
    result: Any
    success: bool
    error: Optional[str] = None
    timestamp: datetime
```

---

### **Rationale:**

**Design Decisions:**

1. **Dataclasses over Plain Dicts**: Chose dataclasses for type safety and IDE support. Rationale: Modern Python (3.11) makes dataclasses zero-overhead. Better than plain dicts for catching errors early.

2. **Enums for Status Fields**: Used Enum classes for status values rather than strings. Rationale: Type-safe, prevents typos, enables exhaustive checking in match statements.

3. **JSONB for Flexibility**: State and TodoList stored as JSONB in PostgreSQL, deserialized to dataclasses. Rationale: Schema evolution without migrations. Preserves Agent V2 JSON format compatibility.

4. **Immutable Domain Events**: Domain events (Thought, Action, Observation) are frozen dataclasses. Rationale: Immutability prevents accidental modification of execution history. Enables event replay for debugging.

5. **Optional Fields with Defaults**: Used Optional + default None for fields not always present. Rationale: Explicit about what's required vs. optional. Better than relying on database NULL semantics.

6. **Separate ExecutionResult Dataclass**: Extracted execution result into own dataclass rather than plain dict. Rationale: Reusable across different tool implementations. Type-safe result handling.

**Trade-offs:**

- **Dataclasses vs Pydantic Models**: Chose dataclasses over Pydantic. Trade-off: Less validation power (Pydantic better), but lighter weight and standard library. Can add Pydantic for API layer validation if needed.

- **JSONB Flexibility vs Schema Enforcement**: JSONB allows schema changes without migrations but loses database-level validation. Trade-off: Flexibility vs. safety. Mitigated by dataclass validation in application code.

**Key Assumptions:**

- Python dataclasses sufficient for domain modeling (validated: they are)
- JSONB performance acceptable for state/plan sizes (typical: <1MB) (needs validation in load testing)
- Enum overhead acceptable (validated: zero runtime cost)

---

**Advanced Elicitation Options**

Data models now using Python dataclasses. Please review:

**0.** Tree of Thoughts - Explore alternative modeling approaches (Pydantic, attrs, plain classes)
**1.** **Proceed to next section**
**2.** Critique and Refine - Challenge data model design choices
**3.** Identify Potential Risks - JSONB flexibility risks, versioning concerns
**4.** Assess Alignment with Goals - Verify models support all PRD requirements
**5.** Stakeholder Roundtable - Dev, DBA perspectives on data models
**6.** Red Team vs Blue Team - Attack dataclass choice, defend simplicity
**7.** Hindsight Reflection - 6 months in: were these the right modeling choices?
**8.** Meta-Prompting - Generate questions about specific model attributes

**Select 0-9 or just type your question/feedback:**


🏗️ **Proceeding to Components...**

---

## Section 5: Components

Based on the Clean Architecture patterns, tech stack, and data models, here are the major components of Taskforce organized by layer:

---

### **Core Layer Components**

#### **Agent (Core Domain)**

**Responsibility:** Implements the ReAct (Reason + Act) execution loop. Pure business logic orchestrating thought generation, action decisions, and observation recording. Zero infrastructure dependencies.

**Key Interfaces:**
- `execute(mission: str, session_id: str) -> ExecutionResult` - Main execution entry point
- `_generate_thought() -> str` - LLM-based reasoning step
- `_decide_action(thought: str) -> Action` - Action selection logic
- `_execute_action(action: Action) -> Observation` - Delegates to tool execution
- `_should_continue() -> bool` - Loop termination conditions

**Dependencies:**
- `StateManagerProtocol` (injected) - For state persistence
- `LLMProviderProtocol` (injected) - For thought generation
- `Dict[str, ToolProtocol]` (injected) - For tool execution
- `TodoListManagerProtocol` (injected) - For plan management

**Technology Stack:** Pure Python 3.11, dataclasses, asyncio

**Code Location:** `taskforce/src/taskforce/core/domain/agent.py`

---

#### **PlanGenerator (Core Domain)**

**Responsibility:** Generates TodoList plans from mission descriptions using LLM-based decomposition. Validates task dependencies and ensures plan coherence.

**Key Interfaces:**
- `generate_plan(mission: str) -> TodoList` - Creates structured plan from mission text
- `validate_dependencies(plan: TodoList) -> bool` - Ensures no circular dependencies
- `update_task_status(item: TodoItem, status: TaskStatus) -> None` - Updates task execution state

**Dependencies:**
- `LLMProviderProtocol` (injected) - For plan generation prompts

**Technology Stack:** Pure Python 3.11, dataclasses for TodoList/TodoItem

**Code Location:** `taskforce/src/taskforce/core/domain/plan.py`

---

#### **Domain Events (Core Domain)**

**Responsibility:** Immutable event objects representing key moments in agent execution. Enable event-driven architecture and progress tracking.

**Key Interfaces:**
- `Thought(session_id, step_id, content, timestamp)` - Reasoning event
- `Action(session_id, step_id, action_type, action_data, timestamp)` - Decision event  
- `Observation(session_id, step_id, result, success, error, timestamp)` - Result event

**Dependencies:** None (pure dataclasses)

**Technology Stack:** Python dataclasses (frozen=True for immutability)

**Code Location:** `taskforce/src/taskforce/core/domain/events.py`

---

### **Core Interface Components (Protocols)**

#### **StateManagerProtocol**

**Responsibility:** Defines contract for session state persistence. Enables swappable file-based and database-backed implementations.

**Key Interfaces:**
```python
async def save_state(session_id: str, state_data: Dict[str, Any]) -> None
async def load_state(session_id: str) -> Optional[Dict[str, Any]]
async def delete_state(session_id: str) -> None
async def list_sessions() -> List[str]
```

**Dependencies:** None (protocol definition)

**Technology Stack:** Python Protocol (PEP 544)

**Code Location:** `taskforce/src/taskforce/core/interfaces/state.py`

---

#### **LLMProviderProtocol**

**Responsibility:** Defines contract for LLM completions. Abstracts OpenAI, Azure OpenAI, and future providers.

**Key Interfaces:**
```python
async def complete(model: str, messages: List[Dict], **params) -> Dict[str, Any]
async def generate(model: str, prompt: str, **params) -> str
```

**Dependencies:** None (protocol definition)

**Technology Stack:** Python Protocol (PEP 544)

**Code Location:** `taskforce/src/taskforce/core/interfaces/llm.py`

---

#### **ToolProtocol**

**Responsibility:** Defines contract for tool execution. All tools (Python, File, Git, Web, RAG) implement this interface.

**Key Interfaces:**
```python
@property
def name() -> str

@property  
def description() -> str

@property
def parameters_schema() -> Dict[str, Any]

async def execute(**params) -> Dict[str, Any]
def validate_parameters(params: Dict[str, Any]) -> bool
```

**Dependencies:** None (protocol definition)

**Technology Stack:** Python Protocol (PEP 544)

**Code Location:** `taskforce/src/taskforce/core/interfaces/tools.py`

---

### **Infrastructure Layer Components**

#### **FileStateManager**

**Responsibility:** File-based state persistence for development. Stores session state as JSON files with async I/O and versioning.

**Key Interfaces:** Implements `StateManagerProtocol`

**Dependencies:**
- `aiofiles` - Async file operations
- File system at `{work_dir}/states/{session_id}.json`

**Technology Stack:** Python 3.11, aiofiles, asyncio, JSON serialization

**Code Location:** `taskforce/src/taskforce/infrastructure/persistence/file_state.py`

---

#### **DbStateManager**

**Responsibility:** PostgreSQL-based state persistence for production. Stores state in relational tables with JSONB columns.

**Key Interfaces:** Implements `StateManagerProtocol`

**Dependencies:**
- `asyncpg` - Async PostgreSQL driver
- `SQLAlchemy 2.0` - ORM and query builder
- PostgreSQL database connection

**Technology Stack:** Python 3.11, SQLAlchemy async, asyncpg, PostgreSQL 15

**Code Location:** `taskforce/src/taskforce/infrastructure/persistence/db_state.py`

---

#### **OpenAIService (LLM Service)**

**Responsibility:** LLM service supporting OpenAI and Azure OpenAI via LiteLLM. Handles model aliases, parameter mapping (GPT-4 vs GPT-5), retry logic, token logging.

**Key Interfaces:** Implements `LLMProviderProtocol`

**Dependencies:**
- `litellm` - Multi-provider LLM client
- `llm_config.yaml` - Model configuration
- Environment variables: `OPENAI_API_KEY`, `AZURE_OPENAI_API_KEY`

**Technology Stack:** Python 3.11, LiteLLM 1.7.7.0, async/await

**Code Location:** `taskforce/src/taskforce/infrastructure/llm/openai_service.py`

---

#### **Native Tools (Infrastructure)**

**Responsibility:** Core tool implementations relocated from Agent V2. Each tool implements `ToolProtocol` with preserved execution semantics.

**Key Interfaces:**
- **PythonTool**: Executes Python code in isolated namespace
- **FileReadTool / FileWriteTool**: File system operations
- **GitTool / GitHubTool**: Git operations and GitHub API
- **PowerShellTool**: Shell command execution (Windows-first)
- **WebSearchTool / WebFetchTool**: HTTP requests and web scraping
- **LLMTool**: Nested LLM calls for sub-tasks
- **AskUserTool**: User interaction via CLI or API

**Dependencies:**
- Various: subprocess, aiohttp, GitPython, etc. (tool-specific)

**Technology Stack:** Python 3.11, async/await, tool-specific libraries

**Code Location:** `taskforce/src/taskforce/infrastructure/tools/native/*.py`

---

#### **RAG Tools (Infrastructure)**

**Responsibility:** Azure AI Search integration for semantic search and document retrieval. Supports RAG agent capabilities.

**Key Interfaces:**
- **SemanticSearchTool**: Vector search in Azure AI Search index
- **ListDocumentsTool**: Document listing with metadata
- **GetDocumentTool**: Document retrieval by ID

**Dependencies:**
- `azure-search-documents` SDK - Azure AI Search client
- Azure AI Search index (external service)
- Environment variables: `AZURE_SEARCH_ENDPOINT`, `AZURE_SEARCH_API_KEY`

**Technology Stack:** Python 3.11, Azure AI Search SDK 11.4+, async/await

**Code Location:** `taskforce/src/taskforce/infrastructure/tools/rag/*.py`

---

### **Application Layer Components**

#### **AgentFactory**

**Responsibility:** Dependency injection container. Reads configuration profiles (dev/staging/prod) and wires domain objects with appropriate infrastructure adapters.

**Key Interfaces:**
- `create_agent(profile: str = "dev") -> Agent` - Creates generic agent
- `create_rag_agent(profile: str = "dev") -> Agent` - Creates RAG-enabled agent
- `_create_state_manager(config: dict) -> StateManagerProtocol` - Instantiates persistence adapter
- `_create_llm_provider(config: dict) -> LLMProviderProtocol` - Instantiates LLM service
- `_create_tools(config: dict) -> List[ToolProtocol]` - Instantiates tool implementations

**Dependencies:**
- All infrastructure adapters (FileStateManager, DbStateManager, OpenAIService, Tools)
- Core domain classes (Agent, PlanGenerator)
- YAML configuration files

**Technology Stack:** Python 3.11, PyYAML, dataclasses

**Code Location:** `taskforce/src/taskforce/application/factory.py`

---

#### **AgentExecutor**

**Responsibility:** Service orchestrating agent execution. Shared logic for CLI and API entrypoints. Handles logging, error handling, state persistence, progress callbacks.

**Key Interfaces:**
- `execute_mission(mission: str, profile: str, session_id: Optional[str]) -> ExecutionResult` - Synchronous execution
- `execute_mission_streaming(mission: str, profile: str) -> AsyncIterator[ProgressUpdate]` - Streaming execution with progress events

**Dependencies:**
- `AgentFactory` - For agent creation
- Core domain `Agent` - For ReAct loop execution
- `structlog` - For structured logging

**Technology Stack:** Python 3.11, structlog, asyncio, async generators

**Code Location:** `taskforce/src/taskforce/application/executor.py`

---

#### **ProfileLoader**

**Responsibility:** Loads and validates YAML configuration profiles. Manages environment variable overrides.

**Key Interfaces:**
- `load_profile(profile_name: str) -> dict` - Loads configuration from YAML
- `validate_profile(config: dict) -> None` - Validates required fields
- `merge_env_overrides(config: dict) -> dict` - Applies environment variable overrides

**Dependencies:**
- `PyYAML` - YAML parsing
- `Pydantic` - Configuration validation
- Configuration files: `configs/dev.yaml`, `configs/staging.yaml`, `configs/prod.yaml`

**Technology Stack:** Python 3.11, PyYAML, Pydantic

**Code Location:** `taskforce/src/taskforce/application/profiles.py`

---

### **API Layer Components**

#### **FastAPI REST Service**

**Responsibility:** HTTP REST API for programmatic access. Exposes agent execution, session management, health checks.

**Key Interfaces:**
- `POST /api/v1/execute` - Execute mission synchronously
- `POST /api/v1/execute/stream` - Execute mission with streaming (SSE)
- `GET /api/v1/sessions` - List sessions
- `GET /api/v1/sessions/{session_id}` - Get session details
- `POST /api/v1/sessions` - Create session
- `GET /health` - Liveness probe
- `GET /health/ready` - Readiness probe (checks DB connectivity)

**Dependencies:**
- `AgentExecutor` - For mission execution
- `AgentFactory` - For session state access
- `Pydantic` - Request/response validation

**Technology Stack:** FastAPI 0.116+, uvicorn 0.25+, Pydantic 2.0+

**Code Location:** `taskforce/src/taskforce/api/server.py`, `taskforce/src/taskforce/api/routes/*.py`

---

#### **Typer CLI**

**Responsibility:** Command-line interface for developers. Adapted from Agent V2 CLI structure with Rich terminal output.

**Key Interfaces:**
- `taskforce run mission <description>` - Execute mission
- `taskforce chat` - Interactive chat mode
- `taskforce tools list` - List available tools
- `taskforce tools inspect <tool-name>` - Show tool details
- `taskforce sessions list` - List sessions
- `taskforce sessions show <session-id>` - Show session details
- `taskforce config show` - Show configuration

**Dependencies:**
- `AgentExecutor` - For mission execution
- `AgentFactory` - For agent creation
- `Typer` - CLI framework
- `Rich` - Terminal UI (progress bars, tables, colors)

**Technology Stack:** Typer 0.9+, Rich 13.0+, asyncio

**Code Location:** `taskforce/src/taskforce/api/cli/main.py`, `taskforce/src/taskforce/api/cli/commands/*.py`

---

### **Component Diagram**

```mermaid
C4Component
    title Taskforce Component Architecture (Clean Architecture Layers)
    
    Container_Boundary(api, "API Layer") {
        Component(cli, "Typer CLI", "Python, Typer, Rich", "Command-line interface")
        Component(rest, "FastAPI REST", "Python, FastAPI", "HTTP API endpoints")
    }
    
    Container_Boundary(app, "Application Layer") {
        Component(executor, "AgentExecutor", "Python", "Orchestrates execution")
        Component(factory, "AgentFactory", "Python", "Dependency injection")
        Component(profiles, "ProfileLoader", "Python, PyYAML", "Config management")
    }
    
    Container_Boundary(core, "Core Layer") {
        Component(agent, "Agent", "Python, Pure Logic", "ReAct loop execution")
        Component(planner, "PlanGenerator", "Python, Pure Logic", "TodoList planning")
        Component(events, "Domain Events", "Python, Dataclasses", "Thought/Action/Observation")
    }
    
    Container_Boundary(protocols, "Core Interfaces") {
        Component(state_proto, "StateManagerProtocol", "Python Protocol", "State persistence contract")
        Component(llm_proto, "LLMProviderProtocol", "Python Protocol", "LLM provider contract")
        Component(tool_proto, "ToolProtocol", "Python Protocol", "Tool execution contract")
    }
    
    Container_Boundary(infra, "Infrastructure Layer") {
        Component(file_state, "FileStateManager", "Python, aiofiles", "File-based persistence")
        Component(db_state, "DbStateManager", "Python, SQLAlchemy", "Database persistence")
        Component(llm_svc, "OpenAIService", "Python, LiteLLM", "LLM integration")
        Component(tools, "Native Tools", "Python", "11+ tool implementations")
        Component(rag_tools, "RAG Tools", "Python, Azure SDK", "Semantic search tools")
    }
    
    Container_Boundary(external, "External Systems") {
        ComponentDb(postgres, "PostgreSQL", "Database", "Production state storage")
        Component(openai, "OpenAI API", "External", "LLM provider")
        Component(azure_search, "Azure AI Search", "External", "Vector search")
    }
    
    Rel(cli, executor, "Uses")
    Rel(rest, executor, "Uses")
    
    Rel(executor, factory, "Creates agents via")
    Rel(factory, profiles, "Loads config from")
    
    Rel(factory, agent, "Instantiates")
    Rel(factory, planner, "Instantiates")
    
    Rel(agent, state_proto, "Depends on")
    Rel(agent, llm_proto, "Depends on")
    Rel(agent, tool_proto, "Depends on")
    Rel(planner, llm_proto, "Depends on")
    
    Rel(state_proto, file_state, "Implemented by", "dev profile")
    Rel(state_proto, db_state, "Implemented by", "prod profile")
    Rel(llm_proto, llm_svc, "Implemented by")
    Rel(tool_proto, tools, "Implemented by")
    Rel(tool_proto, rag_tools, "Implemented by")
    
    Rel(file_state, "File System", "Writes to")
    Rel(db_state, postgres, "Writes to")
    Rel(llm_svc, openai, "Calls")
    Rel(rag_tools, azure_search, "Queries")
```

---

### **Rationale:**

**Component Organization Decisions:**

1. **Strict Layer Separation**: Components organized by layer (Core, Infrastructure, Application, API) with explicit dependency direction (inward). Rationale: Enforces Clean Architecture dependency rule - domain logic never depends on infrastructure.

2. **Protocol Layer as Boundary**: Separate protocol components defining all layer boundaries. Rationale: Makes dependencies explicit. Core depends on abstractions (protocols), not concrete implementations.

3. **Dual Entrypoints (CLI + API)**: Both share AgentExecutor service. Rationale: Single source of truth for execution logic. CLI and API are thin wrappers providing different interfaces to same functionality.

4. **AgentFactory as Wiring Hub**: Centralized dependency injection. Rationale: Makes dependency graph explicit and configurable. Single place to change infrastructure implementations.

5. **Tool Implementations in Infrastructure**: All 11+ tools in infrastructure layer, not core. Rationale: Tools perform I/O (subprocess, HTTP, file system). Core domain only knows ToolProtocol interface.

**Trade-offs:**

- **Many Small Components vs Few Large**: Chose many focused components over monolithic services. Trade-off: More files to navigate vs. clearer responsibilities.
- **Shared Executor vs Separate Services**: CLI and API share executor. Trade-off: Tight coupling between entrypoints vs. guaranteed behavioral consistency.
- **Protocol Overhead**: Every infrastructure component implements a protocol. Trade-off: More interface code vs. testability and flexibility.

🏗️ **Proceeding to External APIs...**

---

## Section 6: External APIs

Taskforce integrates with several external APIs for LLM capabilities and RAG functionality:

---

### **OpenAI API**

- **Purpose:** Primary LLM provider for thought generation, plan generation, and tool reasoning in the ReAct loop
- **Documentation:** https://platform.openai.com/docs/api-reference
- **Base URL(s):** 
  - Production: `https://api.openai.com/v1`
  - Versioned: `https://api.openai.com/v1` (versioning via model names)
- **Authentication:** Bearer token authentication via `Authorization: Bearer $OPENAI_API_KEY` header
- **Rate Limits:** 
  - GPT-4: 10,000 TPM (tokens per minute), 500 RPM (requests per minute) - varies by tier
  - GPT-4-mini: 200,000 TPM, 5,000 RPM
  - Monitor via `x-ratelimit-*` response headers

**Key Endpoints Used:**
- `POST /chat/completions` - Chat completion for ReAct thought generation and planning
- `POST /completions` (legacy) - Text completion (if needed for specific use cases)

**Integration Notes:**
- Integrated via **LiteLLM library** - not direct OpenAI SDK calls
- LiteLLM provides unified interface across providers (OpenAI, Azure, Anthropic)
- Automatic retry with exponential backoff on rate limits (429) and server errors (5xx)
- Token usage logged via structlog for cost tracking
- Parameter mapping for GPT-5 models (temperature → effort, top_p → reasoning)
- Model aliases configured in `llm_config.yaml`: main, fast, powerful, legacy
- Environment variable: `OPENAI_API_KEY` (required for OpenAI provider)

---

### **Azure OpenAI API**

- **Purpose:** Enterprise LLM provider alternative for organizations requiring Azure-hosted models (data residency, compliance, private networking)
- **Documentation:** https://learn.microsoft.com/en-us/azure/ai-services/openai/reference
- **Base URL(s):** 
  - Configured per deployment: `https://{resource-name}.openai.azure.com/`
  - API Version: `2024-02-15-preview` (configurable)
- **Authentication:** 
  - API Key: `api-key: $AZURE_OPENAI_API_KEY` header
  - Alternative: Azure AD OAuth tokens (future enhancement)
- **Rate Limits:** 
  - Configured per deployment in Azure portal
  - Typically: 240,000 TPM for GPT-4 deployments
  - Monitor via Azure metrics

**Key Endpoints Used:**
- `POST /openai/deployments/{deployment-id}/chat/completions?api-version={version}` - Chat completion

**Integration Notes:**
- Integrated via **LiteLLM library** with Azure provider configuration
- Deployment names mapped to model aliases in `llm_config.yaml`:
  ```yaml
  azure:
    enabled: true
    deployment_mapping:
      main: "gpt-4-deployment-prod"
      fast: "gpt-4-mini-deployment-prod"
  ```
- Environment variables: 
  - `AZURE_OPENAI_API_KEY` (required if Azure enabled)
  - `AZURE_OPENAI_ENDPOINT` (required if Azure enabled)
- Same parameter mapping and retry logic as OpenAI
- Optional: Private endpoint support via Azure VNet integration

---

### **Azure AI Search API**

- **Purpose:** Semantic search and document retrieval for RAG (Retrieval Augmented Generation) agent capabilities. Enables vector search over document corpus.
- **Documentation:** https://learn.microsoft.com/en-us/rest/api/searchservice/
- **Base URL(s):** 
  - Configured per search service: `https://{search-service-name}.search.windows.net/`
  - API Version: `2023-11-01` (stable)
- **Authentication:** 
  - Admin Key: `api-key: $AZURE_SEARCH_API_KEY` header (for indexing)
  - Query Key: `api-key: $AZURE_SEARCH_QUERY_KEY` header (for search only)
- **Rate Limits:** 
  - Depends on service tier (Basic, Standard, etc.)
  - Standard: 200 queries/second, 3 indexing requests/second
  - Monitor via Azure portal metrics

**Key Endpoints Used:**
- `POST /indexes/{index-name}/docs/search?api-version={version}` - Semantic vector search
- `GET /indexes/{index-name}/docs/{doc-id}?api-version={version}` - Document retrieval by ID
- `GET /indexes/{index-name}/docs?api-version={version}` - List documents with filtering

**Integration Notes:**
- Integrated via **Azure Search SDK** (`azure-search-documents` package)
- RAG tools (SemanticSearchTool, ListDocumentsTool, GetDocumentTool) in `infrastructure/tools/rag/`
- Shared Azure Search client in `azure_search_base.py`
- Security filtering support (user_id, org_id, scope fields)
- Vector search configuration:
  - Embedding model: Configurable (typically text-embedding-ada-002 or similar)
  - Vector dimensions: 1536 (for ada-002) or model-specific
  - Similarity metric: Cosine similarity
- Environment variables:
  - `AZURE_SEARCH_ENDPOINT` (required for RAG features)
  - `AZURE_SEARCH_API_KEY` (required for RAG features)
  - `AZURE_SEARCH_INDEX_NAME` (default: "documents")
- Optional feature: RAG capabilities disabled if environment variables not set

---

### **GitHub API (Optional)**

- **Purpose:** Git repository operations for GitHubTool (create repos, manage issues, PRs, etc.)
- **Documentation:** https://docs.github.com/en/rest
- **Base URL(s):** 
  - REST API: `https://api.github.com`
  - GraphQL API: `https://api.github.com/graphql` (future enhancement)
- **Authentication:** 
  - Personal Access Token: `Authorization: Bearer $GITHUB_TOKEN` header
  - OAuth tokens (future enhancement)
- **Rate Limits:** 
  - Authenticated: 5,000 requests/hour
  - Unauthenticated: 60 requests/hour
  - GraphQL: 5,000 points/hour (different counting)

**Key Endpoints Used:**
- `POST /user/repos` - Create repository
- `GET /repos/{owner}/{repo}` - Get repository details
- `POST /repos/{owner}/{repo}/issues` - Create issue
- `GET /repos/{owner}/{repo}/contents/{path}` - Read file contents

**Integration Notes:**
- Integrated via **PyGithub library** (optional dependency)
- Used by GitHubTool in `infrastructure/tools/native/git_tools.py`
- Environment variable: `GITHUB_TOKEN` (optional, tool gracefully degrades without it)
- Fallback to local git operations if GitHub API unavailable

---

### **External API Error Handling Strategy**

**Common Error Patterns:**

1. **Rate Limiting (429 responses)**
   - Strategy: Exponential backoff retry (1s, 2s, 4s, 8s)
   - Max retries: 3 attempts
   - Respect `Retry-After` header if present
   - Log rate limit events for monitoring

2. **Server Errors (5xx responses)**
   - Strategy: Retry with exponential backoff
   - Max retries: 3 attempts
   - Circuit breaker pattern after 5 consecutive failures (future enhancement)

3. **Authentication Errors (401, 403)**
   - Strategy: No retry (configuration error)
   - Log error with clear message about missing/invalid API keys
   - Graceful degradation (disable features requiring that API)

4. **Network Timeouts**
   - Default timeout: 30 seconds for LLM calls, 10 seconds for other APIs
   - Retry on connection timeout (max 2 retries)
   - Log timeout events for monitoring

5. **Invalid Requests (4xx except 429)**
   - Strategy: No retry (client error)
   - Log full request/response for debugging
   - Return actionable error message to user

**Retry Configuration:**
```python
# Example from llm_config.yaml
retry:
  max_attempts: 3
  backoff_multiplier: 2
  initial_delay_ms: 1000
  max_delay_ms: 10000
  retry_on_errors:
    - "RateLimitError"
    - "ServiceUnavailableError"
    - "InternalServerError"
```

---

### **API Cost Monitoring**

**Token Usage Tracking (LLM APIs):**
- Log every LLM call with token counts:
  ```python
  logger.info(
      "llm.completion",
      model=model_name,
      prompt_tokens=usage.prompt_tokens,
      completion_tokens=usage.completion_tokens,
      total_tokens=usage.total_tokens,
      cost_estimate_usd=calculate_cost(model, usage)
  )
  ```
- Daily/monthly cost aggregation via log analysis
- Budget alerts (future enhancement)

**Azure AI Search Usage:**
- Query count logging for capacity planning
- Index size monitoring
- Storage cost tracking (documents stored)

---

### **Rationale:**

**API Integration Decisions:**

1. **LiteLLM Abstraction**: Chose LiteLLM over direct OpenAI SDK. Rationale: Multi-provider support (OpenAI + Azure + Anthropic) through single interface. Reduces vendor lock-in. Trade-off: Additional dependency vs. flexibility.

2. **Azure AI Search SDK**: Chose official SDK over REST API calls. Rationale: Type-safe, handles authentication/retry automatically, better error messages. Trade-off: Heavier dependency vs. developer experience.

3. **Optional GitHub Integration**: Made GitHub API optional (tool degrades gracefully). Rationale: Not all deployments need GitHub access. Reduces mandatory dependencies. Trade-off: More complex conditional logic vs. deployment flexibility.

4. **Aggressive Retry Strategy**: Max 3 retries with exponential backoff. Rationale: LLM APIs occasionally unstable, retries improve reliability. Trade-off: Slower failures vs. success rate.

**Key Assumptions:**
- OpenAI API stability sufficient for production use (needs validation with historical uptime data)
- Azure AI Search latency acceptable for RAG queries (<500ms p95) (needs validation via load testing)
- Token costs within budget (needs validation with usage projections)

**Security Considerations:**
- All API keys via environment variables (never hardcoded)
- No API keys logged (filtered from structured logs)
- HTTPS enforced for all external API calls
- Timeout limits prevent hung connections

---

🏗️ **Proceeding to Core Workflows...**

---

## Section 7: Core Workflows

Key system workflows illustrating component interactions and data flow:

---

### **Workflow 1: Mission Execution via CLI (ReAct Loop)**

This workflow shows a complete mission execution from CLI command to completion, illustrating the ReAct (Reason + Act) loop.

```mermaid
sequenceDiagram
    actor User
    participant CLI as Typer CLI
    participant Executor as AgentExecutor
    participant Factory as AgentFactory
    participant Agent as Agent (Core)
    participant LLM as OpenAIService
    participant Tool as PythonTool
    participant State as FileStateManager
    
    User->>CLI: taskforce run mission "Create hello world"
    CLI->>Executor: execute_mission(mission, profile="dev")
    
    Executor->>Factory: create_agent(profile="dev")
    Factory->>State: new FileStateManager()
    Factory->>LLM: new OpenAIService()
    Factory->>Tool: new PythonTool()
    Factory->>Agent: new Agent(state, llm, [tools])
    Factory-->>Executor: agent
    
    Executor->>Agent: execute(mission, session_id)
    
    Note over Agent: ReAct Loop Iteration 1
    Agent->>State: load_state(session_id)
    State-->>Agent: None (new session)
    
    Agent->>LLM: complete("Generate thought for mission")
    LLM->>OpenAI API: POST /chat/completions
    OpenAI API-->>LLM: "I need to create a Python function..."
    LLM-->>Agent: Thought
    
    Agent->>Agent: decide_action(thought)
    Note over Agent: Decides to use PythonTool
    
    Agent->>Tool: execute(code="def hello(): print('Hello World')")
    Tool-->>Agent: Observation(success=true, output="Function created")
    
    Agent->>State: save_state(session_id, state_data)
    State-->>Agent: saved
    
    Note over Agent: ReAct Loop Iteration 2
    Agent->>LLM: complete("Evaluate if mission complete")
    LLM->>OpenAI API: POST /chat/completions
    OpenAI API-->>LLM: "Mission accomplished"
    LLM-->>Agent: Thought
    
    Agent->>Agent: decide_action(thought)
    Note over Agent: Decides to complete
    
    Agent-->>Executor: ExecutionResult(status="completed")
    Executor-->>CLI: result
    CLI-->>User: ✓ Mission completed!
```

---

### **Workflow 2: TodoList Plan Generation**

This workflow shows how a mission is decomposed into a structured TodoList with dependencies.

```mermaid
sequenceDiagram
    participant Agent as Agent (Core)
    participant Planner as PlanGenerator
    participant LLM as OpenAIService
    participant TodoMgr as FileTodoListManager
    participant State as FileStateManager
    
    Agent->>Planner: generate_plan(mission)
    
    Planner->>LLM: complete(prompt="Decompose mission into steps")
    Note over LLM: Uses planning system prompt<br/>with examples
    LLM->>OpenAI API: POST /chat/completions
    OpenAI API-->>LLM: JSON plan structure
    LLM-->>Planner: plan_json
    
    Planner->>Planner: parse_plan_json()
    Note over Planner: Creates TodoItem objects
    
    Planner->>Planner: validate_dependencies()
    alt Circular dependencies detected
        Planner-->>Agent: Error: Circular dependency
    else Valid plan
        Planner->>TodoMgr: save_plan(todolist)
        TodoMgr->>State: save to file system
        State-->>TodoMgr: saved
        TodoMgr-->>Planner: todolist_id
        Planner-->>Agent: TodoList(items, todolist_id)
    end
    
    Agent->>Agent: Set current_step = 0
    Note over Agent: Ready to execute first task
```

---

### **Workflow 3: Tool Execution with Retry and Error Handling**

This workflow shows the tool execution pattern with retry logic and error recovery.

```mermaid
sequenceDiagram
    participant Agent as Agent (Core)
    participant Tool as GitTool
    participant Subprocess as subprocess
    participant Logger as structlog
    
    Agent->>Tool: execute(repo_path="/path", command="clone")
    
    Tool->>Tool: validate_parameters(params)
    alt Invalid parameters
        Tool-->>Agent: Error: Missing required param
    end
    
    Tool->>Logger: log("tool.execution.started", tool="git")
    
    loop Retry up to 3 times
        Tool->>Subprocess: run(["git", "clone", "..."])
        
        alt Success
            Subprocess-->>Tool: returncode=0, stdout="Cloning..."
            Tool->>Logger: log("tool.execution.success")
            Tool-->>Agent: {success: true, output: "..."}
        else Transient Error (network timeout)
            Subprocess-->>Tool: Exception: TimeoutError
            Tool->>Logger: log("tool.execution.retry", attempt=N)
            Note over Tool: Exponential backoff: 1s, 2s, 4s
        else Permanent Error (invalid repo)
            Subprocess-->>Tool: returncode=128, stderr="not found"
            Tool->>Logger: log("tool.execution.failed")
            Tool-->>Agent: {success: false, error: "..."}
        end
    end
    
    alt Max retries exceeded
        Tool->>Logger: log("tool.execution.failed", reason="max_retries")
        Tool-->>Agent: {success: false, error: "Max retries"}
    end
```

---

### **Workflow 4: State Persistence and Recovery (Database)**

This workflow shows database-backed state persistence with versioning and concurrent access handling.

```mermaid
sequenceDiagram
    participant Agent1 as Agent Instance 1
    participant Agent2 as Agent Instance 2
    participant DbState as DbStateManager
    participant SQLAlchemy as SQLAlchemy ORM
    participant Postgres as PostgreSQL
    
    Note over Agent1,Agent2: Concurrent execution scenario
    
    Agent1->>DbState: save_state(session_id, state_data)
    DbState->>SQLAlchemy: query(Session).filter_by(session_id)
    SQLAlchemy->>Postgres: SELECT * FROM sessions WHERE session_id=?
    Postgres-->>SQLAlchemy: session (version=1)
    
    DbState->>SQLAlchemy: insert(State, state_json, version=2)
    SQLAlchemy->>Postgres: INSERT INTO states (session_id, state_json, version=2)
    Postgres-->>SQLAlchemy: OK
    
    DbState->>SQLAlchemy: update(Session, updated_at, version=2)
    SQLAlchemy->>Postgres: UPDATE sessions SET version=2, updated_at=NOW()
    Postgres-->>SQLAlchemy: OK
    SQLAlchemy-->>DbState: committed
    DbState-->>Agent1: saved (version=2)
    
    Note over Agent2: Attempting to save with stale version
    Agent2->>DbState: save_state(session_id, state_data, version=1)
    DbState->>SQLAlchemy: update(Session) WHERE version=1
    SQLAlchemy->>Postgres: UPDATE sessions SET version=2 WHERE version=1
    Postgres-->>SQLAlchemy: 0 rows affected (conflict!)
    
    alt Optimistic lock conflict
        DbState-->>Agent2: Error: State modified by another instance
        Agent2->>DbState: load_state(session_id)
        DbState->>Postgres: SELECT latest state
        Postgres-->>DbState: state (version=2)
        DbState-->>Agent2: current_state
        Note over Agent2: Retry with updated state
    end
```

---

### **Workflow 5: FastAPI REST API Execution with Streaming**

This workflow shows mission execution via REST API with Server-Sent Events for progress updates.

```mermaid
sequenceDiagram
    actor Client
    participant API as FastAPI
    participant Route as ExecutionRoute
    participant Executor as AgentExecutor
    participant Agent as Agent (Core)
    
    Client->>API: POST /api/v1/execute/stream
    Note over Client: {"mission": "...", "profile": "prod"}
    
    API->>Route: execute_mission_stream(request)
    Route->>Executor: execute_mission_streaming(mission, profile)
    
    Note over Executor: Returns AsyncIterator[ProgressUpdate]
    
    loop ReAct Loop Iterations
        Executor->>Agent: execute (step by step)
        
        Agent-->>Executor: ProgressUpdate(event="thought")
        Executor-->>Route: yield ProgressUpdate
        Route-->>API: SSE: data: {"event":"thought", ...}
        API-->>Client: Server-Sent Event
        
        Agent-->>Executor: ProgressUpdate(event="action")
        Executor-->>Route: yield ProgressUpdate
        Route-->>API: SSE: data: {"event":"action", ...}
        API-->>Client: Server-Sent Event
        
        Agent-->>Executor: ProgressUpdate(event="observation")
        Executor-->>Route: yield ProgressUpdate
        Route-->>API: SSE: data: {"event":"observation", ...}
        API-->>Client: Server-Sent Event
    end
    
    Agent-->>Executor: ProgressUpdate(event="complete")
    Executor-->>Route: yield ProgressUpdate
    Route-->>API: SSE: data: {"event":"complete", ...}
    API-->>Client: Server-Sent Event
    
    API->>Client: Connection closed
```

---

### **Workflow 6: Configuration Profile Loading and Adapter Selection**

This workflow shows how configuration profiles determine which infrastructure adapters are used.

```mermaid
sequenceDiagram
    participant CLI as CLI/API
    participant Factory as AgentFactory
    participant Profiles as ProfileLoader
    participant FileState as FileStateManager
    participant DbState as DbStateManager
    participant LLM as OpenAIService
    
    CLI->>Factory: create_agent(profile="prod")
    
    Factory->>Profiles: load_profile("prod")
    Profiles->>Profiles: read configs/prod.yaml
    Profiles->>Profiles: merge_env_overrides()
    Profiles->>Profiles: validate_config()
    Profiles-->>Factory: config
    
    Note over Factory: Config inspection:<br/>persistence.type = "database"
    
    Factory->>Factory: _create_state_manager(config)
    alt config.persistence.type == "database"
        Factory->>DbState: new DbStateManager(db_url)
        DbState->>PostgreSQL: Test connection
        PostgreSQL-->>DbState: OK
        DbState-->>Factory: state_manager
    else config.persistence.type == "file"
        Factory->>FileState: new FileStateManager(work_dir)
        FileState-->>Factory: state_manager
    end
    
    Factory->>Factory: _create_llm_provider(config)
    Factory->>LLM: new OpenAIService(llm_config_path)
    LLM->>LLM: Load llm_config.yaml
    alt config.llm.provider == "azure"
        LLM->>LLM: Configure Azure endpoint
    else config.llm.provider == "openai"
        LLM->>LLM: Configure OpenAI endpoint
    end
    LLM-->>Factory: llm_provider
    
    Factory->>Factory: _create_tools(config)
    Factory-->>CLI: Agent(state_manager, llm_provider, tools)
```

---

### **Rationale:**

**Workflow Selection Decisions:**

1. **ReAct Loop as Primary Workflow**: Showcased complete thought → action → observation cycle. Rationale: This is the core algorithm - understanding this workflow is essential for all developers.

2. **State Persistence with Concurrency**: Included optimistic locking scenario. Rationale: Production environment may have multiple agent instances. Shows how conflicts are detected and resolved.

3. **Streaming API Workflow**: Demonstrated SSE pattern. Rationale: Long-running missions need progress updates. Shows how domain events translate to API events.

4. **Error Handling in Tool Execution**: Showed retry logic explicitly. Rationale: External tool calls fail frequently. Retry strategy is critical for reliability.

5. **Profile-Based Adapter Selection**: Illustrated dependency injection. Rationale: Shows how Clean Architecture enables runtime adapter swapping via configuration.

**Key Patterns Illustrated:**

- **Async throughout**: All I/O operations use async/await
- **Protocol-based boundaries**: Agent never calls concrete implementations directly
- **Event-driven progress**: Domain events enable real-time updates
- **Defensive error handling**: Every external call wrapped in try/catch with retry
- **Structured logging**: Every significant operation logged with context

**Trade-offs:**

- **Sequence diagram complexity**: Detailed diagrams vs. readability. Chose detail to show actual implementation patterns.
- **Workflow scope**: Full workflows vs. focused interactions. Chose full workflows to show end-to-end flow.

---

🏗️ **Proceeding to Security...**

---

## Section 8: Security

Security considerations and implementation strategies for Taskforce:

---

### **Authentication & Authorization**

#### **API Authentication**

**Current Implementation (MVP):**
- **API Key Authentication** for FastAPI REST endpoints
- Simple bearer token validation: `Authorization: Bearer {API_KEY}`
- API keys stored in environment variable `TASKFORCE_API_KEY`
- No per-user authentication in MVP (single-tenant)

**Code Pattern:**
```python
# api/deps.py
from fastapi import HTTPException, Security, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
import os

security = HTTPBearer()

async def verify_api_key(
    credentials: HTTPAuthorizationCredentials = Security(security)
) -> None:
    """Verify API key from Authorization header."""
    api_key = os.getenv("TASKFORCE_API_KEY")
    if not api_key:
        # Allow access if no API key configured (dev mode)
        return
    
    if credentials.credentials != api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API key"
        )
```

**Future Enhancements (Post-MVP):**
- **OAuth 2.0 / JWT**: For multi-tenant deployments
- **Role-Based Access Control (RBAC)**: Admin, user, read-only roles
- **Per-user session isolation**: User ID attached to sessions for auditing
- **API key rotation**: Automated key rotation with grace periods

#### **CLI Authentication**

**Current Implementation:**
- No authentication required (local development tool)
- Assumes trusted execution environment

**Future Enhancements:**
- Local credential storage for remote API calls
- SSH key-based authentication for remote agents

---

### **Secret Management**

#### **Current Strategy (Environment Variables)**

**API Keys and Credentials:**
All sensitive credentials stored as environment variables:
- `OPENAI_API_KEY` - OpenAI API access
- `AZURE_OPENAI_API_KEY` - Azure OpenAI API access
- `AZURE_OPENAI_ENDPOINT` - Azure OpenAI endpoint URL
- `AZURE_SEARCH_API_KEY` - Azure AI Search API key
- `AZURE_SEARCH_ENDPOINT` - Azure AI Search endpoint URL
- `GITHUB_TOKEN` - GitHub API access (optional)
- `TASKFORCE_API_KEY` - FastAPI authentication key
- `DATABASE_URL` - PostgreSQL connection string (contains password)

**Environment Variable Loading:**
```python
# application/profiles.py
import os
from typing import Dict, Any

def merge_env_overrides(config: Dict[str, Any]) -> Dict[str, Any]:
    """Override config with environment variables."""
    env_mappings = {
        "OPENAI_API_KEY": "llm.openai_api_key",
        "DATABASE_URL": "persistence.database_url",
        "TASKFORCE_API_KEY": "api.auth_key",
    }
    
    for env_var, config_path in env_mappings.items():
        value = os.getenv(env_var)
        if value:
            set_nested_config(config, config_path, value)
    
    return config
```

**Security Measures:**
- ✅ Never log API keys (filtered from structured logs)
- ✅ Never commit to version control (.env files in .gitignore)
- ✅ Never pass secrets via command line arguments (visible in process list)
- ✅ Use environment variables for Docker containers (via docker-compose secrets)

#### **Future Strategy (Production)**

**Kubernetes Secrets / Azure Key Vault:**
```python
# Future: infrastructure/secrets/key_vault.py
from azure.keyvault.secrets import SecretClient
from azure.identity import DefaultAzureCredential

class KeyVaultSecretProvider:
    """Azure Key Vault integration for production secrets."""
    
    async def get_secret(self, secret_name: str) -> str:
        """Retrieve secret from Azure Key Vault."""
        credential = DefaultAzureCredential()
        client = SecretClient(
            vault_url=os.getenv("AZURE_KEYVAULT_URL"),
            credential=credential
        )
        secret = client.get_secret(secret_name)
        return secret.value
```

**Planned Enhancements:**
- Azure Key Vault integration for production
- Kubernetes secrets for container deployments
- Secret rotation monitoring and alerts
- Separate secrets for dev/staging/prod environments

---

### **Data Security**

#### **Data at Rest**

**PostgreSQL Encryption:**
- **Database Level**: PostgreSQL Transparent Data Encryption (TDE) enabled on production instances
- **Connection Encryption**: SSL/TLS required for all database connections
  ```python
  # Connection string example
  DATABASE_URL = "postgresql+asyncpg://user:pass@host:5432/db?ssl=require"
  ```
- **Backup Encryption**: Automated backups encrypted with AES-256
- **State Data**: Session state stored as JSONB (may contain sensitive user inputs)
  - Future: Field-level encryption for sensitive state data (e.g., API tokens in state)

**File System (Development Mode):**
- File-based state stored in `{work_dir}/states/` directory
- Permissions: 600 (owner read/write only) on state files
- Recommendation: Work directory on encrypted volume

**Docker Volumes:**
- State volumes mounted with appropriate permissions
- Avoid mounting sensitive directories into containers

#### **Data in Transit**

**HTTPS/TLS Requirements:**
- **Production**: HTTPS mandatory for FastAPI endpoints (enforced via reverse proxy/ingress)
- **Development**: HTTP acceptable for localhost
- **API Calls**: All external API calls (OpenAI, Azure) use HTTPS

**TLS Configuration (Reverse Proxy):**
```yaml
# Example nginx configuration (not in Taskforce repo)
server {
    listen 443 ssl http2;
    ssl_certificate /etc/ssl/certs/taskforce.crt;
    ssl_certificate_key /etc/ssl/private/taskforce.key;
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_ciphers HIGH:!aNULL:!MD5;
    
    location /api/ {
        proxy_pass http://taskforce:8000;
        proxy_set_header X-Forwarded-Proto https;
    }
}
```

**Database Connections:**
- SSL required for PostgreSQL connections in staging/prod profiles
- Certificate verification enabled

---

### **Input Validation & Sanitization**

#### **API Input Validation**

**Pydantic Request Models:**
```python
# api/models.py
from pydantic import BaseModel, Field, validator
from typing import Optional

class ExecuteRequest(BaseModel):
    """Mission execution request."""
    mission: str = Field(..., min_length=1, max_length=10000)
    profile: str = Field(default="dev", regex="^(dev|staging|prod)$")
    session_id: Optional[str] = Field(default=None, regex="^[a-f0-9-]{36}$")
    
    @validator("mission")
    def validate_mission(cls, v: str) -> str:
        """Prevent excessively long missions."""
        if len(v.strip()) == 0:
            raise ValueError("Mission cannot be empty")
        return v.strip()
```

**Benefits:**
- Type safety (Pydantic enforces types)
- Automatic validation before handler execution
- Clear error messages for invalid requests

#### **Prompt Injection Prevention**

**LLM Security Considerations:**
Taskforce sends user-provided mission text directly to LLMs. Potential risks:
1. **Prompt Injection**: User crafts mission to manipulate agent behavior
2. **Data Exfiltration**: User tricks agent into leaking system prompts or state
3. **Jailbreaking**: User bypasses safety restrictions

**Mitigation Strategies:**

1. **System Prompt Protection:**
   ```python
   # Separate system and user messages clearly
   messages = [
       {"role": "system", "content": SYSTEM_PROMPT},
       {"role": "user", "content": f"Mission: {user_mission}"}
   ]
   ```

2. **Input Sanitization:**
   ```python
   def sanitize_mission(mission: str) -> str:
       """Remove potentially harmful content from mission text."""
       # Strip markdown code blocks that might confuse LLM
       mission = re.sub(r"```.*?```", "", mission, flags=re.DOTALL)
       # Limit length
       return mission[:10000]
   ```

3. **Output Validation:**
   - Validate tool parameters before execution
   - Prevent file operations outside work directory
   - Reject shell commands with suspicious patterns (e.g., `rm -rf /`)

4. **Least Privilege Execution:**
   - Python tool runs in restricted namespace (no `os`, `sys` imports by default)
   - File tools reject absolute paths outside work directory
   - Shell tools run with timeout limits

**Example: File Path Validation:**
```python
# infrastructure/tools/native/file_tools.py
import os
from pathlib import Path

def validate_file_path(file_path: str, work_dir: str) -> Path:
    """Ensure file path is within work directory."""
    resolved = Path(file_path).resolve()
    work_dir_resolved = Path(work_dir).resolve()
    
    if not resolved.is_relative_to(work_dir_resolved):
        raise SecurityError(
            f"File path {file_path} is outside work directory"
        )
    
    return resolved
```

---

### **Dependency Security**

#### **Dependency Management**

**Package Security:**
- **uv** package manager with lock file (`uv.lock`)
- Dependency pinning for reproducible builds
- Regular security audits via `pip-audit` or GitHub Dependabot

**Automated Scanning:**
```yaml
# .github/workflows/security.yml (future)
name: Security Scan
on: [push, pull_request]
jobs:
  dependency-check:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - run: pip install pip-audit
      - run: pip-audit --requirement pyproject.toml
```

**Known Security Considerations:**
- **LiteLLM**: Keep updated for API security patches
- **FastAPI**: Keep updated for web framework vulnerabilities
- **SQLAlchemy**: Keep updated for SQL injection mitigations
- **aiohttp**: Keep updated for HTTP client vulnerabilities

#### **Docker Image Security**

**Base Image Selection:**
- Use official Python slim images: `python:3.11-slim`
- Avoid `latest` tags (use specific versions)
- Regular base image updates

**Non-Root User:**
```dockerfile
# Dockerfile
FROM python:3.11-slim

# Create non-root user
RUN useradd -m -u 1000 taskforce
USER taskforce

WORKDIR /app
COPY --chown=taskforce:taskforce . .
RUN uv sync

CMD ["uvicorn", "taskforce.api.server:app", "--host", "0.0.0.0"]
```

**Image Scanning:**
- Trivy or Snyk for vulnerability scanning
- Scan images in CI/CD pipeline before deployment

---

### **Audit Logging**

#### **Structured Logging with structlog**

**Log All Security Events:**
```python
# infrastructure/logging/security_logger.py
import structlog

logger = structlog.get_logger()

# Authentication events
logger.info(
    "auth.api_key.success",
    endpoint="/api/v1/execute",
    client_ip=request.client.host
)

logger.warning(
    "auth.api_key.failed",
    endpoint="/api/v1/execute",
    client_ip=request.client.host,
    reason="invalid_key"
)

# Tool execution events
logger.info(
    "tool.execution.started",
    tool_name="shell",
    session_id=session_id,
    parameters=sanitized_params  # Sensitive params redacted
)

# State access events
logger.info(
    "state.loaded",
    session_id=session_id,
    user_id=user_id
)
```

**Log Retention:**
- Development: 7 days
- Staging: 30 days
- Production: 90 days (compliance requirement)

**Log Analysis:**
- Centralized logging via ELK stack or Azure Application Insights (future)
- Anomaly detection for suspicious patterns (future)

---

### **Rate Limiting & DDoS Protection**

#### **API Rate Limiting**

**FastAPI Middleware:**
```python
# api/middleware/rate_limit.py
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from fastapi import Request

limiter = Limiter(key_func=get_remote_address)

# Apply to routes
@app.post("/api/v1/execute")
@limiter.limit("10/minute")  # 10 requests per minute per IP
async def execute_mission(request: Request, data: ExecuteRequest):
    ...
```

**External API Rate Limiting:**
- Respect OpenAI/Azure rate limits (tracked in LLM service)
- Implement backoff and circuit breaker patterns
- Queue requests if approaching rate limits

#### **DDoS Protection**

**Infrastructure Level:**
- Reverse proxy rate limiting (nginx, Traefik)
- Cloud provider DDoS protection (Azure DDoS Protection, Cloudflare)
- Request size limits (max 10MB payload)

---

### **Kubernetes Security (Future)**

**When migrating from Docker Compose to Kubernetes:**

**Pod Security Standards:**
- Run as non-root user (UID > 1000)
- Read-only root filesystem where possible
- Drop all capabilities except required ones
- Network policies to restrict inter-pod communication

**Secrets Management:**
- Use Kubernetes secrets (not environment variables in manifests)
- Azure Key Vault CSI driver for production secrets
- Rotate secrets regularly

**RBAC:**
- Service accounts with minimal permissions
- No cluster-admin access for applications

---

### **Compliance Considerations**

**GDPR (if handling EU user data):**
- Right to be forgotten: Delete session state API endpoint
- Data minimization: Don't log user inputs unnecessarily
- Audit trail: Track all data access

**SOC 2 Type II (future):**
- Comprehensive audit logging
- Access control policies documented
- Incident response procedures

---

### **Security Checklist (Pre-Production)**

**Before deploying to production:**

- [ ] All API keys stored in environment variables (not code)
- [ ] HTTPS enforced on all API endpoints
- [ ] PostgreSQL SSL connections required
- [ ] Database credentials rotated from defaults
- [ ] API authentication enabled (`TASKFORCE_API_KEY` set)
- [ ] Rate limiting configured
- [ ] Dependency security scan passed
- [ ] Docker images scanned for vulnerabilities
- [ ] Audit logging enabled and tested
- [ ] File path validation prevents directory traversal
- [ ] Python tool sandbox prevents dangerous imports
- [ ] Shell command validation prevents injection
- [ ] Log retention policy configured
- [ ] Backup encryption verified
- [ ] Incident response plan documented

---

### **Rationale:**

**Security Design Decisions:**

1. **API Key over OAuth for MVP**: Simple bearer token authentication initially. Rationale: Faster to implement, sufficient for single-tenant. Trade-off: Less granular access control vs. time to market.

2. **Environment Variables for Secrets**: Standard 12-factor app pattern. Rationale: Simple, works across Docker and Kubernetes. Trade-off: Less secure than Key Vault, but acceptable with proper ops practices.

3. **No Field-Level Encryption (MVP)**: Session state stored as plaintext JSONB. Rationale: Simplifies queries and debugging. Trade-off: Sensitive data visible to DB admins. Mitigated by database encryption at rest and access controls.

4. **Prompt Injection Mitigation (Not Prevention)**: Input sanitization reduces but doesn't eliminate prompt injection risk. Rationale: Complete prevention requires constrained LLM usage that limits flexibility. Trade-off: Security vs. agent capability.

5. **Defensive Tool Validation**: Every tool validates inputs and restricts operations. Rationale: Defense in depth - even if agent is compromised, damage is limited.

**Key Assumptions:**
- Users trust the agent with tool access (validated: this is an automation agent, trust is required)
- Docker/Compose environment is reasonably secure (needs validation: network isolation, host hardening)
- OpenAI API keys treated as highly sensitive (validated: compromise = cost + data leak)

**Known Limitations (MVP):**
- No multi-tenancy (single shared agent)
- No fine-grained RBAC
- No field-level encryption
- Limited prompt injection prevention

---

🏗️ **Proceeding to Performance & Scalability...**

---

## Section 9: Performance & Scalability

Performance targets, bottleneck analysis, and scalability strategies for Taskforce:

---

### **Performance Targets**

#### **Latency Requirements**

**API Response Times (p95):**
- **Health Check**: < 100ms
- **Session List/Get**: < 200ms (database query)
- **Mission Start (non-streaming)**: < 500ms (initial setup, before ReAct loop)
- **Streaming Event Delivery**: < 100ms per event (SSE latency)
- **ReAct Loop Iteration**: 2-10 seconds (dominated by LLM latency)
  - Thought generation: 1-5 seconds (OpenAI API call)
  - Tool execution: 0.1-5 seconds (tool-dependent)
  - State persistence: < 100ms

**CLI Response Times:**
- **Command startup**: < 500ms (Python import overhead)
- **Interactive chat**: Same as ReAct loop iteration (2-10s)
- **Session list**: < 1 second

**Database Query Performance:**
- **State load/save**: < 50ms (single row lookup with index)
- **Session list with pagination**: < 100ms (indexed query)
- **TodoList load**: < 50ms (JSONB retrieval)

#### **Throughput Targets**

**API Throughput (per instance):**
- **Concurrent missions**: 10-50 concurrent agent executions per instance
  - Limited by: CPU (JSON parsing), memory (agent state), I/O (database connections)
- **Requests per second**: 100 RPS for read-only endpoints (health, session get)
- **Database connections**: 20 connections per instance (asyncpg pool)

**LLM API Throughput:**
- **OpenAI rate limits**: 500 RPM (requests per minute) for GPT-4
- **Azure OpenAI**: Configured per deployment (typically 240K TPM)
- **Mitigation**: Queue requests, implement circuit breaker, multi-instance deployment

#### **Resource Utilization**

**Memory per Agent Instance:**
- **Baseline**: 200 MB (Python runtime + libraries)
- **Per active session**: +10-50 MB (agent state, message history, tool instances)
- **Target**: Support 50 concurrent sessions on 4 GB instance

**CPU Utilization:**
- **Async I/O bound**: Low CPU during LLM/database waits
- **JSON parsing**: High CPU during JSONB deserialization (large states)
- **Target**: < 70% average CPU utilization

**Database Storage:**
- **Per session**: ~10-100 KB (state + execution history)
- **Per TodoList**: ~5-20 KB (plan data)
- **Growth rate**: Depends on retention policy
  - Example: 1000 sessions/day × 50 KB = 50 MB/day = 18 GB/year

---

### **Bottleneck Analysis**

#### **Primary Bottlenecks (MVP)**

**1. LLM API Latency (Dominant)**
- **Impact**: 80% of total execution time
- **Characteristics**: 
  - High variability (1-10 seconds)
  - Rate limits constrain throughput
  - Not horizontally scalable (external service)
- **Mitigation**:
  - Use faster models (GPT-4-mini) for simple reasoning
  - Implement caching for repeated prompts (future)
  - Parallel tool execution where possible (future)

**2. Database Connection Pool Exhaustion**
- **Impact**: When concurrent sessions > connection pool size
- **Characteristics**:
  - Fixed pool size (default: 20 connections)
  - Connection acquisition timeout under load
  - Symptoms: 429 errors, increased latency
- **Mitigation**:
  ```python
  # Database pool configuration
  asyncpg_pool = await asyncpg.create_pool(
      dsn=DATABASE_URL,
      min_size=10,
      max_size=50,  # Increased for high load
      command_timeout=30,
      max_queries=50000,
      max_inactive_connection_lifetime=300
  )
  ```

**3. State Serialization (JSONB)**
- **Impact**: Increases with state size (large execution history)
- **Characteristics**:
  - CPU-bound JSON encoding/decoding
  - Large JSONB columns slow down queries
  - Symptom: High CPU, slow database queries
- **Mitigation**:
  - Paginate execution history (don't load all steps)
  - Compress large state fields (gzip)
  - Archive old sessions to separate table

**4. Memory Leaks (Long-Running Agents)**
- **Impact**: Memory growth over time
- **Characteristics**:
  - Unclosed aiohttp sessions
  - Retained message history
  - Large tool output accumulation
- **Mitigation**:
  - Explicit resource cleanup (async context managers)
  - Message history window limit (keep last N messages)
  - Tool output truncation (max 10 KB per observation)

---

### **Caching Strategy**

#### **LLM Response Caching (Future Enhancement)**

**Semantic Caching:**
```python
# infrastructure/llm/cache.py
import hashlib
from typing import Optional

class LLMCache:
    """Cache LLM responses for repeated prompts."""
    
    def __init__(self, redis_client):
        self.redis = redis_client
    
    async def get_cached_response(
        self, 
        model: str, 
        messages: list
    ) -> Optional[str]:
        """Retrieve cached response if available."""
        cache_key = self._generate_key(model, messages)
        return await self.redis.get(cache_key)
    
    async def cache_response(
        self, 
        model: str, 
        messages: list, 
        response: str,
        ttl_seconds: int = 3600
    ):
        """Cache LLM response with TTL."""
        cache_key = self._generate_key(model, messages)
        await self.redis.setex(cache_key, ttl_seconds, response)
    
    def _generate_key(self, model: str, messages: list) -> str:
        """Generate cache key from model and messages."""
        content = f"{model}:{str(messages)}"
        return f"llm:cache:{hashlib.sha256(content.encode()).hexdigest()}"
```

**Benefits:**
- Reduce LLM API costs for repeated missions
- Faster response times for cached queries
- Lower rate limit pressure

**Trade-offs:**
- Non-deterministic responses (LLM outputs vary)
- Cache invalidation complexity
- Redis dependency

#### **State Caching (In-Memory)**

**Agent State Cache:**
```python
# infrastructure/persistence/cached_state.py
from functools import lru_cache
from typing import Optional, Dict, Any

class CachedStateManager:
    """In-memory cache layer over DbStateManager."""
    
    def __init__(self, db_state_manager: DbStateManager):
        self.db = db_state_manager
        self.cache: Dict[str, Dict[str, Any]] = {}
    
    async def load_state(self, session_id: str) -> Optional[Dict[str, Any]]:
        """Load from cache first, fallback to database."""
        if session_id in self.cache:
            return self.cache[session_id]
        
        state = await self.db.load_state(session_id)
        if state:
            self.cache[session_id] = state
        return state
    
    async def save_state(self, session_id: str, state_data: Dict[str, Any]):
        """Write to cache and database."""
        self.cache[session_id] = state_data
        await self.db.save_state(session_id, state_data)
```

**Benefits:**
- Faster state access for active sessions
- Reduced database load

**Trade-offs:**
- Memory usage scales with active sessions
- Cache consistency with multi-instance deployments

---

### **Horizontal Scalability**

#### **Stateless API Design**

**Scalability Characteristics:**
- **FastAPI instances**: Stateless (session state in database, not memory)
- **Load balancing**: Round-robin or least-connections
- **Session affinity**: Not required (any instance can handle any session)

**Docker Compose Scaling (Development/Staging):**
```yaml
# docker-compose.yml
services:
  taskforce-api:
    image: taskforce:latest
    deploy:
      replicas: 3  # Run 3 instances
    environment:
      - DATABASE_URL=postgresql://...
      - OPENAI_API_KEY=${OPENAI_API_KEY}
    depends_on:
      - postgres
    
  nginx:
    image: nginx:alpine
    volumes:
      - ./nginx.conf:/etc/nginx/nginx.conf
    ports:
      - "80:80"
    depends_on:
      - taskforce-api
```

**Load Balancer Configuration (nginx):**
```nginx
# nginx.conf
upstream taskforce_backend {
    least_conn;  # Route to instance with fewest connections
    server taskforce-api:8000 max_fails=3 fail_timeout=30s;
}

server {
    listen 80;
    
    location /api/ {
        proxy_pass http://taskforce_backend;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        
        # Streaming support
        proxy_buffering off;
        proxy_cache off;
    }
}
```

#### **Database Scalability**

**PostgreSQL Optimization:**

**Connection Pooling (PgBouncer):**
```yaml
# docker-compose.yml
services:
  pgbouncer:
    image: pgbouncer/pgbouncer:latest
    environment:
      - DATABASES_HOST=postgres
      - DATABASES_PORT=5432
      - DATABASES_USER=taskforce
      - DATABASES_PASSWORD=${DB_PASSWORD}
      - PGBOUNCER_POOL_MODE=transaction
      - PGBOUNCER_MAX_CLIENT_CONN=1000
      - PGBOUNCER_DEFAULT_POOL_SIZE=25
    ports:
      - "6432:6432"
```

**Benefits:**
- Support many more clients than direct database connections
- Reduce connection overhead

**Read Replicas (Future):**
- PostgreSQL streaming replication
- Route read queries (session list, state load) to replicas
- Write queries (state save) to primary
- Trade-off: Eventual consistency (replication lag)

**Indexing Strategy:**
```sql
-- Critical indexes for performance
CREATE INDEX idx_sessions_user_id ON sessions(user_id);
CREATE INDEX idx_sessions_status ON sessions(status);
CREATE INDEX idx_sessions_created_at ON sessions(created_at DESC);
CREATE INDEX idx_states_session_id_version ON states(session_id, version DESC);
CREATE INDEX idx_execution_history_session_step ON execution_history(session_id, step_id);

-- JSONB indexes for state queries (if needed)
CREATE INDEX idx_states_json_todolist ON states USING GIN ((state_json->'todolist_id'));
```

---

### **Async I/O Optimization**

#### **Async Throughout the Stack**

**Benefits of Async Architecture:**
- **Non-blocking I/O**: One thread handles many concurrent requests
- **Efficient resource usage**: Minimal memory overhead per request
- **Scalability**: 10-100x more concurrent connections than sync

**Key Async Patterns:**

**1. Async Database Queries:**
```python
# All database operations use asyncpg
async def load_state(self, session_id: str) -> Optional[Dict[str, Any]]:
    async with self.pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT state_json FROM states WHERE session_id = $1 ORDER BY version DESC LIMIT 1",
            session_id
        )
        return row['state_json'] if row else None
```

**2. Async LLM Calls:**
```python
# LiteLLM with async
response = await litellm.acompletion(
    model=model_name,
    messages=messages,
    timeout=30.0
)
```

**3. Async Tool Execution:**
```python
# All tools implement async execute
async def execute(self, **params) -> Dict[str, Any]:
    # Use asyncio.subprocess for shell commands
    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE
    )
    stdout, stderr = await proc.communicate()
    return {"output": stdout.decode()}
```

**4. Async File Operations:**
```python
# aiofiles for async file I/O
async with aiofiles.open(state_file, "w") as f:
    await f.write(json.dumps(state_data))
```

#### **Concurrency Control**

**Semaphore for Rate Limiting:**
```python
# Limit concurrent LLM calls
class RateLimitedLLMService:
    def __init__(self, max_concurrent: int = 10):
        self.semaphore = asyncio.Semaphore(max_concurrent)
    
    async def complete(self, **kwargs):
        async with self.semaphore:
            return await litellm.acompletion(**kwargs)
```

**Task Groups for Parallel Execution:**
```python
# Execute multiple tools in parallel (future)
async def execute_parallel_tools(self, tools: List[ToolCall]):
    async with asyncio.TaskGroup() as tg:
        tasks = [tg.create_task(tool.execute(**params)) for tool in tools]
    return [task.result() for task in tasks]
```

---

### **Resource Limits & Guardrails**

#### **Execution Timeouts**

**Per-Request Timeouts:**
```python
# FastAPI timeout middleware
from starlette.middleware.base import BaseHTTPMiddleware

class TimeoutMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        try:
            return await asyncio.wait_for(
                call_next(request),
                timeout=300.0  # 5 minute max per request
            )
        except asyncio.TimeoutError:
            return JSONResponse(
                status_code=504,
                content={"error": "Request timeout"}
            )
```

**Tool Execution Timeouts:**
```python
# Per-tool timeout configuration
TOOL_TIMEOUTS = {
    "python": 60,  # 1 minute
    "shell": 300,  # 5 minutes
    "web_search": 30,  # 30 seconds
    "llm": 60,  # 1 minute
}

async def execute_with_timeout(tool: Tool, **params):
    timeout = TOOL_TIMEOUTS.get(tool.name, 60)
    try:
        return await asyncio.wait_for(
            tool.execute(**params),
            timeout=timeout
        )
    except asyncio.TimeoutError:
        return {"success": False, "error": f"Tool timeout after {timeout}s"}
```

#### **Memory Limits**

**Message History Window:**
```python
class MessageHistory:
    MAX_MESSAGES = 50  # Keep last 50 message pairs
    
    def add_message(self, role: str, content: str):
        self.messages.append({"role": role, "content": content})
        
        # Trim old messages
        if len(self.messages) > self.MAX_MESSAGES:
            # Keep system prompt (first message)
            self.messages = [self.messages[0]] + self.messages[-self.MAX_MESSAGES:]
```

**Tool Output Truncation:**
```python
MAX_TOOL_OUTPUT_SIZE = 10 * 1024  # 10 KB

def truncate_output(output: str) -> str:
    """Truncate large tool outputs."""
    if len(output) > MAX_TOOL_OUTPUT_SIZE:
        return output[:MAX_TOOL_OUTPUT_SIZE] + "\n... (truncated)"
    return output
```

---

### **Performance Monitoring**

#### **Instrumentation Points**

**Key Metrics to Track:**
```python
# infrastructure/monitoring/metrics.py
import structlog
from time import perf_counter

logger = structlog.get_logger()

async def track_latency(operation: str):
    """Context manager for latency tracking."""
    start = perf_counter()
    try:
        yield
    finally:
        duration_ms = (perf_counter() - start) * 1000
        logger.info(
            "performance.latency",
            operation=operation,
            duration_ms=duration_ms
        )

# Usage
async with track_latency("agent.execute"):
    await agent.execute(mission, session_id)
```

**Tracked Operations:**
- Agent execution (total)
- LLM thought generation
- Tool execution (per tool)
- State load/save
- Database queries
- API request handling

#### **Performance Dashboards (Future)**

**Grafana Dashboard Metrics:**
- Request latency (p50, p95, p99)
- Throughput (requests/second)
- Error rate (4xx, 5xx)
- Database connection pool utilization
- LLM API latency
- Active sessions count
- Memory usage per instance

---

### **Scalability Roadmap**

**Phase 1: MVP (Docker Compose)**
- Single instance deployment
- File or database persistence
- No caching
- Target: 10 concurrent sessions

**Phase 2: Multi-Instance (Docker Compose with Nginx)**
- 3-5 API instances behind load balancer
- Database persistence required
- PgBouncer connection pooling
- Target: 50 concurrent sessions

**Phase 3: Production (Kubernetes)**
- Horizontal pod autoscaling (HPA) based on CPU/memory
- PostgreSQL with read replicas
- Redis for LLM caching
- Target: 500+ concurrent sessions

**Phase 4: Optimization (Post-Launch)**
- CDN for static content
- Response caching (Redis)
- Parallel tool execution
- Circuit breaker for external APIs
- Target: 1000+ concurrent sessions

---

### **Rationale:**

**Performance Design Decisions:**

1. **Async-First Architecture**: All I/O operations async. Rationale: LLM calls dominate latency (5-10s), async enables efficient concurrent request handling during waits. Trade-off: Complexity vs. throughput.

2. **Database for Production State**: PostgreSQL over in-memory. Rationale: Durability required for production, supports multi-instance deployments. Trade-off: Latency (~50ms) vs. durability.

3. **No LLM Caching (MVP)**: Deferred to future. Rationale: Cache invalidation complex, non-deterministic responses reduce value. Trade-off: Cost/latency vs. complexity.

4. **Connection Pooling**: PgBouncer for database connections. Rationale: PostgreSQL max_connections limited (~100-200), pooling enables 1000+ clients. Trade-off: Transaction mode limitations vs. scalability.

5. **Aggressive Timeouts**: 5-minute max per request, 1-minute per tool. Rationale: Prevent resource exhaustion from hung operations. Trade-off: May interrupt long-running legitimate operations.

**Key Assumptions:**
- LLM latency is acceptable (5-10s per iteration) - validated by Agent V2 usage
- Database can handle 100 sessions/second write load - needs validation via load testing
- Async architecture provides sufficient concurrency - validated by FastAPI benchmarks (10K+ concurrent connections possible)

🏗️ **Proceeding to Deployment...**

---

## Section 10: Deployment

Deployment architecture, infrastructure setup, and operational procedures for Taskforce:

---

### **Deployment Environments**

#### **Environment Strategy**

**Three-tier deployment:**

1. **Development (Local)**
   - Purpose: Individual developer workstations
   - Deployment: Docker Compose
   - Persistence: File-based state (`FileStateManager`)
   - LLM: OpenAI API (personal keys)
   - Database: Optional PostgreSQL container (for testing DB features)

2. **Staging**
   - Purpose: Pre-production testing, integration testing
   - Deployment: Docker Compose on dedicated VM/server
   - Persistence: PostgreSQL container with persistent volume
   - LLM: Shared OpenAI or Azure OpenAI account
   - Database: PostgreSQL 15 in Docker with backups
   - URL: `https://staging.taskforce.internal`

3. **Production (Future)**
   - Purpose: Live user-facing environment
   - Deployment: Kubernetes cluster (Azure AKS or on-premise)
   - Persistence: Managed PostgreSQL (Azure Database for PostgreSQL)
   - LLM: Azure OpenAI with private endpoint
   - Database: Managed service with high availability
   - URL: `https://api.taskforce.example.com`

---

### **Docker Compose Setup (Development & Staging)**

#### **Docker Compose Architecture**

```yaml
# docker-compose.yml
version: '3.8'

services:
  # PostgreSQL Database
  postgres:
    image: postgres:15-alpine
    container_name: taskforce-postgres
    environment:
      POSTGRES_DB: taskforce
      POSTGRES_USER: taskforce
      POSTGRES_PASSWORD: ${DB_PASSWORD}
      POSTGRES_INITDB_ARGS: "--encoding=UTF8 --locale=en_US.utf8"
    volumes:
      - postgres_data:/var/lib/postgresql/data
      - ./init.sql:/docker-entrypoint-initdb.d/init.sql
    ports:
      - "5432:5432"
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U taskforce"]
      interval: 10s
      timeout: 5s
      retries: 5
    restart: unless-stopped

  # Taskforce API Service
  taskforce-api:
    build:
      context: .
      dockerfile: Dockerfile
    image: taskforce:latest
    container_name: taskforce-api
    environment:
      # Database
      DATABASE_URL: postgresql+asyncpg://taskforce:${DB_PASSWORD}@postgres:5432/taskforce
      
      # LLM Configuration
      OPENAI_API_KEY: ${OPENAI_API_KEY}
      AZURE_OPENAI_API_KEY: ${AZURE_OPENAI_API_KEY:-}
      AZURE_OPENAI_ENDPOINT: ${AZURE_OPENAI_ENDPOINT:-}
      
      # RAG Configuration (optional)
      AZURE_SEARCH_ENDPOINT: ${AZURE_SEARCH_ENDPOINT:-}
      AZURE_SEARCH_API_KEY: ${AZURE_SEARCH_API_KEY:-}
      
      # API Configuration
      TASKFORCE_API_KEY: ${TASKFORCE_API_KEY}
      PROFILE: ${PROFILE:-staging}
      LOG_LEVEL: ${LOG_LEVEL:-info}
      
      # Work Directory
      WORK_DIR: /app/data
    volumes:
      - taskforce_data:/app/data
      - ./configs:/app/configs:ro
    ports:
      - "8000:8000"
    depends_on:
      postgres:
        condition: service_healthy
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8000/health"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 40s
    restart: unless-stopped

  # Nginx Reverse Proxy (Staging only)
  nginx:
    image: nginx:alpine
    container_name: taskforce-nginx
    volumes:
      - ./nginx.conf:/etc/nginx/nginx.conf:ro
      - ./ssl:/etc/nginx/ssl:ro  # SSL certificates
    ports:
      - "80:80"
      - "443:443"
    depends_on:
      - taskforce-api
    restart: unless-stopped
    profiles:
      - staging  # Only run in staging

volumes:
  postgres_data:
    driver: local
  taskforce_data:
    driver: local

networks:
  default:
    name: taskforce-network
```

#### **Dockerfile**

```dockerfile
# Dockerfile
FROM python:3.11-slim

# Install system dependencies
RUN apt-get update && apt-get install -y \
    curl \
    git \
    && rm -rf /var/lib/apt/lists/*

# Create non-root user
RUN useradd -m -u 1000 taskforce && \
    mkdir -p /app/data && \
    chown -R taskforce:taskforce /app

# Set working directory
WORKDIR /app

# Copy dependency files
COPY --chown=taskforce:taskforce pyproject.toml uv.lock ./

# Install uv and dependencies
RUN pip install --no-cache-dir uv && \
    uv sync --frozen

# Copy application code
COPY --chown=taskforce:taskforce . .

# Switch to non-root user
USER taskforce

# Expose port
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
  CMD curl -f http://localhost:8000/health || exit 1

# Run application
CMD ["uv", "run", "uvicorn", "taskforce.api.server:app", "--host", "0.0.0.0", "--port", "8000"]
```

#### **Environment Variables (.env)**

```bash
# .env (not committed to git)
# Database
DB_PASSWORD=change_me_in_production

# LLM Providers
OPENAI_API_KEY=sk-...
AZURE_OPENAI_API_KEY=
AZURE_OPENAI_ENDPOINT=

# RAG (optional)
AZURE_SEARCH_ENDPOINT=
AZURE_SEARCH_API_KEY=

# API Security
TASKFORCE_API_KEY=secure_random_key_here

# Configuration
PROFILE=staging
LOG_LEVEL=info
```

---

### **Deployment Procedures**

#### **Initial Deployment (Staging)**

**Prerequisites:**
- Docker and Docker Compose installed
- `.env` file configured with secrets
- SSL certificates (for HTTPS) in `./ssl/` directory

**Steps:**

```powershell
# 1. Clone repository
git clone https://github.com/yourorg/taskforce.git
cd taskforce

# 2. Configure environment
Copy-Item .env.example .env
# Edit .env with your secrets

# 3. Build images
docker-compose build

# 4. Initialize database (run migrations)
docker-compose run --rm taskforce-api uv run alembic upgrade head

# 5. Start services
docker-compose --profile staging up -d

# 6. Verify deployment
docker-compose ps
curl http://localhost:8000/health
```

**Expected Output:**
```json
{
  "status": "healthy",
  "version": "1.0.0",
  "database": "connected",
  "timestamp": "2025-11-22T10:00:00Z"
}
```

#### **Updates and Rollbacks**

**Deployment Update:**
```powershell
# 1. Pull latest changes
git pull origin main

# 2. Rebuild images
docker-compose build

# 3. Rolling restart (zero downtime with multiple replicas)
docker-compose up -d --no-deps --build taskforce-api

# 4. Verify health
docker-compose exec taskforce-api curl http://localhost:8000/health
```

**Database Migration:**
```powershell
# Run migrations (before deploying new code)
docker-compose run --rm taskforce-api uv run alembic upgrade head

# Rollback migration if needed
docker-compose run --rm taskforce-api uv run alembic downgrade -1
```

**Rollback Procedure:**
```powershell
# 1. Identify previous working version
git log --oneline -10

# 2. Checkout previous version
git checkout <commit-hash>

# 3. Rebuild and restart
docker-compose build
docker-compose up -d

# 4. Rollback database if needed
docker-compose run --rm taskforce-api uv run alembic downgrade <revision>
```

---

### **Database Migrations (Alembic)**

#### **Alembic Configuration**

```python
# alembic.ini
[alembic]
script_location = taskforce/migrations
sqlalchemy.url = # Set via env var

[loggers]
keys = root,sqlalchemy,alembic

[handlers]
keys = console

[formatters]
keys = generic

[logger_root]
level = WARN
handlers = console

[logger_sqlalchemy]
level = WARN
handlers =
qualname = sqlalchemy.engine

[logger_alembic]
level = INFO
handlers =
qualname = alembic

[handler_console]
class = StreamHandler
args = (sys.stderr,)
level = NOTSET
formatter = generic

[formatter_generic]
format = %(levelname)-5.5s [%(name)s] %(message)s
datefmt = %H:%M:%S
```

```python
# taskforce/migrations/env.py
from logging.config import fileConfig
from sqlalchemy import engine_from_config, pool
from alembic import context
import os

# Import your models
from taskforce.infrastructure.persistence.models import Base

config = context.config

# Override sqlalchemy.url from environment
config.set_main_option(
    "sqlalchemy.url",
    os.getenv("DATABASE_URL", "postgresql://taskforce:password@localhost/taskforce")
)

fileConfig(config.config_file_name)

target_metadata = Base.metadata

def run_migrations_online():
    connectable = engine_from_config(
        config.get_section(config.config_ini_section),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)

        with context.begin_transaction():
            context.run_migrations()

run_migrations_online()
```

#### **Creating Migrations**

```powershell
# Auto-generate migration from model changes
docker-compose run --rm taskforce-api uv run alembic revision --autogenerate -m "Add memory table"

# Manually create migration
docker-compose run --rm taskforce-api uv run alembic revision -m "Custom change"

# Apply migrations
docker-compose run --rm taskforce-api uv run alembic upgrade head

# Check current version
docker-compose run --rm taskforce-api uv run alembic current

# Show migration history
docker-compose run --rm taskforce-api uv run alembic history
```

---

### **Backup & Recovery**

#### **Database Backups**

**Automated Backup Script:**
```powershell
# scripts/backup-db.ps1
$BACKUP_DIR = "backups"
$TIMESTAMP = Get-Date -Format "yyyyMMdd_HHmmss"
$BACKUP_FILE = "$BACKUP_DIR/taskforce_backup_$TIMESTAMP.sql"

# Create backup directory
New-Item -ItemType Directory -Force -Path $BACKUP_DIR

# Run pg_dump
docker-compose exec -T postgres pg_dump -U taskforce taskforce > $BACKUP_FILE

# Compress backup
Compress-Archive -Path $BACKUP_FILE -DestinationPath "$BACKUP_FILE.zip"
Remove-Item $BACKUP_FILE

Write-Host "Backup created: $BACKUP_FILE.zip"

# Delete backups older than 30 days
Get-ChildItem -Path $BACKUP_DIR -Filter "*.zip" | 
    Where-Object { $_.LastWriteTime -lt (Get-Date).AddDays(-30) } | 
    Remove-Item
```

**Schedule Backups (Windows Task Scheduler):**
- Frequency: Daily at 2 AM
- Retention: 30 days
- Storage: Local disk + offsite copy (Azure Blob Storage)

**Restore from Backup:**
```powershell
# Extract backup
Expand-Archive -Path backups/taskforce_backup_20251122.sql.zip -DestinationPath temp/

# Stop services
docker-compose stop taskforce-api

# Drop and recreate database
docker-compose exec postgres psql -U taskforce -c "DROP DATABASE IF EXISTS taskforce;"
docker-compose exec postgres psql -U taskforce -c "CREATE DATABASE taskforce;"

# Restore backup
Get-Content temp/taskforce_backup_20251122.sql | docker-compose exec -T postgres psql -U taskforce taskforce

# Restart services
docker-compose start taskforce-api
```

#### **State Data Backups**

**File-based State (Development):**
```powershell
# Backup work directory
Compress-Archive -Path data/states -DestinationPath backups/states_$(Get-Date -Format 'yyyyMMdd').zip
```

**Database State (Staging/Production):**
Included in PostgreSQL backups (states table)

---

### **Monitoring & Health Checks**

#### **Health Check Endpoints**

**Liveness Probe:**
```python
# api/routes/health.py
@app.get("/health")
async def health_check():
    """Basic liveness probe."""
    return {
        "status": "healthy",
        "version": __version__,
        "timestamp": datetime.utcnow().isoformat()
    }
```

**Readiness Probe:**
```python
@app.get("/health/ready")
async def readiness_check(
    db: AsyncSession = Depends(get_db_session)
):
    """Readiness probe - checks database connectivity."""
    try:
        # Test database connection
        await db.execute(text("SELECT 1"))
        
        # Test LLM provider (future)
        # llm_status = await llm_service.health_check()
        
        return {
            "status": "ready",
            "database": "connected",
            "timestamp": datetime.utcnow().isoformat()
        }
    except Exception as e:
        raise HTTPException(
            status_code=503,
            detail=f"Service not ready: {str(e)}"
        )
```

#### **Docker Healthchecks**

Configured in `docker-compose.yml`:
- API: `curl -f http://localhost:8000/health`
- PostgreSQL: `pg_isready -U taskforce`
- Frequency: Every 30 seconds
- Restart policy: `unless-stopped`

---

### **Logging & Log Aggregation**

#### **Structured Logging Configuration**

```python
# infrastructure/logging/config.py
import structlog
import logging

def configure_logging(log_level: str = "INFO"):
    """Configure structured logging."""
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.JSONRenderer()  # JSON output for production
        ],
        wrapper_class=structlog.make_filtering_bound_logger(
            logging.getLevelName(log_level)
        ),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )
```

**Log Output (JSON):**
```json
{
  "event": "agent.execution.started",
  "level": "info",
  "timestamp": "2025-11-22T10:30:00.123Z",
  "session_id": "abc-123",
  "mission": "Create hello world",
  "profile": "staging"
}
```

#### **Log Collection (Docker)**

```yaml
# docker-compose.yml (add to services)
services:
  taskforce-api:
    logging:
      driver: "json-file"
      options:
        max-size: "10m"
        max-file: "3"
```

**View Logs:**
```powershell
# Follow logs
docker-compose logs -f taskforce-api

# Last 100 lines
docker-compose logs --tail=100 taskforce-api

# Export logs
docker-compose logs --no-color taskforce-api > taskforce.log
```

---

### **SSL/TLS Configuration (Staging)**

#### **Nginx SSL Termination**

```nginx
# nginx.conf
events {
    worker_connections 1024;
}

http {
    upstream taskforce_backend {
        server taskforce-api:8000;
    }

    # Redirect HTTP to HTTPS
    server {
        listen 80;
        server_name staging.taskforce.internal;
        return 301 https://$server_name$request_uri;
    }

    # HTTPS server
    server {
        listen 443 ssl http2;
        server_name staging.taskforce.internal;

        # SSL certificates
        ssl_certificate /etc/nginx/ssl/cert.pem;
        ssl_certificate_key /etc/nginx/ssl/key.pem;
        
        # SSL configuration
        ssl_protocols TLSv1.2 TLSv1.3;
        ssl_ciphers HIGH:!aNULL:!MD5;
        ssl_prefer_server_ciphers on;
        ssl_session_cache shared:SSL:10m;
        ssl_session_timeout 10m;

        # Security headers
        add_header Strict-Transport-Security "max-age=31536000" always;
        add_header X-Content-Type-Options "nosniff" always;
        add_header X-Frame-Options "DENY" always;

        # Proxy configuration
        location /api/ {
            proxy_pass http://taskforce_backend;
            proxy_set_header Host $host;
            proxy_set_header X-Real-IP $remote_addr;
            proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
            proxy_set_header X-Forwarded-Proto $scheme;
            
            # Streaming support
            proxy_buffering off;
            proxy_cache off;
            proxy_read_timeout 300s;
        }

        # Health check (no auth required)
        location /health {
            proxy_pass http://taskforce_backend;
            access_log off;
        }
    }
}
```

---

### **Kubernetes Deployment (Future)**

#### **Kubernetes Manifests**

```yaml
# k8s/deployment.yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: taskforce-api
  namespace: taskforce
spec:
  replicas: 3
  selector:
    matchLabels:
      app: taskforce-api
  template:
    metadata:
      labels:
        app: taskforce-api
    spec:
      containers:
      - name: taskforce
        image: taskforce:1.0.0
        ports:
        - containerPort: 8000
        env:
        - name: DATABASE_URL
          valueFrom:
            secretKeyRef:
              name: taskforce-secrets
              key: database-url
        - name: OPENAI_API_KEY
          valueFrom:
            secretKeyRef:
              name: taskforce-secrets
              key: openai-api-key
        resources:
          requests:
            memory: "512Mi"
            cpu: "500m"
          limits:
            memory: "2Gi"
            cpu: "2000m"
        livenessProbe:
          httpGet:
            path: /health
            port: 8000
          initialDelaySeconds: 30
          periodSeconds: 10
        readinessProbe:
          httpGet:
            path: /health/ready
            port: 8000
          initialDelaySeconds: 10
          periodSeconds: 5
---
apiVersion: v1
kind: Service
metadata:
  name: taskforce-api
  namespace: taskforce
spec:
  selector:
    app: taskforce-api
  ports:
  - protocol: TCP
    port: 80
    targetPort: 8000
  type: ClusterIP
---
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: taskforce-ingress
  namespace: taskforce
  annotations:
    cert-manager.io/cluster-issuer: "letsencrypt-prod"
spec:
  tls:
  - hosts:
    - api.taskforce.example.com
    secretName: taskforce-tls
  rules:
  - host: api.taskforce.example.com
    http:
      paths:
      - path: /
        pathType: Prefix
        backend:
          service:
            name: taskforce-api
            port:
              number: 80
```

**Horizontal Pod Autoscaler:**
```yaml
# k8s/hpa.yaml
apiVersion: autoscaling/v2
kind: HorizontalPodAutoscaler
metadata:
  name: taskforce-api-hpa
  namespace: taskforce
spec:
  scaleTargetRef:
    apiVersion: apps/v1
    kind: Deployment
    name: taskforce-api
  minReplicas: 3
  maxReplicas: 10
  metrics:
  - type: Resource
    resource:
      name: cpu
      target:
        type: Utilization
        averageUtilization: 70
  - type: Resource
    resource:
      name: memory
      target:
        type: Utilization
        averageUtilization: 80
```

---

### **CI/CD Pipeline (Future)**

#### **GitHub Actions Workflow**

```yaml
# .github/workflows/deploy.yml
name: Build and Deploy

on:
  push:
    branches: [main, staging]
  pull_request:
    branches: [main]

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      
      - name: Set up Python
        uses: actions/setup-python@v4
        with:
          python-version: '3.11'
      
      - name: Install dependencies
        run: |
          pip install uv
          uv sync
      
      - name: Run tests
        run: uv run pytest
      
      - name: Run linters
        run: |
          uv run ruff check .
          uv run black --check .

  build:
    needs: test
    runs-on: ubuntu-latest
    if: github.ref == 'refs/heads/main' || github.ref == 'refs/heads/staging'
    steps:
      - uses: actions/checkout@v3
      
      - name: Build Docker image
        run: docker build -t taskforce:${{ github.sha }} .
      
      - name: Push to registry
        run: |
          docker tag taskforce:${{ github.sha }} registry.example.com/taskforce:latest
          docker push registry.example.com/taskforce:latest

  deploy-staging:
    needs: build
    runs-on: ubuntu-latest
    if: github.ref == 'refs/heads/staging'
    steps:
      - name: Deploy to staging
        run: |
          ssh staging-server "cd /app/taskforce && docker-compose pull && docker-compose up -d"
```

---

### **Operational Procedures**

#### **Daily Operations**

**Morning Checks:**
- Check service health: `docker-compose ps`
- Review logs for errors: `docker-compose logs --tail=100 taskforce-api | grep -i error`
- Check disk space: `docker system df`
- Verify backups completed: `Get-ChildItem backups | Sort-Object LastWriteTime -Descending | Select-Object -First 1`

**Incident Response:**
1. Check service status: `docker-compose ps`
2. Review recent logs: `docker-compose logs --tail=500 taskforce-api`
3. Check resource usage: `docker stats`
4. Restart service if needed: `docker-compose restart taskforce-api`
5. Escalate if issue persists

#### **Maintenance Windows**

**Scheduled Maintenance:**
- Frequency: Monthly (last Sunday, 2-4 AM)
- Activities:
  - OS updates
  - Docker image updates
  - Database maintenance (VACUUM, ANALYZE)
  - Certificate renewals

**Maintenance Procedure:**
```powershell
# 1. Notify users (if applicable)
# 2. Stop services
docker-compose stop taskforce-api

# 3. Backup database
.\scripts\backup-db.ps1

# 4. Apply updates
docker-compose pull
docker-compose build --pull

# 5. Run migrations
docker-compose run --rm taskforce-api uv run alembic upgrade head

# 6. Start services
docker-compose up -d

# 7. Verify health
Start-Sleep -Seconds 30
curl http://localhost:8000/health

# 8. Monitor for issues
docker-compose logs -f taskforce-api
```

---

### **Rationale:**

**Deployment Design Decisions:**

1. **Docker Compose First, Kubernetes Later**: Start with Docker Compose for simplicity. Rationale: Faster iteration during initial development. Many organizations don't need Kubernetes complexity. Trade-off: Less auto-scaling vs. operational simplicity.

2. **PostgreSQL in Docker (Staging)**: Containerized database for staging. Rationale: Simplifies setup, good enough for staging load. Trade-off: Not production-grade (managed service better) but acceptable for staging.

3. **File-based State for Dev**: FileStateManager for local development. Rationale: Zero setup, no database required. Trade-off: Not multi-instance safe vs. developer experience.

4. **Alembic for Migrations**: SQLAlchemy migration tool. Rationale: Standard Python ecosystem tool, version control for schema. Trade-off: Learning curve vs. database reliability.

5. **Nginx for SSL Termination**: Reverse proxy handles HTTPS. Rationale: Offload SSL from Python app, battle-tested, efficient. Trade-off: Additional component vs. security/performance.

**Key Assumptions:**
- Docker Compose sufficient for staging (<100 concurrent users) - validated by common practice
- Daily backups acceptable (RPO = 24 hours) - needs validation based on business requirements
- Single region deployment acceptable initially - needs validation for disaster recovery

---

## Section 11: Testing Strategy

Comprehensive testing approach ensuring quality, reliability, and maintainability:

---

### **Testing Pyramid**

```
         /\
        /E2E\        ← 5-10% - End-to-End (Slow, Fragile)
       /------\
      /  API   \     ← 15-20% - Integration Tests (Moderate)
     /----------\
    /   Unit     \   ← 70-80% - Unit Tests (Fast, Isolated)
   /--------------\
```

**Testing Philosophy:**
- **Fast feedback**: Most tests should run in seconds
- **Isolated**: Unit tests don't touch database/network
- **Realistic**: Integration tests use real adapters (PostgreSQL, not mocks)
- **Automated**: All tests run in CI/CD pipeline
- **Maintainable**: Tests document expected behavior

---

### **Unit Tests (Core Layer)**

#### **Scope**

Test pure business logic in `core/` layer:
- Agent ReAct loop logic
- PlanGenerator decomposition
- Domain event creation
- Validation logic

**Key Characteristic**: Zero infrastructure dependencies (no database, no HTTP, no LLM calls)

#### **Example: Agent Core Logic Tests**

```python
# tests/unit/core/test_agent.py
import pytest
from unittest.mock import AsyncMock, MagicMock
from taskforce.core.domain.agent import Agent
from taskforce.core.domain.events import Thought, Action, Observation
from taskforce.core.interfaces.state import StateManagerProtocol
from taskforce.core.interfaces.llm import LLMProviderProtocol
from taskforce.core.interfaces.tools import ToolProtocol

@pytest.fixture
def mock_state_manager():
    """Mock state manager for testing."""
    mock = AsyncMock(spec=StateManagerProtocol)
    mock.load_state.return_value = None
    mock.save_state.return_value = None
    return mock

@pytest.fixture
def mock_llm_provider():
    """Mock LLM provider for testing."""
    mock = AsyncMock(spec=LLMProviderProtocol)
    mock.complete.return_value = {
        "choices": [{"message": {"content": "Test thought"}}]
    }
    return mock

@pytest.fixture
def mock_tool():
    """Mock tool for testing."""
    tool = MagicMock(spec=ToolProtocol)
    tool.name = "test_tool"
    tool.execute = AsyncMock(return_value={"success": True, "output": "Done"})
    return tool

@pytest.mark.asyncio
async def test_agent_execute_simple_mission(
    mock_state_manager,
    mock_llm_provider,
    mock_tool
):
    """Test agent executes a simple mission successfully."""
    # Arrange
    agent = Agent(
        state_manager=mock_state_manager,
        llm_provider=mock_llm_provider,
        tools={"test_tool": mock_tool}
    )
    mission = "Test mission"
    session_id = "test-session-123"
    
    # Act
    result = await agent.execute(mission, session_id)
    
    # Assert
    assert result.status == "completed"
    assert mock_state_manager.save_state.called
    assert mock_llm_provider.complete.called

@pytest.mark.asyncio
async def test_agent_handles_tool_failure(
    mock_state_manager,
    mock_llm_provider,
    mock_tool
):
    """Test agent handles tool execution failures gracefully."""
    # Arrange
    mock_tool.execute.return_value = {
        "success": False, 
        "error": "Tool failed"
    }
    agent = Agent(
        state_manager=mock_state_manager,
        llm_provider=mock_llm_provider,
        tools={"test_tool": mock_tool}
    )
    
    # Act
    result = await agent.execute("Test mission", "test-session")
    
    # Assert
    assert result.status in ["failed", "completed"]  # May retry or complete
    # Verify error was logged in observations
    assert any("error" in obs.lower() for obs in result.observations)

@pytest.mark.asyncio
async def test_agent_respects_max_iterations():
    """Test agent stops after max iterations to prevent infinite loops."""
    # Arrange
    mock_state = AsyncMock(spec=StateManagerProtocol)
    mock_llm = AsyncMock(spec=LLMProviderProtocol)
    
    # LLM never returns "complete" action
    mock_llm.complete.return_value = {
        "choices": [{"message": {"content": "Keep working"}}]
    }
    
    agent = Agent(
        state_manager=mock_state,
        llm_provider=mock_llm,
        tools={},
        max_iterations=5  # Force limit
    )
    
    # Act
    result = await agent.execute("Infinite mission", "test-session")
    
    # Assert
    assert result.iteration_count == 5
    assert result.status == "max_iterations_reached"
```

#### **Example: PlanGenerator Tests**

```python
# tests/unit/core/test_plan.py
import pytest
from unittest.mock import AsyncMock
from taskforce.core.domain.plan import PlanGenerator, TodoList, TodoItem, TaskStatus

@pytest.fixture
def mock_llm_provider():
    """Mock LLM that returns valid plan JSON."""
    mock = AsyncMock()
    mock.complete.return_value = {
        "choices": [{
            "message": {
                "content": """
                {
                    "items": [
                        {
                            "position": 0,
                            "description": "Step 1",
                            "acceptance_criteria": ["Done"],
                            "dependencies": []
                        },
                        {
                            "position": 1,
                            "description": "Step 2",
                            "acceptance_criteria": ["Completed"],
                            "dependencies": [0]
                        }
                    ]
                }
                """
            }
        }]
    }
    return mock

@pytest.mark.asyncio
async def test_plan_generator_creates_valid_plan(mock_llm_provider):
    """Test plan generator creates TodoList from mission."""
    # Arrange
    planner = PlanGenerator(llm_provider=mock_llm_provider)
    mission = "Create a web app"
    
    # Act
    plan = await planner.generate_plan(mission)
    
    # Assert
    assert isinstance(plan, TodoList)
    assert len(plan.items) == 2
    assert plan.items[0].status == TaskStatus.PENDING
    assert plan.items[1].dependencies == [0]

def test_plan_validation_detects_circular_dependencies():
    """Test plan validation catches circular dependencies."""
    # Arrange
    planner = PlanGenerator(llm_provider=None)
    
    # Create circular dependency: 0 -> 1 -> 2 -> 0
    plan = TodoList(
        todolist_id="test",
        session_id="test",
        mission="Test",
        items=[
            TodoItem(position=0, description="A", acceptance_criteria=[], dependencies=[2]),
            TodoItem(position=1, description="B", acceptance_criteria=[], dependencies=[0]),
            TodoItem(position=2, description="C", acceptance_criteria=[], dependencies=[1])
        ]
    )
    
    # Act & Assert
    with pytest.raises(ValueError, match="circular dependency"):
        planner.validate_dependencies(plan)

def test_plan_validation_accepts_valid_dag():
    """Test plan validation accepts valid DAG structure."""
    # Arrange
    planner = PlanGenerator(llm_provider=None)
    
    # Valid DAG: 0 <- 1, 0 <- 2, 1 <- 3
    plan = TodoList(
        todolist_id="test",
        session_id="test",
        mission="Test",
        items=[
            TodoItem(position=0, description="A", acceptance_criteria=[], dependencies=[]),
            TodoItem(position=1, description="B", acceptance_criteria=[], dependencies=[0]),
            TodoItem(position=2, description="C", acceptance_criteria=[], dependencies=[0]),
            TodoItem(position=3, description="D", acceptance_criteria=[], dependencies=[1])
        ]
    )
    
    # Act & Assert (should not raise)
    planner.validate_dependencies(plan)
```

#### **Running Unit Tests**

```powershell
# Run all unit tests
uv run pytest tests/unit/ -v

# Run with coverage
uv run pytest tests/unit/ --cov=taskforce.core --cov-report=html

# Run specific test file
uv run pytest tests/unit/core/test_agent.py -v

# Run tests matching pattern
uv run pytest tests/unit/ -k "test_agent" -v
```

**Coverage Target**: ≥80% for core layer

---

### **Integration Tests (Infrastructure Layer)**

#### **Scope**

Test infrastructure adapters with real dependencies:
- Database operations (actual PostgreSQL)
- LLM service (mocked HTTP, not real API)
- Tool execution (actual subprocess/filesystem)
- State persistence round-trips

**Key Characteristic**: Uses real infrastructure, but may mock external APIs

#### **Example: DbStateManager Integration Tests**

```python
# tests/integration/infrastructure/test_db_state.py
import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from taskforce.infrastructure.persistence.db_state import DbStateManager
from taskforce.infrastructure.persistence.models import Base

@pytest_asyncio.fixture
async def test_db():
    """Create test database."""
    # Use in-memory SQLite for fast tests
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    
    # Create schema
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    
    yield engine
    
    # Cleanup
    await engine.dispose()

@pytest_asyncio.fixture
async def db_state_manager(test_db):
    """Create DbStateManager with test database."""
    return DbStateManager(engine=test_db)

@pytest.mark.asyncio
async def test_save_and_load_state(db_state_manager):
    """Test state persistence round-trip."""
    # Arrange
    session_id = "test-session-123"
    state_data = {
        "mission": "Test mission",
        "status": "in_progress",
        "answers": {"question1": "answer1"}
    }
    
    # Act - Save
    await db_state_manager.save_state(session_id, state_data)
    
    # Act - Load
    loaded_state = await db_state_manager.load_state(session_id)
    
    # Assert
    assert loaded_state is not None
    assert loaded_state["mission"] == "Test mission"
    assert loaded_state["answers"]["question1"] == "answer1"

@pytest.mark.asyncio
async def test_state_versioning(db_state_manager):
    """Test state version increments on each save."""
    # Arrange
    session_id = "test-session-version"
    
    # Act - Save multiple versions
    await db_state_manager.save_state(session_id, {"version": 1})
    await db_state_manager.save_state(session_id, {"version": 2})
    await db_state_manager.save_state(session_id, {"version": 3})
    
    # Assert - Latest version loaded
    loaded = await db_state_manager.load_state(session_id)
    assert loaded["version"] == 3
    
    # Assert - Can query version history
    history = await db_state_manager.get_state_history(session_id)
    assert len(history) == 3

@pytest.mark.asyncio
async def test_concurrent_state_updates_conflict_detection(db_state_manager):
    """Test optimistic locking detects concurrent modifications."""
    # Arrange
    session_id = "test-concurrent"
    await db_state_manager.save_state(session_id, {"value": 1})
    
    # Act - Simulate two instances updating same session
    # Instance 1 updates
    state1 = await db_state_manager.load_state(session_id)
    state1["value"] = 2
    await db_state_manager.save_state(session_id, state1)
    
    # Instance 2 tries to update with stale version
    state2 = {"value": 3}  # Stale version
    
    # Assert - Should detect conflict
    with pytest.raises(Exception, match="conflict|version"):
        await db_state_manager.save_state(
            session_id, 
            state2, 
            expected_version=1  # Stale version
        )
```

#### **Example: Tool Integration Tests**

```python
# tests/integration/infrastructure/test_python_tool.py
import pytest
from taskforce.infrastructure.tools.native.python_tool import PythonTool

@pytest.mark.asyncio
async def test_python_tool_executes_valid_code():
    """Test Python tool executes code successfully."""
    # Arrange
    tool = PythonTool(work_dir="/tmp/test")
    code = """
result = 2 + 2
print(f"Result: {result}")
    """
    
    # Act
    result = await tool.execute(code=code)
    
    # Assert
    assert result["success"] is True
    assert "Result: 4" in result["output"]

@pytest.mark.asyncio
async def test_python_tool_handles_syntax_errors():
    """Test Python tool catches syntax errors."""
    # Arrange
    tool = PythonTool(work_dir="/tmp/test")
    code = "print(unclosed string"  # Syntax error
    
    # Act
    result = await tool.execute(code=code)
    
    # Assert
    assert result["success"] is False
    assert "SyntaxError" in result["error"]

@pytest.mark.asyncio
async def test_python_tool_namespace_isolation():
    """Test Python tool runs each execution in isolated namespace."""
    # Arrange
    tool = PythonTool(work_dir="/tmp/test")
    
    # Act - First execution defines variable
    result1 = await tool.execute(code="x = 42")
    assert result1["success"] is True
    
    # Act - Second execution should not see 'x'
    result2 = await tool.execute(code="print(x)")
    
    # Assert
    assert result2["success"] is False
    assert "NameError" in result2["error"]

@pytest.mark.asyncio
async def test_python_tool_respects_timeout():
    """Test Python tool times out infinite loops."""
    # Arrange
    tool = PythonTool(work_dir="/tmp/test", timeout=2)  # 2 second timeout
    code = "while True: pass"  # Infinite loop
    
    # Act
    result = await tool.execute(code=code)
    
    # Assert
    assert result["success"] is False
    assert "timeout" in result["error"].lower()
```

#### **Running Integration Tests**

```powershell
# Run all integration tests
uv run pytest tests/integration/ -v

# Run with test database
uv run pytest tests/integration/ -v --db-url=postgresql://test:test@localhost/taskforce_test

# Run specific integration test
uv run pytest tests/integration/infrastructure/test_db_state.py -v

# Run with real PostgreSQL (requires Docker)
docker-compose -f docker-compose.test.yml up -d postgres-test
uv run pytest tests/integration/ --db-url=postgresql://taskforce:test@localhost:5433/taskforce_test
docker-compose -f docker-compose.test.yml down
```

**Coverage Target**: ≥70% for infrastructure layer

---

### **API Tests (FastAPI Endpoints)**

#### **Scope**

Test HTTP API endpoints with real FastAPI test client:
- Request/response validation
- Authentication
- Error handling
- Streaming endpoints

#### **Example: FastAPI Endpoint Tests**

```python
# tests/api/test_execution_routes.py
import pytest
from httpx import AsyncClient
from taskforce.api.server import app
from unittest.mock import AsyncMock, patch

@pytest.fixture
def api_key():
    """Test API key."""
    return "test-api-key-123"

@pytest.fixture
def auth_headers(api_key):
    """Authorization headers."""
    return {"Authorization": f"Bearer {api_key}"}

@pytest.mark.asyncio
async def test_execute_mission_endpoint(auth_headers):
    """Test POST /api/v1/execute endpoint."""
    # Arrange
    async with AsyncClient(app=app, base_url="http://test") as client:
        payload = {
            "mission": "Create hello world",
            "profile": "dev"
        }
        
        # Act
        with patch.dict("os.environ", {"TASKFORCE_API_KEY": "test-api-key-123"}):
            response = await client.post(
                "/api/v1/execute",
                json=payload,
                headers=auth_headers
            )
        
        # Assert
        assert response.status_code == 200
        data = response.json()
        assert "session_id" in data
        assert data["status"] in ["completed", "in_progress"]

@pytest.mark.asyncio
async def test_execute_mission_requires_authentication():
    """Test endpoint rejects requests without API key."""
    # Arrange
    async with AsyncClient(app=app, base_url="http://test") as client:
        payload = {"mission": "Test", "profile": "dev"}
        
        # Act
        with patch.dict("os.environ", {"TASKFORCE_API_KEY": "secret-key"}):
            response = await client.post("/api/v1/execute", json=payload)
        
        # Assert
        assert response.status_code == 401

@pytest.mark.asyncio
async def test_execute_mission_validates_input():
    """Test endpoint validates request payload."""
    # Arrange
    async with AsyncClient(app=app, base_url="http://test") as client:
        invalid_payload = {
            "mission": "",  # Empty mission
            "profile": "invalid-profile"  # Invalid profile
        }
        
        # Act
        response = await client.post(
            "/api/v1/execute",
            json=invalid_payload,
            headers={"Authorization": "Bearer test-key"}
        )
        
        # Assert
        assert response.status_code == 422  # Validation error

@pytest.mark.asyncio
async def test_health_check_endpoint():
    """Test GET /health endpoint."""
    # Arrange
    async with AsyncClient(app=app, base_url="http://test") as client:
        
        # Act
        response = await client.get("/health")
        
        # Assert
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert "version" in data

@pytest.mark.asyncio
async def test_streaming_execution_endpoint(auth_headers):
    """Test POST /api/v1/execute/stream with SSE."""
    # Arrange
    async with AsyncClient(app=app, base_url="http://test") as client:
        payload = {"mission": "Simple task", "profile": "dev"}
        
        # Act
        with patch.dict("os.environ", {"TASKFORCE_API_KEY": "test-api-key-123"}):
            async with client.stream(
                "POST",
                "/api/v1/execute/stream",
                json=payload,
                headers=auth_headers
            ) as response:
                # Assert
                assert response.status_code == 200
                assert "text/event-stream" in response.headers["content-type"]
                
                # Read events
                events = []
                async for line in response.aiter_lines():
                    if line.startswith("data: "):
                        events.append(line[6:])
                
                # Verify event types
                assert len(events) > 0
                # Should have thought, action, observation, complete events
```

#### **Running API Tests**

```powershell
# Run API tests
uv run pytest tests/api/ -v

# Run with coverage
uv run pytest tests/api/ --cov=taskforce.api --cov-report=html
```

**Coverage Target**: ≥80% for API layer

---

### **End-to-End (E2E) Tests**

#### **Scope**

Test complete user workflows with all components:
- CLI command execution
- Full ReAct loop with real tools
- Database persistence verification
- Multi-step missions

#### **Example: E2E CLI Tests**

```python
# tests/e2e/test_cli_workflows.py
import pytest
import subprocess
import json
from pathlib import Path

@pytest.fixture
def temp_work_dir(tmp_path):
    """Create temporary work directory."""
    work_dir = tmp_path / "taskforce_test"
    work_dir.mkdir()
    return work_dir

def test_cli_run_simple_mission(temp_work_dir):
    """Test 'taskforce run mission' command end-to-end."""
    # Arrange
    mission = "Create a Python file hello.py with a hello function"
    
    # Act
    result = subprocess.run(
        [
            "taskforce", "run", "mission", mission,
            "--profile", "dev",
            "--work-dir", str(temp_work_dir)
        ],
        capture_output=True,
        text=True,
        timeout=60
    )
    
    # Assert
    assert result.returncode == 0
    assert "completed" in result.stdout.lower()
    
    # Verify file was created
    hello_file = temp_work_dir / "hello.py"
    assert hello_file.exists()
    
    # Verify file content
    content = hello_file.read_text()
    assert "def hello" in content

def test_cli_session_persistence(temp_work_dir):
    """Test session state persists across commands."""
    # Act - Start mission
    result1 = subprocess.run(
        [
            "taskforce", "run", "mission", "Start work",
            "--profile", "dev",
            "--work-dir", str(temp_work_dir)
        ],
        capture_output=True,
        text=True
    )
    
    # Extract session ID from output
    output = result1.stdout
    session_id = None
    for line in output.split("\n"):
        if "session_id" in line.lower():
            # Parse session ID from output
            session_id = line.split(":")[-1].strip()
    
    assert session_id is not None
    
    # Act - List sessions
    result2 = subprocess.run(
        ["taskforce", "sessions", "list", "--work-dir", str(temp_work_dir)],
        capture_output=True,
        text=True
    )
    
    # Assert - Session appears in list
    assert session_id in result2.stdout
    
    # Act - Get session details
    result3 = subprocess.run(
        ["taskforce", "sessions", "show", session_id, "--work-dir", str(temp_work_dir)],
        capture_output=True,
        text=True
    )
    
    # Assert - Details include mission
    assert "Start work" in result3.stdout

@pytest.mark.slow
def test_cli_complex_mission_with_tools(temp_work_dir):
    """Test complex mission requiring multiple tools."""
    # Arrange
    mission = """
    1. Create a Python script that generates 10 random numbers
    2. Save the numbers to a file numbers.txt
    3. Read the file and calculate the average
    """
    
    # Act
    result = subprocess.run(
        [
            "taskforce", "run", "mission", mission,
            "--profile", "dev",
            "--work-dir", str(temp_work_dir)
        ],
        capture_output=True,
        text=True,
        timeout=120
    )
    
    # Assert
    assert result.returncode == 0
    
    # Verify artifacts
    assert (temp_work_dir / "numbers.txt").exists()
    assert "average" in result.stdout.lower()
```

#### **Example: E2E API Tests**

```python
# tests/e2e/test_api_workflows.py
import pytest
import httpx
import time

@pytest.mark.e2e
@pytest.mark.asyncio
async def test_complete_mission_execution_workflow():
    """Test full mission execution via API."""
    # Arrange
    base_url = "http://localhost:8000"
    api_key = "test-api-key"
    headers = {"Authorization": f"Bearer {api_key}"}
    
    async with httpx.AsyncClient(base_url=base_url, timeout=60.0) as client:
        # Act - Submit mission
        response = await client.post(
            "/api/v1/execute",
            json={
                "mission": "Create a hello world Python script",
                "profile": "dev"
            },
            headers=headers
        )
        
        assert response.status_code == 200
        data = response.json()
        session_id = data["session_id"]
        
        # Poll for completion
        max_attempts = 30
        for _ in range(max_attempts):
            response = await client.get(
                f"/api/v1/sessions/{session_id}",
                headers=headers
            )
            
            session_data = response.json()
            if session_data["status"] == "completed":
                break
            
            time.sleep(2)
        
        # Assert
        assert session_data["status"] == "completed"
        assert "mission" in session_data
```

#### **Running E2E Tests**

```powershell
# Run E2E tests (requires full environment)
docker-compose up -d
uv run pytest tests/e2e/ -v -m e2e
docker-compose down

# Run with real services
uv run pytest tests/e2e/ -v --base-url=http://localhost:8000

# Skip slow tests
uv run pytest tests/e2e/ -v -m "not slow"
```

**Coverage Target**: Key user workflows covered (not code coverage metric)

---

### **Performance/Load Tests**

#### **Scope**

Test system performance under load:
- Concurrent request handling
- Database connection pool exhaustion
- Memory leaks over time
- Response time degradation

#### **Example: Locust Load Tests**

```python
# tests/performance/locustfile.py
from locust import HttpUser, task, between
import random

class TaskforceUser(HttpUser):
    """Simulated user for load testing."""
    wait_time = between(1, 5)
    
    def on_start(self):
        """Setup: authenticate."""
        self.headers = {"Authorization": "Bearer test-api-key"}
    
    @task(3)
    def health_check(self):
        """Lightweight health check (most common)."""
        self.client.get("/health")
    
    @task(2)
    def list_sessions(self):
        """List sessions."""
        self.client.get("/api/v1/sessions", headers=self.headers)
    
    @task(1)
    def execute_mission(self):
        """Execute a simple mission (slowest)."""
        missions = [
            "Create a hello world script",
            "Calculate 2+2",
            "List files in current directory"
        ]
        
        response = self.client.post(
            "/api/v1/execute",
            json={
                "mission": random.choice(missions),
                "profile": "dev"
            },
            headers=self.headers,
            timeout=60
        )
        
        if response.status_code == 200:
            session_id = response.json()["session_id"]
            # Optionally poll for completion
            self.client.get(
                f"/api/v1/sessions/{session_id}",
                headers=self.headers
            )
```

#### **Running Load Tests**

```powershell
# Start services
docker-compose up -d

# Run load test (10 users, spawn 1/sec)
locust -f tests/performance/locustfile.py --host=http://localhost:8000 --users 10 --spawn-rate 1

# Run headless (no web UI)
locust -f tests/performance/locustfile.py --host=http://localhost:8000 --users 50 --spawn-rate 5 --run-time 5m --headless

# View results at http://localhost:8089
```

**Performance Targets**:
- **Health endpoint**: <100ms p95, 1000 RPS
- **Execute endpoint**: <10s p95, 10 concurrent
- **No memory leaks**: Stable memory over 1 hour test

---

### **Test Data Management**

#### **Fixtures and Factories**

```python
# tests/conftest.py
import pytest
from faker import Faker

fake = Faker()

@pytest.fixture
def sample_mission():
    """Generate sample mission text."""
    return f"Create a script that {fake.sentence()}"

@pytest.fixture
def sample_todolist():
    """Generate sample TodoList."""
    from taskforce.core.domain.plan import TodoList, TodoItem, TaskStatus
    
    return TodoList(
        todolist_id=fake.uuid4(),
        session_id=fake.uuid4(),
        mission="Test mission",
        items=[
            TodoItem(
                position=0,
                description=f"Step 1: {fake.sentence()}",
                acceptance_criteria=[fake.sentence()],
                dependencies=[],
                status=TaskStatus.PENDING
            ),
            TodoItem(
                position=1,
                description=f"Step 2: {fake.sentence()}",
                acceptance_criteria=[fake.sentence()],
                dependencies=[0],
                status=TaskStatus.PENDING
            )
        ]
    )

@pytest.fixture
def sample_session_state():
    """Generate sample session state."""
    return {
        "session_id": fake.uuid4(),
        "mission": fake.sentence(),
        "status": "in_progress",
        "answers": {},
        "todolist_id": fake.uuid4(),
        "current_step": 0
    }
```

---

### **Continuous Integration (CI) Testing**

#### **GitHub Actions Test Workflow**

```yaml
# .github/workflows/test.yml
name: Test Suite

on:
  push:
    branches: [main, develop]
  pull_request:
    branches: [main]

jobs:
  unit-tests:
    runs-on: ubuntu-latest
    strategy:
      matrix:
        python-version: ['3.11', '3.12']
    
    steps:
      - uses: actions/checkout@v3
      
      - name: Set up Python
        uses: actions/setup-python@v4
        with:
          python-version: ${{ matrix.python-version }}
      
      - name: Install dependencies
        run: |
          pip install uv
          uv sync
      
      - name: Run unit tests
        run: uv run pytest tests/unit/ -v --cov=taskforce.core --cov-report=xml
      
      - name: Upload coverage
        uses: codecov/codecov-action@v3
        with:
          files: ./coverage.xml

  integration-tests:
    runs-on: ubuntu-latest
    services:
      postgres:
        image: postgres:15
        env:
          POSTGRES_DB: taskforce_test
          POSTGRES_USER: taskforce
          POSTGRES_PASSWORD: test
        ports:
          - 5432:5432
        options: >-
          --health-cmd pg_isready
          --health-interval 10s
          --health-timeout 5s
          --health-retries 5
    
    steps:
      - uses: actions/checkout@v3
      
      - name: Set up Python
        uses: actions/setup-python@v4
        with:
          python-version: '3.11'
      
      - name: Install dependencies
        run: |
          pip install uv
          uv sync
      
      - name: Run integration tests
        env:
          DATABASE_URL: postgresql://taskforce:test@localhost:5432/taskforce_test
        run: uv run pytest tests/integration/ -v

  api-tests:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      
      - name: Set up Python
        uses: actions/setup-python@v4
        with:
          python-version: '3.11'
      
      - name: Install dependencies
        run: |
          pip install uv
          uv sync
      
      - name: Run API tests
        run: uv run pytest tests/api/ -v

  lint:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      
      - name: Set up Python
        uses: actions/setup-python@v4
        with:
          python-version: '3.11'
      
      - name: Install dependencies
        run: |
          pip install uv
          uv sync
      
      - name: Run linters
        run: |
          uv run ruff check .
          uv run black --check .
          uv run mypy taskforce/
```

---

### **Test Organization**

```
tests/
├── unit/                          # Unit tests (fast, isolated)
│   ├── core/
│   │   ├── test_agent.py
│   │   ├── test_plan.py
│   │   └── test_events.py
│   └── application/
│       ├── test_factory.py
│       └── test_profiles.py
│
├── integration/                   # Integration tests (real dependencies)
│   ├── infrastructure/
│   │   ├── test_db_state.py
│   │   ├── test_file_state.py
│   │   ├── test_llm_service.py
│   │   └── tools/
│   │       ├── test_python_tool.py
│   │       ├── test_file_tools.py
│   │       └── test_git_tools.py
│   └── application/
│       └── test_executor.py
│
├── api/                           # API tests (FastAPI)
│   ├── test_execution_routes.py
│   ├── test_session_routes.py
│   └── test_health.py
│
├── e2e/                           # End-to-end tests (full workflows)
│   ├── test_cli_workflows.py
│   └── test_api_workflows.py
│
├── performance/                   # Load tests
│   ├── locustfile.py
│   └── test_stress.py
│
├── conftest.py                    # Shared fixtures
└── pytest.ini                     # Pytest configuration
```

#### **pytest.ini Configuration**

```ini
# pytest.ini
[pytest]
testpaths = tests
python_files = test_*.py
python_classes = Test*
python_functions = test_*

# Markers
markers =
    unit: Unit tests (fast, isolated)
    integration: Integration tests (real dependencies)
    e2e: End-to-end tests (full workflows)
    slow: Slow tests (skip by default)
    performance: Performance/load tests

# Coverage
addopts =
    --strict-markers
    --verbose
    --color=yes
    --tb=short

# Asyncio
asyncio_mode = auto

# Logging
log_cli = true
log_cli_level = INFO
```

---

### **Test Execution Strategy**

**Development (Pre-commit)**:
```powershell
# Fast feedback (<30 seconds)
uv run pytest tests/unit/ -v
```

**Pull Request (CI)**:
```powershell
# Comprehensive (<5 minutes)
uv run pytest tests/unit/ tests/integration/ tests/api/ -v --cov
```

**Pre-Release (Staging)**:
```powershell
# Full suite including E2E (<30 minutes)
uv run pytest tests/ -v -m "not performance"
```

**Production Readiness**:
```powershell
# Load testing (hours)
locust -f tests/performance/locustfile.py --users 100 --spawn-rate 10 --run-time 2h
```

---

### **Rationale:**

**Testing Strategy Decisions:**

1. **Test Pyramid Structure**: 70% unit, 20% integration, 10% E2E. Rationale: Fast feedback from unit tests, realistic validation from integration tests, confidence from E2E tests. Trade-off: E2E tests are slow and fragile vs. confidence in full system.

2. **Real Dependencies in Integration Tests**: Use actual PostgreSQL, not mocks. Rationale: Mocks can hide integration issues (SQL syntax, connection pooling). Trade-off: Slower tests vs. realistic validation.

3. **Mock LLM Calls**: Don't call real OpenAI API in tests. Rationale: Expensive, slow, non-deterministic, rate-limited. Trade-off: May miss API changes vs. test speed and reliability.

4. **Async Tests Throughout**: All tests use `pytest-asyncio`. Rationale: Application is async, tests should match. Trade-off: Slightly more complex test setup vs. realistic testing.

5. **Fixtures Over Hardcoded Data**: Use pytest fixtures and Faker. Rationale: Reusable, randomized data catches edge cases. Trade-off: Less predictable vs. better coverage.

**Key Assumptions:**
- Unit test coverage >80% sufficient (validated: industry standard)
- Integration tests with SQLite adequate for most DB logic (needs validation: may miss PostgreSQL-specific issues)
- Mocked LLM responses representative (needs validation: actual API may behave differently)

---

## Section 12: Open Questions & Future Considerations

Outstanding questions and planned enhancements beyond MVP scope:

---

### **Open Questions (Require Decision)**

#### **1. Multi-Tenancy Strategy**

**Question**: How should Taskforce handle multiple users/organizations in production?

**Options**:
- **Option A**: Single-tenant deployment (one instance per customer)
  - Pros: Simple, strong isolation, easier security
  - Cons: Higher infrastructure cost, harder to maintain multiple instances
  
- **Option B**: Multi-tenant with row-level security (RLS)
  - Pros: Efficient resource usage, single deployment
  - Cons: More complex, risk of data leakage, performance impact
  
- **Option C**: Hybrid (multi-tenant for small customers, dedicated for enterprise)
  - Pros: Flexible, cost-effective
  - Cons: Operational complexity

**Recommendation**: Start with Option A (single-tenant) for MVP, evaluate Option C for v2.0 based on customer demand.

**Impacts**: Database schema (add tenant_id columns), authentication (JWT with tenant claims), deployment strategy (Kubernetes namespaces per tenant).

---

#### **2. LLM Cost Management**

**Question**: How should we prevent runaway LLM costs?

**Current State**: No hard cost limits, only token logging.

**Options**:
- **Option A**: Per-session token limits (e.g., 50K tokens max)
- **Option B**: Per-user monthly budget with alerting
- **Option C**: Rate limiting (e.g., 10 missions per hour per user)
- **Option D**: Graceful degradation (use cheaper models for simple tasks)

**Recommendation**: Implement Option A + Option C for MVP, add Option B for production.

**Unresolved**: How to communicate limits to users? How to handle limit exhaustion mid-mission?

---

#### **3. State Size Growth**

**Question**: How should we handle sessions with very large execution histories?

**Current State**: All execution steps stored in single JSONB column, loaded on every state read.

**Problem**: After 100+ ReAct iterations, state size could exceed 1MB, slowing queries.

**Options**:
- **Option A**: Pagination (only load last N steps)
- **Option B**: Separate table for execution history (don't load with state)
- **Option C**: Compression (gzip state_json)
- **Option D**: Archival (move old sessions to cold storage after 30 days)

**Recommendation**: Implement Option B (separate execution_history table) in MVP, add Option D post-launch.

**Impacts**: Database schema changes, state loading logic, API responses (pagination required).

---

#### **4. Tool Security Model**

**Question**: How should we prevent malicious tool usage?

**Current State**: Basic validation (file path checks, timeout limits), but tools can still execute arbitrary code/commands.

**Concerns**:
- Python tool can import dangerous modules (e.g., `subprocess`, `os`)
- Shell tool can run destructive commands (e.g., `rm -rf`)
- File tool could read sensitive files (e.g., `/etc/passwd`)

**Options**:
- **Option A**: Whitelist approach (only allow specific imports/commands)
  - Pros: Secure
  - Cons: Limits agent capabilities, high maintenance
  
- **Option B**: Sandbox execution (Docker containers, seccomp profiles)
  - Pros: Strong isolation
  - Cons: Performance overhead, complexity
  
- **Option C**: Human-in-the-loop approval for dangerous operations
  - Pros: User control
  - Cons: Breaks automation, poor UX
  
- **Option D**: Trust-based (current approach + audit logging)
  - Pros: Full capabilities
  - Cons: High risk

**Recommendation**: Start with Option D (trust-based) for MVP with clear documentation, evaluate Option B (sandboxing) for enterprise customers.

**Unresolved**: Define "dangerous operation" criteria? Should we scan code for patterns before execution?

---

#### **5. RAG Index Management**

**Question**: Who manages the Azure AI Search index for RAG features?

**Current State**: Assumes pre-existing index, no management capabilities in Taskforce.

**Options**:
- **Option A**: External tool (users manage with Azure portal/SDK)
  - Pros: Separation of concerns
  - Cons: Poor UX, requires external knowledge
  
- **Option B**: Built-in indexing (Taskforce provides CLI commands to index documents)
  - Pros: Better UX, self-contained
  - Cons: Scope creep, complexity
  
- **Option C**: Hybrid (basic management in Taskforce, advanced via Azure)
  - Pros: Balance of convenience and flexibility
  - Cons: May confuse users

**Recommendation**: Option A for MVP (document external setup), consider Option C for v2.0.

**Unresolved**: How to handle index schema changes? How to validate index compatibility?

---

### **Future Enhancements (Post-MVP)**

#### **Phase 2: Advanced Planning**

**Parallel Task Execution**:
- Allow TodoList to execute independent tasks concurrently
- Modify PlanGenerator to identify parallelizable steps
- Update Agent execution loop to use `asyncio.TaskGroup`

**Benefit**: 2-3x faster execution for missions with independent subtasks
**Effort**: Medium (2-3 weeks)
**Risk**: Increased complexity, potential race conditions

---

**Dynamic Replanning**:
- Allow agent to revise TodoList mid-execution when context changes
- Add `replan` action type with LLM-based plan diff
- Track plan versions for audit trail

**Benefit**: More adaptive agent, better handles unexpected situations
**Effort**: Medium (3-4 weeks)
**Risk**: May cause mission drift, harder to debug

---

#### **Phase 3: Memory & Learning**

**Cross-Session Memory**:
- Implement Memory table with vector embeddings
- Add MemoryRetrieval tool (semantic search over past lessons)
- Inject relevant memories into system prompt dynamically

**Benefit**: Agent learns from experience, fewer repeated mistakes
**Effort**: High (4-6 weeks)
**Risk**: Incorrect lessons may propagate, privacy concerns

---

**Feedback Loop**:
- Capture user feedback on mission outcomes (thumbs up/down)
- Use feedback to refine prompts and tool selection
- Train custom model on successful mission patterns (future)

**Benefit**: Continuous improvement, higher success rate
**Effort**: High (6-8 weeks)
**Risk**: Feedback bias, requires ML expertise

---

#### **Phase 4: Collaboration**

**Multi-Agent Orchestration**:
- Implement `SubAgentTool` (convert agent to tool via `agent.to_tool()`)
- Allow orchestrator agent to delegate subtasks to specialized agents
- Add agent communication protocol

**Benefit**: Specialization (e.g., CodeAgent, ResearchAgent), better at complex tasks
**Effort**: High (6-8 weeks)
**Risk**: Coordination complexity, higher LLM costs

---

**Human-in-the-Loop**:
- Add `approval_required` flag to TodoItems
- Pause execution before dangerous operations
- Send notification (webhook, email) for user approval

**Benefit**: User control, reduced risk
**Effort**: Medium (3-4 weeks)
**Risk**: Breaks automation, notification fatigue

---

#### **Phase 5: Observability**

**Distributed Tracing**:
- Integrate OpenTelemetry for request tracing
- Trace LLM calls, tool executions, database queries
- Send traces to Jaeger or Azure Application Insights

**Benefit**: Easier debugging, performance insights
**Effort**: Medium (2-3 weeks)
**Risk**: Performance overhead, data volume

---

**Metrics Dashboard**:
- Grafana dashboard with key metrics:
  - Mission success rate
  - Average execution time
  - LLM token usage and cost
  - Tool usage patterns
  - Error rates by tool/category
- Alert on anomalies (spike in errors, high latency)

**Benefit**: Proactive issue detection, usage insights
**Effort**: Medium (3-4 weeks)
**Risk**: Dashboard maintenance overhead

---

**Session Replay**:
- Record full ReAct loop (thoughts, actions, observations)
- UI to replay session step-by-step for debugging
- Export to timeline visualization

**Benefit**: Better debugging, training data for improvements
**Effort**: Medium (3-4 weeks)
**Risk**: Storage cost for recordings

---

#### **Phase 6: Integrations**

**MCP (Model Context Protocol) Support**:
- Implement MCP client in `infrastructure/tools/mcp/`
- Allow agent to discover and use MCP servers (Playwright, Filesystem, etc.)
- Standard protocol for tool extensibility

**Benefit**: Ecosystem of tools, community contributions
**Effort**: High (4-6 weeks)
**Risk**: Protocol still evolving, breaking changes

---

**Slack/Teams Integration**:
- Chatbot interface for Slack/Microsoft Teams
- Users submit missions via chat
- Agent posts progress updates to thread
- Approve dangerous operations via button click

**Benefit**: Accessible interface, fits team workflows
**Effort**: Medium (3-4 weeks per platform)
**Risk**: Platform API rate limits, maintenance burden

---

**VS Code Extension**:
- VS Code extension to submit missions from IDE
- Inline code generation and editing
- View agent progress in sidebar

**Benefit**: Developer-friendly, tight integration
**Effort**: High (6-8 weeks)
**Risk**: Different tech stack (TypeScript), extension marketplace requirements

---

### **Technology Considerations**

#### **Alternative LLM Providers**

**Anthropic Claude**:
- Longer context windows (200K tokens)
- Better at following instructions (anecdotal)
- Already supported via LiteLLM

**Consideration**: Add Claude as model option in `llm_config.yaml`, compare performance with GPT-4.

---

**Local Models (Ollama, LM Studio)**:
- Run LLMs on-premise (no API costs)
- Data privacy (no external API calls)
- Limited by local GPU capacity

**Consideration**: Add Ollama support for air-gapped environments, document GPU requirements.

---

#### **Alternative Databases**

**Redis for State Caching**:
- Add Redis cache layer over `DbStateManager`
- Cache hot sessions (recently accessed)
- TTL-based eviction

**Benefit**: 10x faster state access for active sessions
**Effort**: Low (1-2 weeks)
**Trade-off**: Additional dependency, cache invalidation complexity

---

**DynamoDB for Serverless**:
- Replace PostgreSQL with DynamoDB for AWS Lambda deployment
- Pay-per-request pricing
- Infinite scalability

**Benefit**: True serverless, no database management
**Effort**: Medium (3-4 weeks)
**Trade-off**: Eventual consistency, limited query capabilities

---

#### **Alternative Deployment Platforms**

**AWS Lambda + API Gateway**:
- Serverless deployment
- Auto-scaling to zero
- Pay only for execution time

**Benefit**: Lower cost for low-traffic deployments
**Effort**: Medium (3-4 weeks)
**Trade-off**: Cold starts (5-10s), 15-minute execution limit

---

**Azure Container Apps**:
- Managed Kubernetes (simpler than AKS)
- Scale-to-zero capability
- Integrated Azure services

**Benefit**: Easier operations than Kubernetes
**Effort**: Low (1-2 weeks)
**Trade-off**: Azure vendor lock-in

---

### **Known Limitations (MVP)**

**1. No Parallel Tool Execution**:
- ReAct loop executes one tool at a time sequentially
- Independent operations (e.g., two API calls) can't run concurrently
- **Workaround**: None (planned for Phase 2)

**2. Limited Error Recovery**:
- Agent may get stuck if tool fails repeatedly
- No automatic fallback to alternative approaches
- **Workaround**: User must restart mission with refined prompt

**3. No Cost Guardrails**:
- Agent can consume unlimited LLM tokens
- No per-mission or per-user budget enforcement
- **Workaround**: Manual monitoring of token usage logs

**4. Single-Region Deployment**:
- No multi-region support for disaster recovery
- High latency for users far from deployment region
- **Workaround**: Deploy in user's closest region

**5. No Version Management**:
- No API versioning (/v1/ prefix exists but not enforced)
- Breaking changes will impact all clients
- **Workaround**: Careful backward compatibility, long deprecation periods

**6. Limited Observability**:
- Basic structured logging only
- No distributed tracing
- No metrics dashboard
- **Workaround**: Manual log analysis, external monitoring tools

---

### **Research Topics**

**1. Prompt Engineering Optimization**:
- **Question**: What prompt structure yields best task decomposition?
- **Approach**: A/B test different system prompts, measure success rate
- **Timeline**: Ongoing

**2. Tool Selection Strategy**:
- **Question**: Should agent decide tool before or after generating thought?
- **Current**: Tool selected based on thought content (sequential)
- **Alternative**: Parallel generation (thought + tool in single LLM call)
- **Approach**: Prototype alternative, benchmark latency and quality

**3. Context Window Management**:
- **Question**: What's the optimal message history window size?
- **Current**: Last 50 messages
- **Consideration**: Larger window = more context but higher cost and latency
- **Approach**: Experiment with 25, 50, 100 messages, measure impact

**4. State Compression**:
- **Question**: Can we use LLM to summarize old execution history?
- **Approach**: Periodically compress old observations into summary
- **Benefit**: Reduce state size while preserving essential context
- **Risk**: Information loss

---

### **Compliance & Governance**

**GDPR Compliance (if applicable)**:
- Right to erasure: Implement session deletion API
- Data portability: Export session data as JSON
- Audit logging: Track all data access
- Data retention: Auto-delete sessions after 90 days (configurable)

**SOC 2 Type II (future certification)**:
- Access controls: RBAC implementation
- Encryption: At rest and in transit
- Incident response: Document procedures
- Change management: Audit trail for code changes

**Industry-Specific**:
- **Healthcare (HIPAA)**: PHI handling, BAA requirements, audit logs
- **Finance (PCI DSS)**: No credit card data in state, secure API keys
- **Government (FedRAMP)**: Air-gapped deployment, US-based LLMs

---

### **Migration Path from Agent V2**

**For Existing Agent V2 Users**:

**Step 1: State Migration**:
```powershell
# Convert Agent V2 file states to Taskforce database
uv run python scripts/migrate_v2_states.py --source capstone/agent_v2/work_dir --target DATABASE_URL
```

**Step 2: Configuration Mapping**:
- Agent V2 `agent_factory` → Taskforce `configs/prod.yaml`
- V2 tool names preserved (no breaking changes)

**Step 3: CLI Compatibility Layer**:
- Taskforce CLI accepts same commands as Agent V2
- Alias `agent` → `taskforce` for backward compatibility

**Breaking Changes**:
- Session ID format changed (UUID4 vs custom)
- State schema: flat dict → versioned JSONB
- Tool parameter names may differ slightly

**Timeline**: Migration tool available in v1.0 beta

---

### **Success Metrics (Post-Launch)**

**Product Metrics**:
- Mission success rate: >80% (missions completed without error)
- Average execution time: <2 minutes per mission
- User retention: >60% weekly active users (WAU)

**Technical Metrics**:
- API uptime: >99.5% (staging), >99.9% (production)
- P95 latency: <10s per ReAct iteration
- Error rate: <5% of tool executions

**Business Metrics**:
- LLM cost per mission: <$0.50 (target for profitability)
- Infrastructure cost per user: <$10/month
- Support ticket volume: <10% of total missions

---

## Section 13: Glossary

Key terms and concepts used throughout this architecture:

---

### **Core Concepts**

**Agent**:
The core orchestrator implementing the ReAct (Reason + Act) execution loop. Coordinates LLM calls, tool execution, and state management to accomplish missions.

**Mission**:
A user-provided task description in natural language that the agent attempts to accomplish (e.g., "Create a Python web scraper").

**ReAct Loop**:
A reasoning pattern where the agent iteratively: (1) generates a **Thought** (reasoning), (2) decides an **Action** (tool call or decision), (3) observes the **Observation** (result), then repeats until mission complete.

**Session**:
A single execution instance with a unique ID, representing one mission execution from start to completion or failure.

**State**:
The persisted snapshot of a session at a point in time, including mission text, current status, answers, TodoList ID, and execution history.

**TodoList**:
A structured plan generated by the agent that breaks a mission into sequential tasks (TodoItems) with dependencies and acceptance criteria.

**TodoItem**:
A single actionable task within a TodoList, with a description, acceptance criteria, dependencies on other tasks, and execution status (pending, in_progress, completed, failed, skipped).

**Tool**:
An executable capability provided to the agent (e.g., PythonTool, FileReadTool, WebSearchTool). Tools implement the `ToolProtocol` interface with `execute()` method.

---

### **Architecture Patterns**

**Clean Architecture**:
A software architectural pattern emphasizing separation of concerns into concentric layers: Core (business logic), Infrastructure (adapters), Application (use cases), API (entrypoints). Dependencies point inward; outer layers depend on inner layers, never the reverse.

**Hexagonal Architecture (Ports & Adapters)**:
Alternative name for Clean Architecture. The "core" is the hexagon, "ports" are interfaces defining contracts, "adapters" are concrete implementations of ports.

**Protocol (Port)**:
In Python, a `typing.Protocol` defining a contract (interface) that concrete classes must implement. Used to define layer boundaries (e.g., `StateManagerProtocol`, `ToolProtocol`).

**Adapter**:
A concrete implementation of a Protocol. Example: `FileStateManager` and `DbStateManager` both implement `StateManagerProtocol`, allowing runtime swapping.

**Dependency Injection (DI)**:
A design pattern where dependencies are provided to a class rather than the class creating them. In Taskforce, the `AgentFactory` creates all dependencies and injects them into the `Agent`.

**Repository Pattern**:
An abstraction for data access that encapsulates the logic required to access data sources. `StateManager` acts as a repository for session state.

---

### **Technical Components**

**FastAPI**:
Modern Python web framework for building REST APIs with automatic validation, async support, and OpenAPI documentation generation.

**Typer**:
Python library for building CLI applications with type hints and automatic help text generation.

**LiteLLM**:
Unified interface for multiple LLM providers (OpenAI, Azure OpenAI, Anthropic, etc.), providing consistent API and retry logic.

**SQLAlchemy**:
Python SQL toolkit and Object-Relational Mapper (ORM) for database access with support for async operations.

**Alembic**:
Database migration tool for SQLAlchemy, managing schema version control and changes.

**structlog**:
Structured logging library that outputs machine-readable JSON logs with contextual information.

**Pydantic**:
Data validation library using Python type hints, used for API request/response validation and configuration management.

**asyncio**:
Python's built-in asynchronous I/O framework, enabling non-blocking concurrent operations.

**asyncpg**:
High-performance async PostgreSQL driver for Python.

**aiofiles**:
Async file I/O operations for Python.

**aiohttp**:
Async HTTP client/server library for Python.

**uv**:
Fast Python package installer and resolver, used as Taskforce's dependency management tool (replacement for pip/poetry).

---

### **Deployment Terms**

**Docker**:
Containerization platform that packages applications and dependencies into portable containers.

**Docker Compose**:
Tool for defining and running multi-container Docker applications using YAML configuration.

**Kubernetes (K8s)**:
Container orchestration platform for automating deployment, scaling, and management of containerized applications.

**PostgreSQL**:
Open-source relational database system used for production state persistence.

**PgBouncer**:
Connection pooler for PostgreSQL that reduces connection overhead and increases scalability.

**Nginx**:
High-performance web server and reverse proxy used for SSL termination and load balancing.

**Helm**:
Package manager for Kubernetes applications, used to deploy Taskforce charts.

**HPA (Horizontal Pod Autoscaler)**:
Kubernetes feature that automatically scales the number of pods based on CPU/memory utilization.

---

### **Testing Terms**

**Unit Test**:
Test of a single component in isolation with mocked dependencies. Fast and deterministic.

**Integration Test**:
Test of multiple components working together with real dependencies (e.g., actual database).

**E2E Test (End-to-End)**:
Test of complete user workflow from start to finish with all components running.

**Fixture**:
Reusable test setup code (pytest concept), providing mock objects, test data, or environment setup.

**Mock**:
Simulated object that mimics the behavior of real objects in controlled ways for testing.

**Coverage**:
Metric indicating the percentage of code executed during tests. Taskforce targets 80% for core layer.

**pytest**:
Python testing framework with fixture support, parameterization, and plugin ecosystem.

**Locust**:
Load testing tool for simulating many concurrent users, used for performance testing.

---

### **Domain Events**

**Thought**:
Immutable domain event representing the agent's reasoning step. Contains LLM-generated rationale for the next action.

**Action**:
Immutable domain event representing the agent's decision. Types: `tool_call`, `ask_user`, `complete`, `replan`.

**Observation**:
Immutable domain event representing the result of an action. Contains success status, output data, and any errors.

---

### **LLM Terms**

**Token**:
Unit of text processed by LLMs. Roughly 1 token = 4 characters or 0.75 words in English.

**Context Window**:
Maximum number of tokens an LLM can process in a single request (prompt + response). GPT-4: 8K-128K tokens depending on variant.

**Prompt**:
The input text sent to an LLM, typically including system instructions and user query.

**System Prompt**:
The first message in an LLM conversation, defining the AI's role, capabilities, and constraints.

**Temperature**:
LLM parameter controlling randomness in responses (0.0 = deterministic, 1.0 = creative). Default: 0.7.

**Top-p (Nucleus Sampling)**:
LLM parameter controlling diversity by sampling from the smallest set of tokens whose cumulative probability exceeds p. Default: 1.0.

**Completion**:
The output generated by an LLM in response to a prompt.

**Embedding**:
Vector representation of text, used for semantic similarity search. Typical dimension: 1536 (OpenAI ada-002).

---

### **RAG Terms**

**RAG (Retrieval Augmented Generation)**:
Technique combining semantic search (retrieval) with LLM generation. Agent searches documents, then uses retrieved content to answer questions.

**Azure AI Search**:
Microsoft's cloud search service with vector search capabilities, used for RAG document retrieval.

**Semantic Search**:
Search method using vector embeddings to find documents by meaning rather than exact keyword matches.

**Vector Search**:
Database query using vector similarity (e.g., cosine similarity) to find nearest neighbors in embedding space.

**Index**:
In Azure AI Search, a searchable collection of documents with defined schema and vector fields.

---

### **Security Terms**

**Bearer Token**:
Authentication method where client sends a token in the `Authorization: Bearer <token>` header.

**API Key**:
Secret string used to authenticate API requests. In Taskforce, stored in `TASKFORCE_API_KEY` environment variable.

**SSL/TLS**:
Protocols for encrypted communication over networks (HTTPS). TLS is the modern version of SSL.

**CORS (Cross-Origin Resource Sharing)**:
Security mechanism that allows or restricts web applications from making requests to different domains.

**RBAC (Role-Based Access Control)**:
Security model where permissions are assigned to roles, and users are assigned roles (e.g., admin, user, read-only).

**Secret Management**:
Practice of securely storing and accessing sensitive credentials (API keys, passwords). Taskforce uses environment variables (dev) and will use Azure Key Vault (prod).

**Prompt Injection**:
Security vulnerability where users craft inputs to manipulate LLM behavior, bypass restrictions, or extract system prompts.

---

### **Observability Terms**

**Structured Logging**:
Logging with machine-readable formats (JSON) containing key-value pairs for filtering and analysis.

**Trace**:
Record of a request's path through distributed systems, showing timing and dependencies.

**Metric**:
Quantitative measurement of system behavior (e.g., request latency, error rate, CPU usage).

**Health Check**:
Endpoint or probe that indicates whether a service is running and ready to accept requests.

**Liveness Probe**:
Health check indicating if a service is alive (vs. crashed). Kubernetes uses this to restart unhealthy pods.

**Readiness Probe**:
Health check indicating if a service is ready to accept traffic (e.g., database connected). Kubernetes uses this to route traffic.

---

### **Performance Terms**

**Latency**:
Time delay between request and response. Measured in milliseconds (ms) or seconds (s).

**Throughput**:
Number of requests processed per unit of time. Measured in requests per second (RPS) or transactions per minute (TPM).

**P95 Latency**:
95th percentile latency. If P95 = 500ms, 95% of requests complete in ≤500ms.

**Concurrency**:
Number of requests being processed simultaneously.

**Rate Limiting**:
Restricting the number of requests a client can make within a time window (e.g., 100 requests per minute).

**Connection Pool**:
Reusable set of database connections shared across requests, avoiding overhead of creating new connections.

**Async I/O**:
Non-blocking I/O operations that allow other code to run while waiting for I/O to complete.

---

### **Acronyms**

- **API**: Application Programming Interface
- **CLI**: Command-Line Interface
- **CRUD**: Create, Read, Update, Delete
- **DI**: Dependency Injection
- **E2E**: End-to-End
- **HTTP**: HyperText Transfer Protocol
- **HTTPS**: HTTP Secure
- **JSON**: JavaScript Object Notation
- **JSONB**: JSON Binary (PostgreSQL data type)
- **JWT**: JSON Web Token
- **K8s**: Kubernetes (8 characters between K and s)
- **LLM**: Large Language Model
- **MCP**: Model Context Protocol
- **MVP**: Minimum Viable Product
- **ORM**: Object-Relational Mapper
- **PoC**: Proof of Concept
- **RAG**: Retrieval Augmented Generation
- **RBAC**: Role-Based Access Control
- **REST**: Representational State Transfer
- **RPS**: Requests Per Second
- **SDK**: Software Development Kit
- **SQL**: Structured Query Language
- **SSE**: Server-Sent Events
- **SSL**: Secure Sockets Layer
- **TLS**: Transport Layer Security
- **TPM**: Tokens Per Minute (or Transactions Per Minute)
- **UI**: User Interface
- **URL**: Uniform Resource Locator
- **UX**: User Experience
- **UUID**: Universally Unique Identifier
- **WAU**: Weekly Active Users

---

## Conclusion

This architecture document defines the technical foundation for **Taskforce**, a production-ready AI agent framework built on Clean Architecture principles. By extracting and reorganizing code from the proven Agent V2 PoC while enforcing strict layer separation, Taskforce achieves:

**✅ Maintainability**: Clear component boundaries and protocol-based interfaces make the system easy to understand and modify.

**✅ Testability**: Dependency injection and layered architecture enable comprehensive unit, integration, and E2E testing.

**✅ Scalability**: Stateless API design, async I/O, and database-backed persistence support horizontal scaling from single instances to Kubernetes clusters.

**✅ Flexibility**: Protocol-based adapters allow runtime swapping of implementations (file vs. database state, OpenAI vs. Azure OpenAI) via configuration.

**✅ Security**: Multi-layer security controls including API authentication, input validation, tool sandboxing, and comprehensive audit logging.

### **Architecture Highlights**

1. **Four-Layer Clean Architecture**: Core (business logic) → Infrastructure (adapters) → Application (orchestration) → API (entrypoints) with strict inward-pointing dependencies.

2. **ReAct Execution Pattern**: Proven reasoning loop (Thought → Action → Observation) preserved from Agent V2 with improved state management.

3. **Dual Deployment Path**: Docker Compose for rapid development and staging, Kubernetes for production scale.

4. **Protocol-Driven Design**: Python Protocols define all layer boundaries, enabling flexible implementation swapping without core logic changes.

5. **Code Reuse Strategy**: Maximum extraction from Agent V2's working code (~11 tools, state management, LLM integration) into new architecture.

### **Implementation Roadmap**

**Phase 1 (MVP - 6-8 weeks)**:
- Core domain logic and protocols
- File and database state managers
- Native tools migration
- FastAPI REST API
- Typer CLI
- Docker Compose deployment

**Phase 2 (Production Hardening - 4-6 weeks)**:
- Kubernetes manifests
- Advanced observability (tracing, metrics)
- Load testing and optimization
- Security hardening

**Phase 3 (Advanced Features - Ongoing)**:
- Parallel task execution
- Cross-session memory
- Multi-agent orchestration
- MCP integration

### **Success Criteria**

This architecture will be considered successful if:

- **Feature Parity**: Matches Agent V2 capabilities (all tools, RAG support)
- **Performance**: <10s P95 latency per ReAct iteration, >99.5% uptime
- **Scalability**: Supports 50+ concurrent sessions per instance
- **Maintainability**: New developers onboard in <1 week
- **Extensibility**: New tools added in <1 day without core changes

### **Next Steps**

1. **Review**: Stakeholder review of architecture (Dev team, Security, Operations)
2. **Story Refinement**: Break down epics into detailed implementation stories
3. **Spike Work**: Prototype protocol-based tool execution to validate approach
4. **Implementation**: Begin Story 1.1 (Project Structure and Dependencies)

---

## Document Metadata

**Version**: 1.0  
**Status**: Draft  
**Last Updated**: 2025-11-22  
**Authors**: Architect Agent (Claude), Product Manager Agent  
**Reviewers**: TBD  
**Approval**: Pending  

**Related Documents**:
- [Product Requirements Document (PRD)](./prd.md)
- [Story Cards](./stories/)
- [Agent V2 Source Code](../../capstone/agent_v2/)
- [Project Rules](.cursor/rules/)

---

**End of Architecture Document**