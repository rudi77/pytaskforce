# CLI Guide

The `taskforce` CLI is the primary way to interact with the agent framework during development.

## 🛠 Basic Commands

### Running a Mission
The `run mission` command starts a new agent task.
```powershell
taskforce run mission "Summarize the latest trends in AI"
```

### Running Slash Commands
Execute custom slash commands from `.taskforce/commands/`:
```powershell
# Run with inline arguments
taskforce run command review path/to/file.py

# Run with arguments from a file (useful for complex multi-line specs)
taskforce run command ralph:init --spec-file spec.md
taskforce run command ralph:init -F spec.md

# With streaming output
taskforce run command analyze data.csv --stream

# With JSON output format
taskforce run command review -F spec.md -f json
```

**Options:**
- `--spec-file`, `-F`: Path to a file containing command arguments. Mutually exclusive with positional arguments. The file content is used verbatim, preserving formatting (newlines, markdown, etc.).
- `--profile`, `-p`: Configuration profile to use
- `--stream`, `-S`: Enable streaming output
- `--output-format`, `-f`: Output format (`text` or `json`)

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

