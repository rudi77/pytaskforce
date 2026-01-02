# Section 3: Tech Stack

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
| **MCP Integration** | mcp (Python SDK) | latest | Model Context Protocol client | Connects to external MCP servers (stdio/SSE); enables tool composition from external providers |
| **Node.js Runtime** | Node.js | 20+ | MCP server execution | Required for running official MCP servers (e.g., @modelcontextprotocol/server-filesystem) |

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


---

### **Model Context Protocol (MCP) Integration**

**Overview:**
Taskforce integrates with the Model Context Protocol (MCP) to enable dynamic tool composition from external providers. MCP allows the agent to connect to specialized servers that expose tools via a standardized protocol.

**Supported Connection Types:**
1. **stdio**: Local servers launched as subprocesses (e.g., filesystem, database tools)
2. **SSE**: Remote servers accessed via Server-Sent Events (future support)

**Configuration Example (configs/dev.yaml):**

```yaml
mcp_servers:
  # Official MCP Filesystem Server
  - type: stdio
    command: npx
    args:
      - "-y"  # Auto-install if not present
      - "@modelcontextprotocol/server-filesystem"
      - ".mcp_test_data"  # Allowed directory (security boundary)
    env: {}  # Optional environment variables
```

**Available Official MCP Servers:**
- `@modelcontextprotocol/server-filesystem`: File operations (read, write, list, search)
- `@modelcontextprotocol/server-github`: GitHub API integration
- `@modelcontextprotocol/server-postgres`: PostgreSQL database operations
- `@modelcontextprotocol/server-brave-search`: Web search via Brave API

**Tool Precedence:**
When MCP tools overlap with native tools (e.g., both provide `read_file`), the agent can use either based on context. Native tools are registered first, MCP tools are appended. The LLM chooses the most appropriate tool for each task.

**Security Considerations:**
- MCP filesystem server enforces directory boundaries (only accesses configured paths)
- Environment variables can pass API keys securely
- Each server runs in isolated subprocess with limited permissions

**Requirements:**
- Node.js 20+ (for running official MCP servers via npx)
- Python `mcp` SDK (installed via `uv add mcp`)

**Validation:**
See `test_mcp_validation.py` for end-to-end integration tests.

---

