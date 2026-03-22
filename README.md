# Taskforce

Production-grade multi-agent orchestration framework built with Clean Architecture principles.

## Quick Start

### 1. Install uv
```bash
# Install the uv package manager if you haven't already
pip install uv
```

### 2. Setup Environment
```bash
# Clone and enter the repo
cd pytaskforce

# Create virtual environment and install dependencies
uv venv .venv
source .venv/bin/activate        # Linux/macOS
# .\.venv\Scripts\Activate.ps1   # Windows PowerShell
uv sync

# Setup environment variables
cp .env.example .env
# Now edit .env and add your OPENAI_API_KEY
```

### 3. Run Your First Mission
```bash
# CLI Mode (default profile: butler)
taskforce run mission "Describe the current weather in Vienna"

# Interactive Chat
taskforce chat

# API Mode
uvicorn taskforce.api.server:app --reload
# Documentation: http://localhost:8000/docs
```

### 4. Load a Plugin (Optional)
```bash
# CLI: Load plugin directly
taskforce chat --plugin examples/accounting_agent

# Chat input — use Ctrl+Enter to send, Enter for new lines
# /plugins      — list available plugins
# /accounting_agent — switch to plugin agent
# /skills       — list available skills
# /context      — inspect LLM context and token estimates

# API: Plugins are automatically discovered and available via agent_id
# GET /api/v1/agents lists all agents including plugins
# POST /api/v1/execution/execute with agent_id: "accounting_agent"
```

---

## Features

- **Clean Architecture**: Strict layer separation (Core → Infrastructure → Application → API).
- **Multi-Agent Orchestration**: Delegate complex tasks to specialist sub-agents working in parallel.
- **Dual Interfaces**: Full-featured CLI (Typer) and REST API (FastAPI).
- **27 Native Tools**: File, shell, Git, web, browser, search, edit, LLM, memory, authentication, notifications, and more.
- **Swappable Persistence**: File-based for dev, PostgreSQL for production.
- **LLM Agnostic**: Multi-provider support (OpenAI, Anthropic, Google, Azure, Ollama) via LiteLLM.
- **Dynamic LLM Routing**: Use different models for planning, reasoning, acting, and summarizing phases.
- **Plugin System**: Load custom agent plugins with specialized tools.
- **Skills System**: Context, prompt, and agent-type skills for domain-specific capabilities.
- **Communication Gateway**: Unified inbound/outbound messaging for Telegram, MS Teams, Slack ([docs/integrations.md](docs/integrations.md)).
- **Butler Agent**: Event-driven personal assistant daemon with scheduling, rules, and Google Workspace integration.
- **Resumable HITL Workflows**: Durable wait/resume checkpoints with workflow APIs (`/api/v1/workflows/*`).
- **Long-Term Memory**: Session-persistent memory with human-like consolidation (forgetting curves, spaced repetition).
- **Enterprise Ready**: Optional `taskforce-enterprise` add-on for RBAC, multi-tenancy, and compliance.

## Enterprise Features (Optional)

Enterprise features are available as a separate package:

```bash
pip install taskforce-enterprise
# or
uv pip install taskforce-enterprise
```

After installation, enterprise features are **automatically activated** via the entry-point plugin system:

| Feature | Description |
|---------|-------------|
| **Multi-Tenant RBAC** | JWT/API-Key auth, roles, permissions |
| **Admin API** | User, role, tenant management under `/api/v1/admin/*` |
| **Policy Engine** | Fine-grained access control |
| **Audit Logging** | Compliance-level logging |
| **Evidence Tracking** | Citations and audit trails for RAG |

See [docs/features/enterprise.md](docs/features/enterprise.md) for details.

## Architecture Overview

Taskforce follows a strict Hexagonal/Clean Architecture pattern:

```
src/taskforce/
├── core/              # LAYER 1: Pure Domain Logic (Protocols, Agent, Plans)
├── infrastructure/    # LAYER 2: Adapters (DB, LLM, Tools, Memory)
├── application/       # LAYER 3: Use Cases (Factory, Executor, Profiles)
└── api/               # LAYER 4: Entrypoints (CLI, REST Routes)
```

## Multi-Agent Orchestration

Taskforce supports **multi-agent orchestration** via the `coding_agent` profile, which delegates complex missions to specialist sub-agents. Each sub-agent runs in isolation with its own tools and context.

### Quick Example

```bash
# Run with coding_agent profile (multi-agent orchestration)
taskforce run mission "Research Python FastAPI and React, create comparison docs" \
  --profile coding_agent
```

The coding agent orchestrator will:
1. Analyze the mission and break it down
2. Spawn specialist sub-agents in parallel:
   - **coding_planner**: Task decomposition and prioritization
   - **coding_worker**: Implementation with tooling access
   - **coding_reviewer**: Code review and quality checks
