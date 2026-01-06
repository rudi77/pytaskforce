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

