# CLI Guide

The `taskforce` CLI is the primary way to interact with the agent framework
during development.

There are two entry points:

1. **Unified CLI** (`taskforce-cli`, preferred) — discovers installed agent
   packages and automatically adds their subcommands (`butler`, `epic`, `rag`).
2. **Framework-only fallback** (`src/taskforce/api/cli/main.py`) — used when
   `taskforce-cli` is not installed. Only ships the framework commands
   (`run`, `chat`, `tools`, `skills`, `config`, `memory`, `acp`).

> **Default profile:** The unified CLI picks `butler` if `taskforce-butler`
> is installed, otherwise `dev`. The fallback CLI always defaults to `dev`.
> Override with `--profile <name>` or the `TASKFORCE_PROFILE` env var.

## Global Options

```bash
taskforce --profile <name>   # Configuration profile
taskforce --debug            # Enable debug output (agent thoughts, actions, observations)
```

## Top-Level Commands

### Version
```bash
taskforce version            # Show Taskforce version, banner, and installed agent packages
```

### Butler Shortcuts (require `taskforce-butler`)
Convenience commands that delegate to `taskforce butler`:

```bash
taskforce start              # Start the butler daemon (shortcut for 'butler start')
taskforce start --detach     # Start in background
taskforce status             # Show butler daemon status
taskforce stop               # Stop the butler daemon gracefully
```

---

## Running a Mission

The `run mission` command starts a new agent task.

```bash
taskforce run mission "Summarize the latest trends in AI"
```

### Options

| Option | Short | Description |
|--------|-------|-------------|
| `--profile` | `-p` | Configuration profile |
| `--session` | `-s` | Resume an existing session ID |
| `--stream` | `-S` | Enable streaming output |
| `--plugin` | `-P` | Load a plugin agent |
| `--debug` | | Enable debug output |
| `--lean` | `-l` | Use LeanAgent instead of full Agent |
| `--planning-strategy` | | Override planning strategy (native_react, plan_and_execute, plan_and_react, spar) |
| `--planning-strategy-params` | | JSON string of strategy parameters |

### Examples

```bash
# With specific profile
taskforce run mission "Analyze code quality" --profile coding_agent

# With streaming
taskforce run mission "Build a REST API" --stream

# With planning strategy override
taskforce run mission "Complex task" --planning-strategy spar

# Resume a session
taskforce run mission "Continue analysis" --session abc-123
```

### Running a Skill

Execute a skill directly from the command line:

```bash
taskforce run skill <skill_name> [arguments]
```

Options: `--profile`, `--debug`, `--stream`

```bash
# Run a skill
taskforce run skill pdf-processing "Extract text from invoice.pdf"
taskforce run skill code-review "Review src/main.py"
```

---

## Interactive Chat

Open a continuous conversation with an agent.

```bash
taskforce chat
```

Use `Enter` to send messages (simple REPL-style input). Streaming output is enabled by default. Agent thoughts, events, and plan updates are printed inline with icons and color.

### Interrupting the Agent

Press `Ctrl+C` while a mission is running to **pause** the agent cooperatively:

- The current step (LLM call + any in-flight tool calls) finishes normally.
- State is persisted — messages, plan progress, step counter.
- The chat shows `⏸ Paused — type your next message to resume.`
- Your next input continues the session; no work is lost.

Press `Ctrl+C` a **second** time within 5 seconds to force-exit (for stuck
teardown). On POSIX you can also use `Ctrl+\` (SIGQUIT) as a guaranteed
last-resort kill. See [ADR-019](adr/adr-019-agent-interruption.md).

### Chat Options

| Option | Short | Description |
|--------|-------|-------------|
| `--profile` | `-p` | Configuration profile |
| `--plugin` | `-P` | Load a plugin agent |
| `--lean` | `-l` | Use LeanAgent |
| `--debug` | | Enable debug output |
| `--user-id` | | User ID for identity context |
| `--org-id` | | Organization ID for scoping |
| `--scope` | | RAG scope context |
| `--telegram-polling` | | Enable Telegram polling mode |

### Slash Commands in Chat

| Command | Description |
|---------|-------------|
| `/help` | Show available commands |
| `/clear` | Clear conversation history |
| `/plugins` | List available plugin agents |
| `/<plugin_name>` | Switch to a plugin agent |
| `/skills` | List available skills |
| `/<skill_name> [args]` | Invoke a prompt/agent skill |
| `/context` | Inspect LLM context with token estimates |
| `/context full` | Full context with content |
| `/tree` | Show LLM context as tree (mirrors actual API call structure) |
| `/tree --sub-agents` | Include sub-agent contexts in the tree |
| `/write-tree` | Dump full LLM context to `tree.md` |
| `/write-tree --sub-agents` | Include sub-agent contexts in the dump |

### Loading Plugins

```bash
taskforce chat --plugin examples/accounting_agent
```

The `--plugin` option accepts a path to a plugin directory containing:
- A Python package with tools in `{package}/tools/__init__.py`
- Optional config at `configs/{package}.yaml`

See **[Plugin Development Guide](plugins.md)** for creating your own plugins.

---

## Multi-Agent Orchestration

Install `taskforce-coding-agent` to enable the `coding_agent` profile, which
delegates to specialist sub-agents:

```bash
uv pip install -e agents/coding-agent

