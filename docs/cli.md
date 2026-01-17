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

---
*For full command details, run `taskforce --help`.*

