# Taskforce Chat UI

## Overview

The Taskforce Chat UI provides a modern, terminal-based chat interface built with the Textual framework. It replaces the previous command-line chat implementation with a fully-featured TUI (Text User Interface) that offers:

- **Fixed Input Bar**: Input stays at the bottom of the screen and doesn't scroll away
- **Scrollable Message History**: Chat messages scroll independently of the input
- **Real-time Status Updates**: Live status indicator showing agent activity
- **Plan Visualization**: Display of the current task plan with progress tracking
- **Token Usage Tracking**: Real-time token count updates
- **Event Visualization**: Tool calls, results, and errors displayed in context

## Architecture

### Components

The chat UI is organized into the following components:

```
src/taskforce/api/cli/chat_ui/
├── __init__.py           # Package exports
├── app.py                # Main Textual application
├── styles.css            # Textual CSS styling
└── widgets/              # UI components
    ├── __init__.py       # Widget exports
    ├── chat_log.py       # Scrollable message container
    ├── message.py        # Individual message bubbles
    ├── header.py         # Status bar with session info
    ├── input_bar.py      # Fixed input field
    └── plan_panel.py     # Plan visualization panel
```

### Widget Hierarchy

```
TaskforceChatApp
├── Header (session info, status, tokens)
├── Container
│   ├── PlanPanel (collapsible plan display)
│   └── ChatLog (scrollable message list)
│       ├── ChatMessage (user)
│       ├── ChatMessage (agent)
│       ├── ChatMessage (system)
│       └── ...
├── InputBar (fixed at bottom)
└── Footer (keyboard shortcuts)
```

## Usage

### Basic Chat

```bash
# Start chat with new UI
taskforce chat

# Debug mode (shows agent thoughts and tool details)
taskforce --debug chat
```

### LeanAgent Mode

```bash
# Use LeanAgent (simplified architecture)
taskforce chat --lean

# With streaming enabled (default)
taskforce chat --lean --stream

# Disable streaming
taskforce chat --lean --no-stream
```

### RAG Context

```bash
# Chat with RAG user context
taskforce --profile rag_dev chat \
  --user-id ms-user \
  --org-id MS-corp \
  --scope user
```

## Features

### Message Types

The UI supports different message types with distinct styling:

- **User Messages**: Inline label with timestamp
- **Agent Messages**: Inline label with timestamp, markdown-formatted output
- **System Messages**: Inline label with timestamp
- **Tool Calls**: Inline label with timestamp (debug mode)
- **Tool Results**: Inline label with timestamp (debug mode)
- **Errors**: Inline label with timestamp
- **Plan Updates**: Inline label with timestamp

### Commands

The Chat UI supports built-in and **[Custom Slash Commands](slash-commands.md)**. Type these commands in the chat input:

- `/help` or `/h` - Show all available commands (including custom ones)
- `/clear` or `/c` - Clear chat history
- `/export` or `/e` - Export chat to file (coming soon)
- `/debug` - Toggle debug mode
- `/tokens` - Show token usage statistics
- `/exit` or `/quit` - Exit the application

Custom commands can be added by placing Markdown files in `.taskforce/commands/`.

### Keyboard Shortcuts

- `Ctrl+Enter` - Send message
- `Enter` - Insert newline (multi-line input)
- `Ctrl+C` - Quit application
- `Ctrl+L` - Clear chat
- `F1` - Show help

### Status Indicators

The header displays real-time status with icons:

- 💤 Idle - Waiting for input
- 🔄 Initializing - Starting up
- 🧠 Thinking - Processing request
- ⚙️ Working - General work in progress
- 🔧 Calling Tool - Executing tool
- ⚡ Processing - Processing results
- 💬 Responding - Generating response
- ✅ Complete - Task finished
- ❌ Error - Error occurred

### Plan Visualization

When the agent creates a plan, it's displayed in the Plan Panel with:

- Checkbox indicators for step status
- Real-time updates as steps complete
- Collapsible panel to save screen space

```
🧭 Current Plan
─────────────────────────────────
[✓] 1. Read the input file
[⏳] 2. Process the data
[ ] 3. Generate output report
```

## Streaming Mode

Streaming mode (enabled by default) provides real-time updates:

- Tool calls appear immediately when invoked
- Tool results stream as they complete
- Agent responses appear token-by-token
- Plan updates show progress live
- Token counts update in real-time

Disable streaming for a more traditional request-response flow:

```bash
taskforce chat --no-stream
```

## Debug Mode

Debug mode reveals the agent's internal reasoning:

- **Thoughts**: Agent's reasoning process (for compatible agents)
- **Tool Calls**: Detailed tool invocations with parameters
- **Tool Results**: Full tool outputs
- **Internal Events**: Additional execution details

Enable debug mode globally:

```bash
taskforce --debug chat
```

Or toggle during chat:

```
> /debug
System: Debug mode enabled
```

## Styling

The UI uses a dark theme by default with customizable colors via CSS. The color scheme is defined in `styles.css`:

- Primary: `#0178d4` (Azure blue)
- Accent: `#00c9ff` (Bright cyan)
- Surface: `#1e1e1e` (Dark gray)
- Text: `#cccccc` (Light gray)

## Development

### Adding New Message Types

1. Add type to `MessageType` enum in `widgets/message.py`
2. Implement render method in `ChatMessage` class
3. Add helper method in `ChatLog` if needed
4. Update CSS in `styles.css`

### Adding New Commands

1. Add command handler in `app.py` `_handle_command` method
2. Update help text in `_show_help` method
3. Add keyboard binding if needed in `BINDINGS`

### Testing

Run widget tests:

```bash
uv run pytest tests/unit/api/cli/chat_ui/ -v
```

Note: Some tests require widgets to be mounted in an app context.

## Migration from Old Chat UI

The old Rich-based chat UI has been completely replaced. Key differences:

### Old UI:
- Scrolling input/output mixed together
- No persistent status bar
- Plan shown inline in messages
- Limited visual separation

### New UI:
- Fixed input bar at bottom
- Persistent header with status
- Dedicated plan panel
- Clear message separation
- Better organization

All existing functionality is preserved:
- ✅ Debug mode
- ✅ Streaming
- ✅ Tool visualization
- ✅ Plan tracking
- ✅ Token usage
- ✅ RAG context
- ✅ LeanAgent support

## Troubleshooting

### UI doesn't start

Check that Textual is installed:

```bash
uv sync
```

### Terminal rendering issues

Some terminals may not fully support Textual. Try:

```bash
# Use a different terminal emulator
# Or fall back to run command for non-interactive execution
taskforce run mission "your task"
```

### Input not responding

Press `Ctrl+C` to exit and restart. The input should automatically focus on startup.

### Colors look wrong

Textual requires a terminal with true color support. Check your terminal settings or try a different terminal emulator.

## Future Enhancements

Planned features:

- [ ] Chat export to markdown/JSON
- [ ] Custom themes
- [ ] Message search
- [ ] Multi-session management
- [ ] Conversation replay
- [ ] Plugin system for custom widgets
