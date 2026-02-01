# Slash Commands

Slash Commands are flexible, file-based commands that allow you to extend the functionality of the Taskforce Chat interface. They can be simple prompt templates or specialized agents with their own configuration.

## 🧭 Built-in Chat Commands

Taskforce ships with a handful of built-in commands in chat:

- `/help`, `/clear`, `/tokens`, `/quit`
- `/commands` (list custom slash commands)
- `/plugins` (list available plugin agents)
- `/skills` (list available skills from plugin or global skill directories)
- `/<plugin_name>` (switch to a plugin agent listed in `/plugins`)

## 📂 Storage Locations

Taskforce searches for slash commands in two locations:

1. **Project-wide**: `.taskforce/commands/` in your project root.
2. **User-specific**: `~/.taskforce/commands/` in your home directory.

**Precedence**: Project-level commands override user-level commands with the same name.

## 🏷️ Naming

Commands are named after their filename (without the `.md` extension). You can organize commands into subdirectories, which results in a hierarchical name using colons:

- `.taskforce/commands/review.md` → `/review`
- `.taskforce/commands/agents/architect.md` → `/agents:architect`

## 📝 Command Definition

A slash command is defined as a Markdown file with an optional YAML frontmatter.

### 1. Prompt Commands (`type: prompt`)

The default type. It replaces the placeholder `$ARGUMENTS` in the body with whatever text you provide after the command.

**Example: `explain.md`**
```markdown
---
description: Explains a concept in simple terms
type: prompt
---
Please explain the following concept to a beginner: $ARGUMENTS
```

**Usage**: `/explain recursion`

### 2. Agent Commands (`type: agent`)

Defines a specialized agent for a specific task. These commands **temporarily override** the current agent's configuration (system prompt, tools, profile) for a single execution.

**Example: `reviewer.md`**
```markdown
---
description: Performs a strict code review
type: agent
profile: coding_agent  # Base profile to use
tools: [file_read, python]
---
You are a senior code reviewer. Analyze the following code for bugs and security issues: $ARGUMENTS
```

**Usage**: `/reviewer src/core/agent.py`

## ⚙️ YAML Options

| Key | Type | Description |
|-----|------|-------------|
| `description` | String | A short description shown in the help menu. |
| `type` | String | Either `prompt` (default) or `agent`. |
| `profile` | String | (Agent only) The base configuration profile to use. |
| `tools` | List | (Agent only) List of tool short-names allowed for this command. |
| `mcp_servers` | List | (Agent only) List of MCP servers to connect to. |

## 🔄 Execution Behavior

When you execute a slash command:
1. The system loads the definition from the Markdown file.
2. If it's a `prompt` type, it substitutes `$ARGUMENTS` and sends it as a user message.
3. If it's an `agent` type, it creates a temporary agent context with the specified system prompt and tools, executes the request, and then restores the previous agent state.
