# Taskforce CLI - Enhanced User Interface

## Overview

The Taskforce CLI has been redesigned with a beautiful, eye-catching interface that provides:

- 🎨 **Visual Distinction**: Clear separation between Agent and User messages
- 🐛 **Debug Mode**: Toggle detailed logging with `--debug` flag
- 🎭 **Rich Formatting**: Panels, colors, and icons for better readability
- 🚀 **Professional Look**: Eye-catching banner and structured output

## Features

### 1. Debug Mode Toggle

Control the verbosity of output with the `--debug` flag:

```powershell
# Normal mode - clean output, no logs
taskforce chat

# Debug mode - shows agent thoughts, actions, observations, and all logs
taskforce --debug chat
```

**Debug mode shows:**
- 💭 Agent thought processes (reasoning)
- ⚡ Agent actions (tool calls, decisions)
- 👁️ Observations (tool results)
- 🔍 Debug messages with detailed info
- 📝 Structured logs (component initialization, tool registration, etc.)

**Logging Level Control:**
- **Normal Mode**: Logging level set to WARNING (only warnings and errors)
- **Debug Mode**: Logging level set to DEBUG (all logs visible)

This means in normal mode, you get a clean, user-friendly interface without any technical logs cluttering the output. In debug mode, you see everything for troubleshooting and development.

### 2. Visual Message Distinction

**User Messages** (Green panels with 👤 icon):
```
╭─ 👤 You ─────────────────────────────────╮
│ Analyze the sales data from Q4          │
╰──────────────────────────────────────────╯
```

**Agent Messages** (Cyan panels with 🤖 icon):
```
╭─ 🤖 Agent ───────────────────────────────╮
│ I'll analyze the Q4 sales data for you. │
│ Let me start by reading the file...     │
╰──────────────────────────────────────────╯
```

**Agent Thoughts** (Magenta panels, debug mode only):
```
╭─ 💭 Agent Thought ───────────────────────╮
│ The user wants Q4 analysis. I need to   │
│ first locate the data file, then use    │
│ Python to perform statistical analysis. │
╰──────────────────────────────────────────╯
```

### 3. Startup Banner

Every session starts with an eye-catching banner:

```
╔═══════════════════════════════════════════════════════╗
║                                                       ║
║        🤖 TASKFORCE - ReAct Agent Framework        ║
║                                                       ║
╚═══════════════════════════════════════════════════════╝
```

### 4. Session Information

Clear display of session context:

```
╭─ ℹ️ Session Info ────────────────────────╮
│ Session ID: abc-123-def-456              │
│ Profile: dev                             │
│ RAG Context:                             │
│   user_id: john-doe                      │
│   org_id: acme-corp                      │
╰──────────────────────────────────────────╯
```

## Usage Examples

### Interactive Chat

```powershell
# Standard chat
taskforce chat

# Chat with debug mode
taskforce --debug chat

# RAG chat with user context
taskforce --profile rag_dev chat --user-id john --org-id acme
```

### Mission Execution

```powershell
# Execute mission
taskforce run mission "Analyze data.csv"

# Execute with debug output
taskforce --debug run mission "Create a report"

# Resume previous session
taskforce run mission "Continue" --session abc-123
```

### Global vs Local Options

```powershell
# Global debug flag (applies to all commands)
taskforce --debug chat

# Local debug flag (overrides global)
taskforce chat --debug

# Profile can be set globally or per-command
taskforce --profile prod run mission "Deploy"
taskforce run mission "Deploy" --profile prod
```

## Color Scheme

The CLI uses a carefully designed color theme:

| Element | Color | Icon | Purpose |
|---------|-------|------|---------|
| Agent | Cyan | 🤖 | Agent responses |
| User | Green | 👤 | User input |
| System | Blue | ℹ️ | System messages |
| Success | Green | ✅ | Success notifications |
| Error | Red | ❌ | Error messages |
| Warning | Yellow | ⚠️ | Warnings |
| Debug | Dim White | 🔍 | Debug information |
| Thought | Magenta | 💭 | Agent reasoning |
| Action | Yellow | ⚡ | Agent actions |
| Observation | Cyan | 👁️ | Tool results |

## Architecture

### Components

1. **`output_formatter.py`**: Core formatting module
   - `TaskforceConsole`: Main console class with themed output
   - Methods for different message types (agent, user, system, error, etc.)
   - Debug mode support

2. **`main.py`**: CLI entry point
   - Global `--debug` flag
   - Command registration
   - Context management

3. **`commands/chat.py`**: Interactive chat mode
   - Uses `TaskforceConsole` for formatted output
   - Shows user/agent messages in panels
   - Debug mode shows thoughts and actions

4. **`commands/run.py`**: Mission execution
   - Progress indicators with spinners
   - Formatted success/error messages
   - Session info display

### Design Principles

1. **Clarity**: Clear visual distinction between different message types
2. **Consistency**: Same formatting patterns across all commands
3. **Flexibility**: Debug mode can be toggled without code changes
4. **Beauty**: Eye-catching design that's professional and modern
5. **Usability**: Important information stands out, noise is minimized

## Customization

### Extending the Theme

To add new styles, edit `output_formatter.py`:

```python
TASKFORCE_THEME = Theme({
    "agent": "bold cyan",
    "user": "bold green",
    "custom_style": "bold purple",  # Add your style
})
```

### Adding New Message Types

Add methods to `TaskforceConsole`:

```python
def print_custom_message(self, message: str):
    """Print custom message type."""
    panel = Panel(
        message,
        title="🎯 Custom",
        border_style="purple",
    )
    self.console.print(panel)
```

## Testing

Test the CLI output:

```powershell
# Test banner and version
taskforce version

# Test chat interface
taskforce chat
> Hello
> exit

# Test debug mode
taskforce --debug chat
> Test debug output
> exit

# Test mission execution
taskforce run mission "Test mission"
```

## Troubleshooting

### Colors not showing

Ensure your terminal supports ANSI colors:
- Windows: Use Windows Terminal or PowerShell 7+
- Linux/Mac: Most terminals support colors by default

### Debug output not showing

Make sure you're using the `--debug` flag:
```powershell
taskforce --debug chat  # Correct
taskforce chat          # No debug output
```

### Panels look broken

Update Rich library:
```powershell
uv add rich@latest
```

## Future Enhancements

Potential improvements:
- [ ] Streaming output for long agent responses
- [ ] Progress bars for multi-step missions
- [ ] Syntax highlighting for code blocks in messages
- [ ] Export chat history with formatting
- [ ] Custom themes via config file
- [ ] Interactive tool selection UI
- [ ] Live updating status dashboard

## Credits

Built with:
- [Rich](https://github.com/Textualize/rich) - Beautiful terminal formatting
- [Typer](https://github.com/tiangolo/typer) - Modern CLI framework

