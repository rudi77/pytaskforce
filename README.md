# Taskforce

Production-grade multi-agent orchestration framework built with **hexagonal (clean) architecture** principles.

## Quick Start

Taskforce installs four ways — pick the one that fits. Every path ends with
a single process serving the REST API **and** the web UI on
<http://localhost:8070>. Full guide: **[docs/install.md](docs/install.md)**.

### Option A — Native installer (easiest, no developer tools)

**Linux / macOS:**
```bash
curl -LsSf https://raw.githubusercontent.com/rudi77/pytaskforce/main/install.sh | sh
taskforce up
```

**Windows (PowerShell):**
```powershell
irm https://raw.githubusercontent.com/rudi77/pytaskforce/main/install.ps1 | iex
taskforce up
```

The installer downloads a self-contained bundle (no Python/Node/git
needed), asks for your OpenAI API key, and puts a `taskforce` launcher on
your `PATH`. Pass `--from-source` to install from this repository with
`uv` instead.

### Option B — Docker (desktop or server)

```bash
git clone https://github.com/rudi77/pytaskforce && cd pytaskforce
cp .env.example .env        # then add your OPENAI_API_KEY
docker compose up -d        # open http://localhost:8070
```

Works identically on Linux servers, Windows and macOS (Docker Desktop).
State persists in the `taskforce_data` volume.

### Option C — From source (developers)

Taskforce uses the modern **uv** package manager.

```bash
# Install uv if you haven't already
pip install uv

# Clone and enter the repo
git clone https://github.com/rudi77/pytaskforce && cd pytaskforce

# Create the virtual environment and install everything
# (framework + unified CLI + bundled agent packages)
uv sync

# Browser tool (optional) — download the Chromium binary once
uv run playwright install chromium

# Build the web UI so the API can serve it (optional but recommended)
cd ui && pnpm install && pnpm run build && cd ..
cp -r ui/dist src/taskforce/api/_ui

# Configure and run
cp .env.example .env        # add your OPENAI_API_KEY
uv run taskforce up
```

> **Enterprise edition** — multi-tenant authentication, RBAC, policy
> engine and audit trail — installs separately as its own image /
> installer. See the
> [taskforce-enterprise](https://github.com/rudi77/taskforce-enterprise)
> repository.

### Run Your First Mission
```bash
# CLI Mode — default profile is 'butler' if taskforce-butler is installed,
# otherwise 'dev'. Override any time with --profile <name>.
taskforce run mission "Describe the current weather in Vienna"

# Interactive Chat
taskforce chat

# Web UI + REST API (single process)
taskforce up
# Documentation: http://localhost:8070/docs
```

### Install Optional Agent Packages

The native installer and Docker image already include the bundled agent
packages. For a from-source install you can add them individually:

```bash
# Enable butler (daemon + Google Workspace tools + scheduler)
uv pip install -e agents/butler

# Enable coding orchestration (epic pipeline, coding_agent profile)
uv pip install -e agents/coding-agent

# Enable RAG tools (rag_agent profile)
uv pip install -e agents/rag-agent
```

The default deployment surfaces only the Butler family (incl. coding sub-agents),
`rag_agent`, and the standalone `accounting_agent` in `GET /api/v1/agents` and
the UI. Showcases and other discoverable agents stay loadable by id but stay
out of the catalog. To customise, edit `src/taskforce/configs/deployment.yaml`,
point `TASKFORCE_DEPLOYMENT_MANIFEST` at your own manifest, or toggle agents
from **Settings → Agents** in the UI — see
[`docs/profiles.md`](docs/profiles.md#deployment-manifest-visible-agents-allowlist).

### Configure runtime via the UI

Once the server is running, **Settings** in the UI exposes the runtime config you'd
otherwise pin via env vars:

- **LLM Providers** — API keys + endpoints for OpenAI, Anthropic, Azure, Google,
  Ollama. Includes a "Test connection" probe.
- **Channels** — Telegram bot token, Teams app id/secret. Includes a test-send
  button.
- **Agents** — checkbox editor for the visible-agents allowlist (overrides
  `deployment.yaml`).
- **Integrations** — list + revoke OAuth connections (Gmail / Calendar / Drive).

Secrets are stored Fernet-encrypted at `<work_dir>/settings.json.enc`. For
production, set `TASKFORCE_SECRETS_KEY` so the master key lives outside the
work dir; otherwise it auto-generates at `<work_dir>/.secrets.key` (mode 0600
on POSIX).

### Load a Plugin (Optional)
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

Installing the Enterprise edition is documented in the
[taskforce-enterprise](https://github.com/rudi77/taskforce-enterprise)
repository — it ships as its own Docker image and installer, layered on
the Community distribution.

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
`pc-agent`, `research_agent`). Butler *top-level* role specializations
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

- **[Installation Guide](docs/install.md)**: All four install paths (native, Docker, source) for Community and Enterprise.
- **[Setup & Configuration](docs/setup.md)**: Environment setup and `.env` reference.
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

> **Requires pnpm 11+.** The launcher and `scripts/sync-plugins.ps1` call
> `pnpm approve-builds --all` after every install (pnpm 11's `esbuild`
> postinstall is treated as a hard install failure unless explicitly
> approved). On pnpm 10 this fails with `Unknown option: 'all'`. Either
> enable Corepack (`corepack enable` — picks up the version pinned in
> `ui/package.json`'s `packageManager` field) or install globally:
> `npm install -g pnpm@latest`.

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

### Core Tool Dependencies

`uv sync` already installs every dependency the default agent needs at
runtime — including Playwright (browser tool), `python-docx` /
`python-pptx` / `openpyxl` (office tools), `tiktoken`, `cryptography`
and `watchdog`. The matching `--extra` groups (`browser`, `office`,
`tokenizer`, `auth`, `event-sources-fs`, `pdf`) remain accepted as
no-op extras so legacy install scripts keep working.

For the `browser` tool, download the Chromium binary once:
```bash
playwright install chromium
```

### Building the Distribution Artifacts

```bash
# Docker image (Community)
docker build -t taskforce-community .

# Self-contained PyInstaller bundle (used by the native installer's binary mode)
uv run python scripts/build_exe.py --archive
```

Tagging a `v*` release runs `.github/workflows/release.yml`, which builds and
publishes the Docker image and the per-OS PyInstaller bundles automatically.

### Optional Dependency Groups
```bash
uv sync --extra rag                # Azure AI Search
uv sync --extra postgres           # PostgreSQL persistence
uv sync --extra tracing            # Arize Phoenix OTEL tracing
uv sync --extra acp                # Agent Communication Protocol SDK
uv sync --extra evals              # Inspect AI + SWE-Bench evaluation
```

## License
MIT - see [LICENSE](LICENSE) for details.
