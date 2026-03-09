# Parallel Sub-Agent Execution

Execute multiple sub-agent missions concurrently for faster multi-agent workflows.

**ADR:** [ADR-015](../adr/adr-015-parallel-sub-agent-execution.md)

---

## Overview

Taskforce supports two complementary mechanisms for parallel sub-agent execution:

1. **LLM-Driven Parallelism** — The LLM emits multiple tool calls in one response; sub-agents with `auto_approve: true` run concurrently through the existing parallel execution gate.
2. **Batch Dispatch** — The `call_agents_parallel` tool accepts a list of missions and dispatches them with configurable concurrency control.

Both approaches use isolated sessions per sub-agent, preventing state conflicts.

## Quick Start

Add parallel-capable sub-agents to your profile YAML:

```yaml
# my_profile.yaml
tools:
  # Worker with auto_approve — enables LLM-driven parallelism
  - type: sub_agent
    name: coding_worker
    auto_approve: true
    summarize_results: true

  # Read-only analyst — safe for parallel execution
  - type: sub_agent
    name: coding_analyst
    auto_approve: true
    summarize_results: true

  # Batch dispatch tool
  - type: parallel_agent
    max_concurrency: 3
```

## Mechanism 1: LLM-Driven Parallelism (`auto_approve`)

When the LLM emits multiple tool calls in a single response, the execution engine checks each tool's parallel eligibility:

```python
can_parallel = (
    tool.supports_parallelism
    and not tool.requires_approval
)
```

Sub-agent tools (`AgentTool`, `SubAgentTool`) have `supports_parallelism = True` but default to `requires_approval = True`. Setting `auto_approve: true` in the profile YAML flips `requires_approval` to `False`, allowing the parallel gate to open.

### When to Use

- The LLM naturally emits independent tasks as separate tool calls
- You want the AI to decide what runs in parallel
- Simple workflows with 2-4 concurrent tasks

### Safety Model

- `auto_approve` only skips **parent-level** approval for spawning
- Each sub-agent still enforces its own internal tool approval
- The parent agent's `max_parallel_tools` (default: 3) bounds concurrency

## Mechanism 2: Batch Dispatch (`call_agents_parallel`)

For explicit control, use the `call_agents_parallel` tool:

```yaml
# The LLM calls this tool with a list of missions
call_agents_parallel:
  missions:
    - mission: "Implement user authentication module"
      specialist: coding_worker
    - mission: "Implement email notification service"
      specialist: coding_worker
    - mission: "Analyze database schema for optimization"
      specialist: coding_analyst
  max_concurrency: 3
```

### When to Use

- You need explicit concurrency control
- Dispatching many tasks (5+) at once
- Different specialists for different missions
- The LLM doesn't naturally emit multiple tool calls

### Features

- **Concurrency control** via `asyncio.Semaphore` (configurable `max_concurrency`)
- **Partial failure resilience** — one failing worker doesn't cancel siblings
- **Aggregated results** with per-mission success/failure status

### Response Format

```json
{
  "success": false,
  "total": 3,
  "succeeded": 2,
  "failed": 1,
  "results": [
    {"mission": "...", "specialist": "coding_worker", "success": true, "result": "..."},
    {"mission": "...", "specialist": "coding_worker", "success": false, "error": "..."},
    {"mission": "...", "specialist": "coding_analyst", "success": true, "result": "..."}
  ]
}
```

## Configuration Reference

### Sub-Agent Tool (`type: sub_agent`)

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `name` | string | required | Sub-agent name (matches config in `configs/custom/`) |
| `auto_approve` | bool | `false` | Skip parent-level approval (enables parallelism) |
| `summarize_results` | bool | `true` | Summarize sub-agent output for token efficiency |
| `summary_max_length` | int | `2000` | Max chars for result summary |
| `planning_strategy` | string | — | Override sub-agent planning strategy |

### Parallel Agent Tool (`type: parallel_agent`)

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `max_concurrency` | int | `3` | Maximum simultaneous sub-agents |
| `profile` | string | `dev` | Default profile for spawned sub-agents |

## Best Practices

1. **Assign non-overlapping files** to parallel workers to avoid conflicts.
2. **Use `coding_analyst`** for read-only investigation — safe for unrestricted parallelism.
3. **Keep `coding_reviewer` sequential** (no `auto_approve`) — reviews should happen after all workers finish.
4. **Start with `max_concurrency: 3`** and adjust based on system resources and API rate limits.
5. **Scope missions clearly** — each sub-agent mission should be self-contained with explicit file paths and expected outputs.

## Built-In Sub-Agent Profiles

| Profile | Purpose | Parallel-Safe |
|---------|---------|---------------|
| `coding_worker` | Implementation (read/write) | Yes (with care) |
| `coding_analyst` | Read-only codebase analysis | Yes |
| `coding_planner` | Task decomposition | Usually sequential |
| `coding_reviewer` | Quality review | Usually sequential |

Custom sub-agent configs live in `src/taskforce/configs/custom/`.

## Example: Coding Agent Workflow

```
User: "Refactor the authentication module and add rate limiting"

Orchestrator (coding_agent):
  1. coding_planner → decomposes into independent tasks
  2. call_agents_parallel:
       - coding_worker: "Refactor auth module in src/auth/"
       - coding_worker: "Add rate limiting middleware in src/middleware/"
     (runs concurrently — different file areas)
  3. coding_reviewer → reviews all changes sequentially
  4. Consolidate and report results
```

## Troubleshooting

**Sub-agents run sequentially despite `auto_approve: true`:**
- Check that `max_parallel_tools` in your profile is > 1 (default: 3)
- Verify the LLM is emitting multiple tool calls in one response (check logs)
- Ensure `supports_parallelism` is `True` on the tool (default for sub-agent tools)

**File conflicts between parallel workers:**
- Ensure the planner assigns non-overlapping file scopes
- Use `coding_analyst` instead of `coding_worker` for read-only tasks
- Consider reducing `max_concurrency` for write-heavy workflows
