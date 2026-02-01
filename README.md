# Taskforce

Production-grade multi-agent orchestration framework built with Clean Architecture principles.

## 🚀 Quick Start (Windows/PowerShell)

### 1. Install uv
```powershell
# Install the uv package manager if you haven't already
pip install uv
```

### 2. Setup Environment
```powershell
# Clone and enter the repo
# cd pytaskforce

# Create virtual environment and install dependencies
uv venv .venv
.\.venv\Scripts\Activate.ps1
uv sync

# Setup environment variables
Copy-Item .env.example .env
# Now edit .env and add your OPENAI_API_KEY
```

### 3. Run Your First Mission
```powershell
# CLI Mode
taskforce run mission "Describe the current weather in Vienna"

# API Mode
uvicorn taskforce.api.server:app --reload
# Documentation: `http://localhost:8000/docs`
```

### 4. Load a Plugin (Optional)
```powershell
# CLI: Load plugin directly
taskforce chat --plugin examples/accounting_agent

# Chat input
# Use Ctrl+Enter to send, Enter for new lines (multi-line input supported)
# List plugins and switch via slash commands
# /plugins
# /accounting_agent

# API: Plugins are automatically discovered and available via agent_id
# GET /api/v1/agents lists all agents including plugins
# POST /api/v1/execution/execute with agent_id: "accounting_agent"
```

---

## 📦 Features

- **Clean Architecture**: Strict layer separation (Core → Application → Infrastructure → API).
- **Multi-Agent Orchestration**: Delegate complex tasks to specialist sub-agents working in parallel.
- **Dual Interfaces**: Full-featured CLI (Typer) and REST API (FastAPI).
- **Swappable Persistence**: File-based for dev, PostgreSQL for production.
- **LLM Agnostic**: Support for OpenAI, Azure OpenAI, and more via LiteLLM.
- **Plugin System**: Load custom agent plugins with specialized tools.
- **Communication Integrations**: Inbound messaging endpoints for Telegram/MS Teams with session-bound chat history ([docs/integrations.md](docs/integrations.md)).
- **Skill Metadata**: Optional skill frontmatter fields (license, compatibility, allowed tools, metadata) show up in `taskforce skills show --full`.
- **Advanced Tools**: Python, Git, RAG (Azure AI Search), and web search.
- **Long-Term Memory**: Session-persistent knowledge graphs via MCP Memory Server.
- **Enterprise Ready**: Optional `taskforce-enterprise` Add-on for RBAC, multi-tenancy, and compliance.

## 🏢 Enterprise Features (Optional)

Enterprise-Features sind als separates Paket verfügbar:

```powershell
# Installation mit Enterprise-Features
pip install taskforce-enterprise
# oder
uv pip install taskforce-enterprise
```

Nach der Installation werden Enterprise-Features **automatisch aktiviert** (Entry-Point-basiertes Plugin-System):

| Feature | Beschreibung |
|---------|--------------|
| **Multi-Tenant RBAC** | JWT/API-Key Auth, Rollen, Berechtigungen |
| **Admin API** | User-, Rollen-, Tenant-Management unter `/api/v1/admin/*` |
| **Policy Engine** | Feingranulare Zugriffskontrolle |
| **Audit Logging** | Compliance-konforme Protokollierung |
| **Evidence Tracking** | Zitationen und Audit-Trails für RAG |

Siehe [docs/features/enterprise.md](docs/features/enterprise.md) für Details.

## 🧠 Architecture Overview

Taskforce follows a strict Hexagonal/Clean Architecture pattern:

```
taskforce/
├── src/taskforce/
│   ├── core/              # LAYER 1: Pure Domain Logic (Protocols, Agent, Plans)
│   ├── infrastructure/    # LAYER 2: Adapters (DB, LLM, Tools, Memory)
│   ├── application/       # LAYER 3: Use Cases (Factory, Executor, Profiles)
│   └── api/               # LAYER 4: Entrypoints (CLI, REST Routes)
```

## 🤝 Multi-Agent Orchestration

Taskforce supports **multi-agent orchestration**, allowing you to delegate complex missions to specialist sub-agents. Each sub-agent runs in isolation with its own tools and context.

### Quick Example

```powershell
# Run with orchestrator profile
taskforce run mission "Research Python FastAPI and React, create comparison docs" \
  --profile orchestrator
```

The orchestrator agent will:
1. Analyze the mission and break it down
2. Spawn specialist sub-agents in parallel:
   - **Coding Agent**: Research FastAPI best practices
   - **Coding Agent**: Research React patterns
   - **Doc Writer Agent**: Create comparison documentation
3. Combine results into final deliverable

### Available Specialist Agents

- **`coding`**: File operations, shell commands, Git operations
- **`rag`**: Semantic search, document retrieval
- **`wiki`**: Wikipedia research
- **Custom agents**: Create your own in `configs/custom/`

### Custom Agent Example

Create `configs/custom/code_reviewer.yaml`:

```yaml
system_prompt: |
  You are a code review expert. Check for:
  - Security vulnerabilities
  - Performance issues
  - Code quality

tool_allowlist:
  - file_read
  - python
  - git_tool
```

Then use it:

```powershell
# Use directly
taskforce run mission "Review code quality" --profile code_reviewer

# Or via orchestrator
taskforce run mission "Get expert code review for src/" --profile orchestrator
# Orchestrator will automatically call code_reviewer specialist
```

### How It Works

Orchestrator agents have access to the `call_agent` tool, which:
- Creates isolated sub-agents with their own session IDs
- Supports parallel execution of multiple sub-agents
- Handles context isolation (no cross-contamination)
- Returns aggregated results to the orchestrator

See [docs/architecture/multi-agent-orchestration-plan.md](docs/architecture/multi-agent-orchestration-plan.md) for implementation details.

## 🧩 Epic Orchestration (Planner → Workers → Judge)

Taskforce can run epic-scale workflows where a planner creates tasks, workers execute
them in parallel, and a judge consolidates results and optionally commits changes.

```powershell
taskforce epic run "Implement epic: billing export overhaul" `
  --scope "backend export pipeline" `
  --scope "frontend export UI" `
  --workers 4 `
  --rounds 3 `
  --auto-commit `
  --commit-message "Epic: billing export overhaul"
```

---

## 📚 Documentation & Next Steps

Detailed guides are available in the [docs/](docs/) directory:

- **[Quickstart & Setup](docs/setup.md)**: Detailed environment setup.
- **[Architecture Deep Dive](docs/index.md)**: Understanding the layers.
- **[CLI Guide](docs/cli.md)**: Master the `taskforce` command.
- **[REST API Guide](docs/api.md)**: Integrating Taskforce into your apps (includes plugin support).
- **[Plugin Development](docs/plugins.md)**: Creating and using custom agent plugins.
- **[Profiles & Config](docs/profiles.md)**: Managing dev/prod environments.
- **[Long-Term Memory](docs/features/longterm-memory.md)**: Session-persistent knowledge graphs.
- **[Multi-Agent Orchestration](docs/architecture/multi-agent-orchestration-plan.md)**: Deep dive into orchestration.

---

## 🛠 Development

### Run Tests
```powershell
uv run pytest
uv run pytest --cov=taskforce --cov-report=html
```

### Code Quality
```powershell
uv run black src/taskforce tests
uv run ruff check src/taskforce tests
uv run mypy src/taskforce
```

## 📜 License
MIT - see [LICENSE](LICENSE) for details.