3. Combine results into final deliverable

### Available Sub-Agent Profiles

Built-in sub-agent profiles in `src/taskforce/configs/custom/`:

| Profile | Description |
|---------|-------------|
| `coding_planner` | Task decomposition and planning |
| `coding_worker` | Implementation with full tooling |
| `coding_reviewer` | Code review specialist |
| `code_reviewer` | Alternative code review agent |
| `test_engineer` | Test writing and validation |
| `doc_writer` | Documentation creation |
| `research_agent` | Web research and fact-checking |
| `doc-agent` | Document extraction/transformation |
| `pc-agent` | Windows system automation |
| `swe_analyzer` | SWE-Bench analysis |
| `swe_coder` | SWE-Bench solving |

### Custom Agent Example

Create `src/taskforce/configs/custom/security_auditor.yaml`:

```yaml
system_prompt: |
  You are a security audit expert. Check for:
  - Security vulnerabilities
  - OWASP Top 10 issues
  - Dependency risks

tools:
  - file_read
  - grep
  - glob
  - python
  - git
```

Then use it:

```bash
# Use directly
taskforce run mission "Review code security" --profile security_auditor
```

### How It Works

Orchestrator agents have access to the `call_agent` and `call_agents_parallel` tools:
- Creates isolated sub-agents with their own session IDs
- Supports parallel execution of multiple sub-agents
- Handles context isolation (no cross-contamination)
- Returns aggregated results to the orchestrator

See [docs/architecture/multi-agent-orchestration-plan.md](docs/architecture/multi-agent-orchestration-plan.md) for implementation details.

## Epic Orchestration

Taskforce includes an epic orchestration system for complex, multi-step tasks using planner/worker/judge roles. Configuration is done via the `orchestration.auto_epic` section in profile YAML:

```yaml
orchestration:
  auto_epic:
    enabled: true
    confidence_threshold: 0.7
    default_worker_count: 3
    default_max_rounds: 3
```

See [Epic Orchestration docs](docs/architecture/epic-orchestration.md) for full configuration options.

---

## Butler Agent (Event-Driven)

The Butler is a proactive, event-driven agent daemon that runs 24/7 as a personal assistant. It is the **default profile** for Taskforce.

```bash
# Start the butler daemon
taskforce start                    # shortcut
taskforce butler start --profile butler

# Check status
taskforce status                   # shortcut
taskforce butler status

# Stop the butler
taskforce stop
```

The Butler integrates with Google Calendar, Gmail, Google Drive, and supports scheduled jobs, trigger rules, and proactive notifications. See [ADR-010](docs/adr/adr-010-event-driven-butler-agent.md).

### Butler Roles

Specialized butler personas are available:

- `butler_roles/accountant` — Financial document processing
- `butler_roles/personal_assistant` — General personal assistant

---

## Documentation & Next Steps

Detailed guides are available in the [docs/](docs/) directory:

- **[Setup & Installation](docs/setup.md)**: Environment setup guide.
- **[CLI Guide](docs/cli.md)**: Master the `taskforce` command.
- **[REST API Guide](docs/api.md)**: Integrating Taskforce via FastAPI.
- **[Profiles & Config](docs/profiles.md)**: Configuration profiles and settings.
- **[Plugin Development](docs/plugins.md)**: Creating custom agent plugins.
- **[Skills System](docs/features/skills.md)**: Context, prompt, and agent-type skills.
- **[Long-Term Memory](docs/features/longterm-memory.md)**: Memory with human-like consolidation.
- **[External Integrations](docs/integrations.md)**: Telegram, Teams, Google Workspace.
- **[Architecture Overview](docs/architecture.md)**: Design principles and layers.
- **[ADR Index](docs/adr/index.md)**: Architecture Decision Records.

---

## Development

### Install Dev Dependencies
```bash
uv sync --group dev
```

### Run Tests
```bash
uv run pytest
uv run pytest --cov=taskforce --cov-report=html
```

### Code Quality
```bash
uv run black src/taskforce tests
uv run ruff check src/taskforce tests
uv run mypy src/taskforce
```

### Optional Dependency Groups
```bash
uv sync --extra browser           # Playwright browser automation
uv sync --extra rag               # Azure AI Search
uv sync --extra pdf               # PDF processing
uv sync --extra personal-assistant # Google Calendar/API
uv sync --extra postgres           # PostgreSQL persistence
uv sync --extra tokenizer          # Tiktoken token counting
uv sync --extra tracing            # Arize Phoenix OTEL tracing
uv sync --extra auth               # Cryptography for authentication
uv sync --extra evals              # Inspect AI + SWE-Bench evaluation
```

## License
MIT - see [LICENSE](LICENSE) for details.
