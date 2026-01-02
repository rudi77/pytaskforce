# Story 1.14: Add Deployment Infrastructure and Documentation

**Epic**: Build Taskforce Production Framework with Clean Architecture  
**Story ID**: 1.14  
**Status**: Pending  
**Priority**: Medium  
**Estimated Points**: 3  
**Dependencies**: All previous stories (1.1-1.13)

---

## User Story

As a **developer**,  
I want **Docker containerization and comprehensive documentation**,  
so that **Taskforce can be deployed to production environments**.

---

## Acceptance Criteria

1. ✅ Create `taskforce/Dockerfile` with multi-stage build (builder + runtime)
2. ✅ Create `taskforce/docker-compose.yml` for local development (taskforce service + postgres)
3. ✅ Create `taskforce/.dockerignore` excluding unnecessary files
4. ✅ Create configuration profiles:
   - `configs/dev.yaml` - File persistence, OpenAI, debug logging
   - `configs/staging.yaml` - PostgreSQL, Azure OpenAI, info logging
   - `configs/prod.yaml` - PostgreSQL with pooling, Azure OpenAI, warning logging
5. ✅ Update `taskforce/README.md` with:
   - Architecture overview with layer diagram
   - Setup instructions (local dev, Docker, production)
   - Configuration guide (profiles, environment variables)
   - Usage examples (CLI commands, API calls)
6. ✅ Create `taskforce/docs/architecture.md` with Clean Architecture explanation
7. ✅ Create `taskforce/docs/deployment.md` with Kubernetes deployment guide
8. ✅ Verify Docker build succeeds and container runs successfully

---

## Integration Verification

- **IV1: Existing Functionality Verification** - Agent V2 deployment remains independent
- **IV2: Integration Point Verification** - Dockerized Taskforce executes missions identically to local Taskforce
- **IV3: Performance Impact Verification** - Container startup time <10 seconds, ready to accept requests

---

## Technical Notes

**Dockerfile:**

```dockerfile
# taskforce/Dockerfile
# Multi-stage build for production deployment

# Stage 1: Builder
FROM python:3.11-slim as builder

WORKDIR /app

# Install uv package manager
RUN pip install --no-cache-dir uv

# Copy dependency files
COPY pyproject.toml uv.lock* ./

# Install dependencies
RUN uv sync --frozen --no-dev

# Stage 2: Runtime
FROM python:3.11-slim

WORKDIR /app

# Install runtime dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    git \
    && rm -rf /var/lib/apt/lists/*

# Copy virtual environment from builder
COPY --from=builder /app/.venv /app/.venv

# Copy application code
COPY src/ /app/src/
COPY configs/ /app/configs/
COPY alembic/ /app/alembic/
COPY alembic.ini /app/

# Set environment variables
ENV PATH="/app/.venv/bin:$PATH"
ENV PYTHONPATH="/app/src:$PYTHONPATH"
ENV TASKFORCE_PROFILE=prod

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "import requests; requests.get('http://localhost:8000/health')"

# Expose API port
EXPOSE 8000

# Default command: run API server
CMD ["uvicorn", "taskforce.api.server:app", "--host", "0.0.0.0", "--port", "8000"]
```

**Docker Compose:**

```yaml
# taskforce/docker-compose.yml
version: '3.8'

services:
  postgres:
    image: postgres:15-alpine
    environment:
      POSTGRES_DB: taskforce
      POSTGRES_USER: taskforce
      POSTGRES_PASSWORD: taskforce_dev
    ports:
      - "5432:5432"
    volumes:
      - postgres_data:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U taskforce"]
      interval: 10s
      timeout: 5s
      retries: 5

  taskforce:
    build:
      context: .
      dockerfile: Dockerfile
    environment:
      DATABASE_URL: postgresql+asyncpg://taskforce:taskforce_dev@postgres:5432/taskforce
      OPENAI_API_KEY: ${OPENAI_API_KEY}
      TASKFORCE_PROFILE: dev
    ports:
      - "8000:8000"
    depends_on:
      postgres:
        condition: service_healthy
    volumes:
      - ./src:/app/src  # Mount for development
      - ./configs:/app/configs
    command: uvicorn taskforce.api.server:app --host 0.0.0.0 --port 8000 --reload

volumes:
  postgres_data:
```

**.dockerignore:**

```
# taskforce/.dockerignore
__pycache__/
*.py[cod]
*$py.class
*.so
.Python
.venv/
env/
venv/
.git/
.gitignore
.pytest_cache/
.coverage
htmlcov/
dist/
build/
*.egg-info/
.DS_Store
tests/
docs/stories/
*.md
!README.md
```

**Configuration Profiles:**

```yaml
# taskforce/configs/dev.yaml
persistence:
  type: file
  work_dir: .taskforce_dev

llm:
  config_path: configs/llm_config.yaml
  default_model: fast

logging:
  level: DEBUG
  format: console
  structured: false

server:
  host: 0.0.0.0
  port: 8000
  reload: true
```

```yaml
# taskforce/configs/prod.yaml
persistence:
  type: database
  db_url_env: DATABASE_URL
  pool_size: 20
  max_overflow: 10

llm:
  config_path: configs/llm_config.yaml
  default_model: powerful

rag:
  endpoint_env: AZURE_SEARCH_ENDPOINT
  api_key_env: AZURE_SEARCH_API_KEY
  index_name: production-docs

logging:
  level: WARNING
  format: json
  structured: true

server:
  host: 0.0.0.0
  port: 8000
  reload: false
  workers: 4
```

