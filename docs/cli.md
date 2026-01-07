# CLI Guide

The `taskforce` CLI is the primary way to interact with the agent framework during development.

## 🛠 Basic Commands

### Running a Mission
The `run mission` command starts a new agent task.
```powershell
taskforce run mission "Summarize the latest trends in AI"
```

### Long-Running Harness Sessions
Run long-running coding tasks with a persistent harness (feature list, progress log, init script):
```powershell
# Initialize harness artifacts and first session
taskforce run longrun --init "Build a billing dashboard"

# Continue the same mission (resume with session id)
taskforce run longrun --session <session-id> "Continue billing dashboard"

# Auto-continue for multiple runs (e.g., 5 iterations)
taskforce run longrun --auto --max-runs 5 "Continue billing dashboard"

# Use a mission/spec file (MISSION becomes optional)
taskforce run longrun --init --prompt-path ".\\spec.md"
```

By default, Taskforce stores harness files under `.taskforce/longrun/`:
- `feature_list.json`
- `progress.md`
- `init.sh`
- `harness.json` (last mission + session id)

You can override paths using `--features-path`, `--progress-path`, `--init-script`, `--prompt-path` (mission/spec file), or `--metadata-path`.

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
