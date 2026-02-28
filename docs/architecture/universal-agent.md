# Universal Agent Architecture

## Overview

The Universal Agent is the default entry point for Taskforce. It provides a single agent that handles most tasks directly and intelligently delegates to specialist sub-agents when needed.

**Before:** Users had to choose the right profile for each task.
```bash
taskforce run mission "..." --profile dev
taskforce run mission "..." --profile coding_agent
taskforce epic "..." --rounds 3
```

**After:** One command that just works.
```bash
taskforce run mission "Analyze this CSV file"
taskforce run mission "Refactor the auth module and write tests"
taskforce run mission "Build a REST API" --auto-epic
```

## Architecture

```
┌─────────────────────────────────────────────────────┐
│                    CLI / API                         │
│  taskforce run mission "..."                        │
│  (Default: universal profile)                       │
└──────────────────────┬──────────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────────┐
│              Universal Agent                         │
│  Tools: file_*, web_*, python, shell, browser,      │
│         git, memory, call_agent                     │
│  Strategy: plan_and_react                           │
│                                                      │
│  System Prompt: LEAN_KERNEL + UNIVERSAL_AGENT       │
│  + Compact Specialist Index (auto-discovered)       │
└──────┬──────────┬──────────┬───────────────────────┘
       │          │          │
       │ direct   │ call_agent(specialist=...)
       │ tools    │          │
       ▼          ▼          ▼
  ┌─────────┐ ┌──────────┐ ┌──────────────────┐
  │ Direct  │ │ coding_  │ │ Plugin Agents    │
  │ Tool    │ │ worker   │ │ (accounting,     │
  │ Usage   │ │ coding_  │ │  doc_extraction) │
  │         │ │ reviewer │ │                  │
  └─────────┘ └──────────┘ └──────────────────┘
```

## Components

### 1. Universal Profile (`configs/universal.yaml`)

Broad toolset including:
- File operations: `file_read`, `file_write`, `edit`, `grep`, `glob`
- Code execution: `python`, `powershell`
- Web & browser: `web_search`, `web_fetch`, `browser`
- VCS: `git`
- Memory & interaction: `memory`, `ask_user`
- Specialist delegation: `call_agent`

Uses `plan_and_react` strategy for hybrid planning + reactive execution.

### 2. Universal Agent Prompt

Located in `core/prompts/autonomous_prompts.py` as `UNIVERSAL_AGENT_PROMPT`.

Provides clear guidance on:
- **When to handle directly** (simple file ops, web search, shell commands)
- **When to delegate** (complex multi-file development, specialized domains)
- **Task decomposition** (splitting into parallel sub-tasks)
- **Available specialists** (dynamically injected via `{available_specialists}` placeholder)

### 3. Specialist Discovery Service

Located in `application/specialist_discovery.py`.

Automatically discovers available specialists from three sources:
1. **Built-in:** `coding`, `rag`, `wiki`
2. **Custom agents:** `configs/custom/*.yaml`
3. **Plugin agents:** `plugins/*/configs/agents/*.yaml`

Produces a compact index (name + one-liner per specialist) for:
- System prompt injection (replaces `{available_specialists}`)
- AgentTool description (shows available specialists to the LLM)

Results are cached after first scan. Typical index size: < 500 characters for 10 specialists.

### 4. Dynamic AgentTool Description

The `call_agent` tool (`AgentTool`) receives the specialist index at creation time and includes it in its tool description. This way the LLM knows exactly which specialists are available without hardcoded lists.

## How Delegation Works

1. The LLM receives the system prompt with the specialist index
2. Based on the task, it decides to either use direct tools or `call_agent`
3. `call_agent` spawns an isolated sub-agent via `SubAgentSpawner`
4. The sub-agent executes with its own tools, session, and state
5. Results are returned to the Universal Agent for consolidation

Multiple `call_agent` invocations can run in parallel for independent tasks.

## Adding New Specialists

New specialists are automatically discovered. To add one:

1. Create a YAML config in `configs/custom/my_specialist.yaml`
2. Include a `description` field or a descriptive header comment
3. The Universal Agent will discover it on next startup

```yaml
# My Specialist Agent
#
# Expert in data analysis and visualization.

agent:
  type: custom
  max_steps: 40

system_prompt: |
  You are a data analysis expert...

tools:
  - python
  - file_read
  - file_write
```

## Configuration

The universal profile is the CLI default. To override:

```bash
# Use a specific profile
taskforce run mission "..." --profile dev

# Use with auto-epic for complex tasks
taskforce run mission "..." --auto-epic
```