**README.md:**

```markdown
# Taskforce - Production-Ready ReAct Agent Framework

Taskforce is a production-ready AI agent framework implementing Clean Architecture principles with ReAct (Reasoning + Acting) capabilities, TodoList planning, and extensible tool execution.

## Architecture

Taskforce follows a **four-layer Clean Architecture**:

```
┌─────────────────────────────────────────┐
│          API Layer (Entrypoints)        │
│   FastAPI REST API │ Typer CLI          │
├─────────────────────────────────────────┤
│    Application Layer (Orchestration)    │
│  AgentFactory │ AgentExecutor │ Profiles│
├─────────────────────────────────────────┤
│   Infrastructure Layer (Adapters)       │
│ Persistence │ LLM │ Tools │ Memory      │
├─────────────────────────────────────────┤
│     Core Layer (Business Logic)         │
│  ReAct Agent │ TodoList │ Protocols     │
└─────────────────────────────────────────┘
```

## Quick Start

### Local Development

```powershell
# Clone and setup
cd taskforce
uv sync

# Run CLI
taskforce run mission "Create a Python hello world function"

# Run API server
taskforce-server
```

### Docker

```powershell
# Start services (API + PostgreSQL)
docker-compose up

# Execute mission via API
curl -X POST http://localhost:8000/api/v1/execute \
  -H "Content-Type: application/json" \
  -d '{"mission": "Create a hello world function", "profile": "dev"}'
```

## Documentation

- [Architecture Guide](docs/architecture.md)
- [Deployment Guide](docs/deployment.md)
- [API Documentation](http://localhost:8000/docs) (when server running)
- [Story Cards](docs/stories/)

## Configuration

Taskforce supports three configuration profiles:

- **dev**: File-based persistence, OpenAI direct, debug logging
- **staging**: PostgreSQL, Azure OpenAI, info logging
- **prod**: PostgreSQL with pooling, Azure OpenAI, minimal logging

Select profile via `--profile` flag or `TASKFORCE_PROFILE` environment variable.

## Environment Variables

Required:
- `OPENAI_API_KEY` - OpenAI API key for LLM access

Optional:
- `AZURE_OPENAI_API_KEY` - Azure OpenAI API key
- `AZURE_OPENAI_ENDPOINT` - Azure OpenAI endpoint URL
- `DATABASE_URL` - PostgreSQL connection string (production)
- `TASKFORCE_PROFILE` - Configuration profile (dev/staging/prod)

## License

[Your License]
```

**Deployment Guide:**

```markdown
# taskforce/docs/deployment.md
# Taskforce Deployment Guide

## Kubernetes Deployment

### Prerequisites
- Kubernetes cluster (1.24+)
- PostgreSQL database
- Azure OpenAI or OpenAI API access

### Deploy to Kubernetes

```yaml
# taskforce-deployment.yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: taskforce
spec:
  replicas: 3
  selector:
    matchLabels:
      app: taskforce
  template:
    metadata:
      labels:
        app: taskforce
    spec:
      containers:
      - name: taskforce
        image: your-registry/taskforce:latest
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
        - name: TASKFORCE_PROFILE
          value: "prod"
        livenessProbe:
          httpGet:
            path: /health
            port: 8000
          initialDelaySeconds: 10
          periodSeconds: 30
        readinessProbe:
          httpGet:
            path: /health/ready
            port: 8000
          initialDelaySeconds: 5
          periodSeconds: 10
        resources:
          requests:
            cpu: "500m"
            memory: "512Mi"
          limits:
            cpu: "2000m"
            memory: "2Gi"
```

Apply:
```bash
kubectl apply -f taskforce-deployment.yaml
```

## Monitoring

- Logs: `kubectl logs -f deployment/taskforce`
- Health: `kubectl get pods -w`
- Metrics: Prometheus integration (future)
```

---

## Testing Strategy

```python
# tests/integration/test_docker_deployment.py
import subprocess
import requests
import time

def test_docker_build_succeeds():
    """Verify Docker image builds successfully."""
    result = subprocess.run(
        ["docker", "build", "-t", "taskforce:test", "."],
        cwd="taskforce",
        capture_output=True
    )
    assert result.returncode == 0

def test_docker_container_starts():
    """Verify container starts and serves requests."""
    # Start container
    subprocess.run([
        "docker", "run", "-d",
        "--name", "taskforce-test",
        "-p", "8001:8000",
        "-e", "TASKFORCE_PROFILE=dev",
        "taskforce:test"
    ])
    
    # Wait for startup
    time.sleep(5)
    
    try:
        # Check health endpoint
        response = requests.get("http://localhost:8001/health")
        assert response.status_code == 200
        assert response.json()["status"] == "healthy"
    finally:
        # Cleanup
        subprocess.run(["docker", "stop", "taskforce-test"])
        subprocess.run(["docker", "rm", "taskforce-test"])
```

---

## Definition of Done

- [ ] Dockerfile with multi-stage build created
- [ ] docker-compose.yml for local dev environment
- [ ] .dockerignore configured
- [ ] Configuration profiles created (dev/staging/prod)
- [ ] README.md with comprehensive setup instructions
- [ ] docs/architecture.md with Clean Architecture explanation
- [ ] docs/deployment.md with Kubernetes guide
- [ ] Docker build succeeds
- [ ] Container starts and serves requests
- [ ] Container startup time <10 seconds
- [ ] Code review completed
- [ ] Code committed to version control

