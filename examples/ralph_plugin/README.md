# Ralph Plugin - Quick Start Guide

This directory contains the Ralph Loop plugin, which enables autonomous multi-iteration development tasks with context rotation.

## What is Ralph Loop?

Ralph Loop is a pattern for breaking down complex development tasks into smaller stories that can be completed autonomously across multiple LLM context windows. Each iteration starts fresh, but maintains awareness through:

- **PRD (prd.json)**: Tracks user stories and completion status
- **Git History**: Each iteration is committed
- **Learnings (progress.txt)**: Lessons learned from previous iterations
- **Guardrails (AGENTS.md)**: Rules to prevent repeating mistakes

## Quick Start

### 1. Prerequisites

- Taskforce CLI installed and in PATH
- PowerShell 7+ (for orchestrator script)
- Git repository initialized

### 2. Define Your Task

Create a task description. See `RALPH_TASK.md` in this directory for an example.

### 3. Initialize PRD

```powershell
taskforce run command ralph:init "Your task description here"
```

This creates `prd.json` with user stories broken down from your description.

### 4. Run the Loop

```powershell
.\scripts\ralph.ps1
```

The orchestrator will:
- Run iterations until all tasks are complete
- Commit each successful iteration
- Exit when done or max iterations reached

### 5. Monitor Progress

Watch the console output for iteration count, current task, and git commits.

## Example Files

This directory includes example files to help you get started:

- **RALPH_TASK.md**: Example task description
- **prd.json.example**: Example PRD structure (created by `ralph:init`)

## Plugin Structure

```
ralph_plugin/
├── ralph_plugin/
│   ├── __init__.py
│   └── tools/
│       ├── prd_tool.py          # PRD management tool
│       └── learnings_tool.py    # Learnings and guardrails tool
├── configs/
│   └── ralph_plugin.yaml        # Plugin configuration
└── requirements.txt              # Plugin dependencies
```

## Tools

### ralph_prd

Manages the PRD (Product Requirements Document):

- `action: "get_next"` - Get the next pending story
- `action: "mark_complete"` - Mark a story as complete (requires `story_id`)

### ralph_learnings

Records lessons and updates guardrails:

- Appends to `progress.txt` with lessons learned
- Updates `AGENTS.md` with guardrails and signs

## Slash Commands

### /ralph:init

Initializes a new PRD from a task description:

```powershell
taskforce run command ralph:init "Create a calculator with tests"
```

### /ralph:step

Executes one iteration - picks next task, implements it, updates PRD:

```powershell
taskforce run command ralph:step --output-format json
```

## Configuration

The plugin uses the `ralph_plugin` profile defined in `configs/ralph_plugin.yaml`. Key settings:

- **max_steps**: 50 (maximum steps per iteration)
- **planning_strategy**: plan_and_execute
- **work_dir**: .taskforce_ralph (where state is stored)

## Troubleshooting

See the main [Ralph Loop documentation](../../docs/ralph.md) for detailed troubleshooting.

Common issues:

- **"taskforce command not found"**: Ensure Taskforce is installed and in PATH
- **"Git repository not initialized"**: Run `git init`
- **"Failed to initialize"**: Ensure you provide a task description argument

## Learn More

- **[Full Documentation](../../docs/ralph.md)**: Comprehensive guide to Ralph Loop
- **[CLI Guide](../../docs/cli.md)**: Taskforce CLI reference
- **[Plugin Development](../../docs/plugins.md)**: Creating custom plugins
