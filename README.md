# Taskforce

Production-grade multi-agent orchestration framework built with Clean Architecture principles.

## Overview

Taskforce is a refactored and production-ready version of Agent V2, designed for enterprise deployment with:

- **Clean Architecture**: Strict layer separation (Core → Application → Infrastructure → API)
- **Protocol-based Design**: Swappable implementations for state management, LLM providers, and tools
- **Dual Interfaces**: CLI (Typer + Rich) and REST API (FastAPI)
- **Production Persistence**: PostgreSQL with SQLAlchemy for state management (or file-based for dev)
- **RAG Capabilities**: Azure AI Search integration for semantic search

## Architecture

```
taskforce/
├── src/taskforce/
│   ├── core/              # Domain logic (pure Python, no dependencies)
│   │   ├── domain/        # Agent, PlanGenerator, Domain Events
│   │   ├── interfaces/    # Protocols (StateManager, LLM, Tool)
│   │   └── prompts/       # System prompts and templates
│   ├── infrastructure/    # External integrations
│   │   ├── persistence/   # File and DB state managers
│   │   ├── llm/           # LiteLLM service (OpenAI, Azure)
│   │   ├── tools/         # Native, RAG, and MCP tools
│   │   └── memory/        # Memory management
│   ├── application/       # Use cases and orchestration
│   │   ├── factory.py     # Dependency injection
│   │   ├── executor.py    # Execution orchestration
│   │   └── profiles.py    # Configuration management
│   └── api/               # Entrypoints
│       ├── cli/           # Typer CLI
│       └── routes/        # FastAPI REST endpoints
├── tests/
│   ├── unit/              # Core domain tests
│   ├── integration/       # Infrastructure tests
│   └── fixtures/          # Test data and mocks
└── docs/                  # Architecture, PRD, stories
```

## Prerequisites

- **Python**: 3.11 or higher
- **Package Manager**: `uv` (not pip/venv)

## Setup

### 1. Install uv

```powershell
# Windows (PowerShell)
pip install uv
```

### 2. Create Virtual Environment and Install Dependencies

```powershell
cd taskforce
uv venv .venv
.\.venv\Scripts\Activate.ps1
uv sync
```

### 3. Configure Environment Variables

```powershell
# Copy example environment file
cp .env.example .env

# Edit .env and set required variables:
# - OPENAI_API_KEY (required for LLM calls)
# - GITHUB_TOKEN (optional, for GitHub API operations)
# - DATABASE_URL (optional, for production PostgreSQL)
```

## Usage

Taskforce can be used either as a Command Line Interface (CLI) tool or as a REST API service.

### CLI Tool

The `taskforce` command is available after activating the virtual environment.

```powershell
# Activate virtual environment first
.\.venv\Scripts\Activate.ps1

# Show help and available commands
taskforce --help

# Run a mission
taskforce run mission "Analyze sales data and create visualization"

# Run a mission with specific profile and session resumption
taskforce run mission "Analyze data" --profile dev --session <session-id>

# Interactive chat mode
taskforce chat

# Manage Tools
taskforce tools list
taskforce tools inspect python

# Manage Sessions
taskforce sessions list
taskforce sessions show <session-id>

# View Configuration
taskforce config show
```

### REST API Service

The REST API allows you to integrate the agent into other applications.

#### Start the Server

```powershell
# Start API server using uvicorn
uvicorn taskforce.api.server:app --host 0.0.0.0 --port 8000 --reload

# Access API Documentation
# http://localhost:8000/docs (Swagger UI)
# http://localhost:8000/redoc (ReDoc)
```

#### Key Endpoints

- **Execute Mission**: `POST /api/v1/execution/execute`
  - Body: `{"mission": "...", "profile": "dev"}`
  - Returns: Final result and session ID.

- **Execute Mission (Streaming)**: `POST /api/v1/execution/execute/stream`
  - Body: `{"mission": "...", "profile": "dev"}`
  - Returns: Server-Sent Events (SSE) stream of progress updates.

- **Manage Sessions**:
  - `GET /api/v1/sessions`: List all sessions.
  - `GET /api/v1/sessions/{session_id}`: Get session details.
  - `POST /api/v1/sessions`: Create a new session.

- **Health Check**: `GET /health`

## Development

### Run Tests

```powershell
# All tests
uv run pytest

# Unit tests only
uv run pytest tests/unit

# With coverage
uv run pytest --cov=taskforce --cov-report=html

# View coverage report
start htmlcov/index.html
```

### Code Quality

```powershell
# Format code
uv run black src/taskforce tests

# Lint code
uv run ruff check src/taskforce tests

# Type checking
uv run mypy src/taskforce
```

## Configuration Profiles

Taskforce supports multiple deployment profiles loaded from `configs/{profile}.yaml`:

- **dev**: File-based state, local LLM/OpenAI, verbose logging
- **staging**: PostgreSQL state, cloud LLM, structured logging
- **prod**: PostgreSQL state, cloud LLM, JSON logging, monitoring

## License

MIT License - see LICENSE file for details