taskforce run mission "Research Python FastAPI and React, create comparison" \
  --profile coding_agent
```

The orchestrator delegates to specialist sub-agents shipped in
`agents/coding-agent/configs/custom/`:

- **coding_planner**: Task decomposition and planning
- **coding_worker**: Implementation with tooling access
- **coding_reviewer**: Code review and quality checks
- Also available: `test_engineer`, `doc_writer`, `code_reviewer`, `swe_analyzer`, `swe_coder`

```bash
# Use a specialist directly (without the orchestrator)
taskforce run mission "Review code quality in src/" --profile code_reviewer
```

See [Sub-Agent Orchestration](features/sub-agent-orchestration.md) for patterns.

---

## Inspection & Management

### Tools
List and inspect available tools:
```bash
taskforce tools list
taskforce tools inspect python
```

### Conversations
Manage persistent agent conversations (ADR-016):

```bash
# List active conversations
taskforce conversations list

# List archived conversations
taskforce conversations list --archived

# Show messages for a conversation
taskforce conversations show <conversation-id>

# Archive a conversation
taskforce conversations archive <conversation-id>
```

### Missions
View past mission runs:

```bash
taskforce missions list
taskforce missions show <mission-id>
```

### Configuration
View the current active configuration:
```bash
taskforce config show
taskforce config list             # List all available profiles
```

### Skills
Manage and inspect agent skills:

```bash
# List all available skills
taskforce skills list

# List with full descriptions
taskforce skills list --verbose

# Show skill details (preview first 20 lines)
taskforce skills show pdf-processing

# Show complete skill instructions
taskforce skills show pdf-processing --full

# --full output includes optional skill frontmatter fields when available
# (license, compatibility, allowed-tools, metadata)

# List bundled resources for a skill
taskforce skills resources pdf-processing

# Read a specific resource file
taskforce skills read pdf-processing forms.md

# Show skill search directories
taskforce skills paths
```

Skills are modular capabilities that extend agent functionality with domain-specific expertise. Each skill packages instructions, metadata, and optional resources (scripts, templates, documentation).

**Available Built-in Skills:**
- `code-review` - Code review for bugs, security, and quality
- `data-analysis` - Data exploration, statistics, and visualization
- `documentation` - Technical documentation creation
- `pdf-processing` - PDF manipulation (extract text, fill forms, merge/split)

See **[Skills Documentation](features/skills.md)** for creating custom skills.

### Memory
Manage long-term memory consolidation:

```bash
# Trigger memory consolidation
taskforce memory consolidate

# Consolidation options
taskforce memory consolidate --strategy <strategy> --max-sessions <n>
taskforce memory consolidate --sessions <id1> <id2>   # specific sessions
taskforce memory consolidate --dry-run                 # preview only

# List captured session experiences
taskforce memory experiences
taskforce memory experiences --unprocessed             # only unconsolidated

# View consolidation statistics
taskforce memory stats
```

### Butler (requires `taskforce-butler`)
Manage the butler daemon, trigger rules, schedules, and roles. These commands
are registered by the unified CLI only when `taskforce-butler` is installed
(`uv pip install -e agents/butler`).

```bash
# Daemon management
taskforce butler start --profile butler
taskforce butler start --detach          # run in background
taskforce butler status

# Trigger rules
taskforce butler rules list
taskforce butler rules add --name "calendar_reminder" --source calendar --type calendar.upcoming

# Scheduled jobs
taskforce butler schedules list

# Butler roles
taskforce butler roles list
taskforce butler roles show accountant
taskforce butler roles show personal_assistant
```

### Epic orchestration (requires `taskforce-coding-agent`)
When installed, the unified CLI exposes `taskforce epic` for iterative
planner/worker/judge pipelines. See
[ADR-005](adr/adr-005-epic-orchestration-pipeline.md) and the package's own
README for details.

### RAG operations (requires `taskforce-rag-agent`)
When installed, `taskforce rag` provides RAG-specific operations backed by
Azure AI Search.

---

## Profile Selection

1. **Environment Variable**: `export TASKFORCE_PROFILE=dev`
2. **CLI Flag**: `taskforce run mission "..." --profile dev`

### Available Profiles

Framework-shipped (always available): `default`, `dev`, `acp_peer`, `showcase_*`.

Agent-package profiles (require the matching package):

| Profile | Package | Description |
|---------|---------|-------------|
| `butler` | `taskforce-butler` | Event-driven personal assistant daemon |
| `coding_agent` | `taskforce-coding-agent` | Multi-agent coding orchestrator |
| `coding_analysis` | `taskforce-coding-agent` | Code analysis specialist |
| `rag_agent` | `taskforce-rag-agent` | RAG-enabled agent (Azure AI Search) |

See **[Profiles & Config](profiles.md)** for the full list (incl. butler roles
and coding sub-agent profiles) and configuration details.

---
*For full command details, run `taskforce --help`.*
