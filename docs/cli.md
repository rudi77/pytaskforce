# CLI Guide

The `taskforce` CLI is the primary way to interact with the agent framework during development.

## 🛠 Basic Commands

### Running a Mission
The `run mission` command starts a new agent task.
```powershell
taskforce run mission "Summarize the latest trends in AI"
```

### Interactive Chat
Open a continuous conversation with an agent.
```powershell
taskforce chat
```
Use `Enter` to send messages (simple REPL-style input).
Streaming output is enabled by default. Agent thoughts, events, and plan updates are printed inline with icons and color.
Within the chat, you can use **Slash Commands** (e.g., `/help`, `/clear`) to interact with the system or trigger custom workflows. See the **[Slash Commands Guide](slash-commands.md)** for details on creating your own.

### Loading Plugins
Load external agent plugins with custom tools:
```powershell
taskforce chat --plugin examples/accounting_agent
```

The `--plugin` option accepts a path to a plugin directory containing:
- A Python package with tools in `{package}/tools/__init__.py`
- Optional config at `configs/{package}.yaml`

See **[Plugin Development Guide](plugins.md)** for creating your own plugins.

### Profile Selection
By default, Taskforce uses the `dev` profile. You can override this:
```powershell
taskforce run mission "..." --profile prod
```

### Multi-Agent Orchestration
Use the `orchestrator` profile to enable multi-agent coordination:
```powershell
taskforce run mission "Research Python FastAPI and React, create comparison" \
  --profile orchestrator
```

The orchestrator agent can delegate subtasks to specialist sub-agents:
- **coding**: File operations, shell, Git
- **rag**: Semantic search, document retrieval
- **wiki**: Wikipedia research
- **Custom agents**: Your own specialists from `configs/custom/`

**Example with custom agent:**
```powershell
# First, create configs/custom/security_auditor.yaml with custom prompt and tools

# Then use the orchestrator
taskforce run mission "Perform security audit on codebase" --profile orchestrator

# The orchestrator will automatically spawn the security_auditor specialist
```

**Direct specialist usage:**
```powershell
# Use specialist directly (without orchestrator)
taskforce run mission "Review code quality in src/" --profile code_reviewer
```

See [Multi-Agent Orchestration Plan](architecture/multi-agent-orchestration-plan.md) for details.

### Epic Orchestration (Planner → Workers → Judge)
Run epic-scale workflows that generate tasks, execute them in parallel, and
consolidate changes with a judge agent:

```powershell
taskforce epic run "Implement epic: billing export overhaul" \
  --scope "backend export pipeline" \
  --scope "frontend export UI" \
  --workers 4 \
  --rounds 3 \
  --auto-commit \
  --commit-message "Epic: billing export overhaul"
```

Profiles used by default:
- `planner` (task generation)
- `worker` (implementation)
- `judge` (review/commit)

## 🔍 Inspection & Management

### Tools
List and inspect available tools:
```powershell
taskforce tools list
taskforce tools inspect python
```

### Sessions
View and resume previous agent sessions:
```powershell
taskforce sessions list
taskforce sessions show <session-id>
```

### Configuration
View the current active configuration:
```powershell
taskforce config show
```

### Skills
Manage and inspect agent skills:

```powershell
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

---
*For full command details, run `taskforce --help`.*
