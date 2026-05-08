# Taskforce

Production-grade multi-agent orchestration framework built with **hexagonal (clean) architecture** principles.

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
# CLI Mode — default profile is 'butler' if taskforce-butler is installed,
# otherwise 'dev'. Override any time with --profile <name>.
taskforce run mission "Describe the current weather in Vienna"

# Interactive Chat
taskforce chat

# API Mode
uvicorn taskforce.api.server:app --reload
# Documentation: http://localhost:8000/docs
```

### 3a. Install Optional Agent Packages
```bash
# Enable butler (daemon + Google Workspace tools + scheduler)
uv pip install -e agents/butler

# Enable coding orchestration (epic pipeline, coding_agent profile)
uv pip install -e agents/coding-agent

# Enable RAG tools (rag_agent profile)
uv pip install -e agents/rag-agent
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
# /tree         — show LLM context as tree (mirrors API call structure)
# /write-tree   — dump full LLM context to tree.md

# API: Plugins are automatically discovered and available via agent_id
# GET /api/v1/agents lists all agents including plugins
# POST /api/v1/execution/execute with agent_id: "accounting_agent"
# POST /api/v1/agents/{agent_id}/deploy to queue agent deployments
# GET /api/v1/agents/{agent_id}/active for deployment status
```

---

## Features

- **Clean Architecture**: Strict layer separation (Core → Infrastructure → Application → API).
- **Multi-Package Design**: Lean core framework (`taskforce`) plus optional agent packages
  (`taskforce-butler`, `taskforce-coding-agent`, `taskforce-rag-agent`) wired together by a
  unified CLI (`taskforce-cli`).
- **Multi-Agent Orchestration**: Delegate complex tasks to specialist sub-agents, in parallel
  (`call_agents_parallel`) or across the network via ACP (`call_acp_agent`).
- **Dual Interfaces**: Full-featured CLI (Typer) and REST API (FastAPI).
- **Rich Tool Registry**: 20+ framework-native tools (file, shell, Git, web, browser, search,
  edit, LLM, memory, notifications, Office, accounting, …) plus tools contributed by agent
  packages (Gmail, Google Drive, Calendar, scheduler, RAG).
- **Swappable Persistence**: File-based for dev, PostgreSQL for production.
- **LLM Agnostic**: Multi-provider support (OpenAI, Anthropic, Google, Azure, Ollama) via LiteLLM.
- **Dynamic LLM Routing**: Use different models for planning, reasoning, acting, and summarizing phases.
- **Plugin System**: Load custom agent plugins with specialized tools.
- **Skills System**: Context, prompt, and agent-type skills for domain-specific capabilities.
- **Communication Gateway**: Unified inbound/outbound messaging for Telegram, MS Teams, Slack ([docs/integrations.md](docs/integrations.md)).
- **Butler Agent** (optional): Event-driven personal assistant daemon with scheduling, rules,
  and Google Workspace integration — shipped in the `taskforce-butler` package.
- **Persistent Agents**: Sessionless orchestrator architecture with durable conversations (ADR-016).
- **First-Class Workflows**: Durable wait/resume checkpoints plus stored workflow definitions that can be run through `/api/v1/workflows/*`.
- **Long-Term Memory**: Session-persistent memory with human-like consolidation (forgetting curves, spaced repetition) and a generative dreaming engine (ADR-014).
- **ACP Support**: Remote-agent invocation over the Agent Communication Protocol (ADR-018).
- **Enterprise Integration Surface**: Core contains stable interfaces/stubs and middleware seams for enterprise extensions maintained in separate repositories.

## Enterprise Integration (separate repository)

Enterprise product features were moved to a dedicated repository. The OSS core keeps only the integration seams:

- interface protocols/stubs under `src/taskforce/core/interfaces/`
- plugin discovery + middleware hooks
- UI plugin manifest endpoint: `GET /api/v1/ui/manifest`

This means `pytaskforce` stays lightweight while allowing enterprise packages to plug in cleanly without forking the core.

## Architecture Overview

Taskforce is organized as a multi-package monorepo. The framework is the lean
core; agent-specific capabilities are shipped as optional packages that are
discovered at runtime.

```
pytaskforce/
├── src/taskforce/          # Core framework (Core → Infrastructure → Application → API)
├── cli/src/taskforce_cli/  # Unified CLI (discovers installed agent packages)
├── agents/
│   ├── butler/             # taskforce_butler — daemon, scheduler, rules, GSuite tools
│   ├── coding-agent/       # taskforce_coding_agent — epic orchestration, sub-agents
│   └── rag-agent/          # taskforce_rag_agent — Azure AI Search tools
├── examples/               # Example plugin agents
└── docs/                   # Markdown documentation
```

## Multi-Agent Orchestration

Taskforce supports **multi-agent orchestration** via the `coding_agent` profile
(shipped in `taskforce-coding-agent`), which delegates complex missions to
specialist sub-agents. Each sub-agent runs in isolation with its own tools and
context.

### Quick Example

```bash
# Requires `uv pip install -e agents/coding-agent`
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

Sub-agent profiles ship in `agents/coding-agent/configs/custom/`:

| Profile | Description |
|---------|-------------|
| `coding_planner` | Task decomposition and planning |
| `coding_worker` | Implementation with full tooling |
| `coding_reviewer` | Code review specialist |
| `code_reviewer` | Alternative code review agent |
| `test_engineer` | Test writing and validation |
| `doc_writer` | Documentation creation |
| `swe_analyzer` | SWE-Bench analysis |
| `swe_coder` | SWE-Bench solving |

Butler custom roles live in `agents/butler/configs/custom/` (`accountant`,
`pc-agent`, `research_agent`, `vision_ocr`). Butler *top-level* role specializations
are under `agents/butler/configs/roles/` (`accountant`, `personal_assistant`).

### Custom Agent Example

Create `agents/coding-agent/configs/custom/security_auditor.yaml` (or any
directory the profile loader is configured to search):

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

## Butler Agent (Event-Driven, Optional Package)

The Butler is a proactive, event-driven agent daemon that runs 24/7 as a personal
assistant. It ships as the `taskforce-butler` package under `agents/butler/`.
When installed, the unified CLI promotes `butler` to the default profile;
without it, the default is `dev`.

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

Specialized butler personas live in `agents/butler/configs/roles/`:

- `accountant` — Financial document processing
- `personal_assistant` — General personal assistant

See [ADR-017](docs/adr/adr-017-butler-role-specialization.md) for the role model.

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

### Local Dev Launcher (Windows / PowerShell)

`dev.ps1` boots the backend (`taskforce serve --reload`) and the UI (`pnpm dev`)
together, with the enterprise plugin pre-flight (alembic + bootstrap) and
stale-chunk protection for the `@taskforce/enterprise-ui` Vite dep.

```powershell
.\dev.ps1                  # backend (8070) + UI (5173) in this terminal, prefixed logs
.\dev.ps1 -Split           # both in two separate terminal windows (independent Ctrl+C)
.\dev.ps1 -Backend         # backend only, foreground
.\dev.ps1 -Frontend        # UI only, foreground
.\dev.ps1 -Install         # force reinstall enterprise plugin + UI deps, then start
.\dev.ps1 -SkipMigrate     # skip alembic on startup (faster cold start)
.\dev.ps1 -Build           # production build of UI only
.\dev.ps1 -Port 8080       # override backend port (also re-points UI proxy)
.\dev.ps1 -ForceVite       # always wipe ui/node_modules/.vite + start with --force
```

Stale-chunk protection: before starting the UI, the script fingerprints
`ui/node_modules/@taskforce/enterprise-ui/dist/index.js` (+ `index.css`) and
compares it with `ui/.dev-fingerprint`. If the dist changed since the last run,
`ui/node_modules/.vite` is wiped and Vite is started with `--force`, which
prevents the browser from requesting old chunk hashes (e.g. a 404 on
`CreateUserPage-XXX.js` and the "Page update required" fallback).

### Run Tests
```bash
uv run pytest
uv run pytest --cov=taskforce --cov-report=html

cd ui
npm run test
npm run test:e2e
```

### Code Quality
```bash
uv run black src/taskforce tests
uv run ruff check src/taskforce tests
uv run mypy src/taskforce
```

### Optional Dependency Groups
```bash
uv sync --extra browser            # Playwright browser automation
uv sync --extra rag                # Azure AI Search
uv sync --extra office             # docx/pptx/excel tools
uv sync --extra postgres           # PostgreSQL persistence
uv sync --extra tokenizer          # Tiktoken token counting
uv sync --extra tracing            # Arize Phoenix OTEL tracing
uv sync --extra auth               # Cryptography / OAuth2
uv sync --extra acp                # Agent Communication Protocol SDK
uv sync --extra evals              # Inspect AI + SWE-Bench evaluation
```

## License
MIT - see [LICENSE](LICENSE) for details.
