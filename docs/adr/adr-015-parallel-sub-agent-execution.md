# ADR-015: Parallel Sub-Agent Execution

**Status:** Accepted
**Date:** 2026-03-09
**Deciders:** Team
**Context:** Taskforce multi-agent orchestration framework

---

## Context and Problem Statement

Sub-agents in Taskforce already declare `supports_parallelism = True`, indicating they are designed for concurrent execution (isolated sessions, independent state). However, the parallel execution gate in `_execute_tool_calls()` enforces:

```python
can_parallel = (
    tool and getattr(tool, "supports_parallelism", False)
    and not tool.requires_approval
)
```

Since both `AgentTool` and `SubAgentTool` set `requires_approval = True`, sub-agents **never** run in parallel — even when the LLM emits multiple tool calls in a single response.

This is a significant bottleneck for orchestration workflows like the `coding_agent`, where a planner creates multiple independent tasks that could be executed concurrently by separate coding workers.

### Current Architecture

| Component | Supports Parallelism | Requires Approval | Effective Parallel |
|-----------|---------------------|-------------------|--------------------|
| `AgentTool` | Yes | Yes | **No** |
| `SubAgentTool` | Yes | Yes | **No** |
| Other tools | Opt-in | Varies | Yes (if both conditions met) |

## Decision

Implement parallel sub-agent execution through two complementary mechanisms:

### Mechanism 1: `auto_approve` Flag (Config-Driven)

Add a configurable `auto_approve: bool` parameter to `AgentTool` and `SubAgentTool`. When enabled:
- `requires_approval` returns `False`
- The existing parallel execution gate in `_execute_tool_calls()` naturally allows concurrent execution
- No changes needed to the core parallel execution logic

This is safe because:
- Auto-approval only skips the **parent-level** approval for spawning
- Sub-agents still enforce their own tool-level approval internally
- The configuration is explicit and opt-in per sub-agent tool in the profile YAML

### Mechanism 2: `call_agents_parallel` Tool (Batch Dispatch)

A new dedicated tool that accepts a list of missions and dispatches them concurrently:
- Uses `asyncio.Semaphore` for configurable concurrency control
- Uses `asyncio.gather(return_exceptions=True)` for partial failure resilience
- Manages its own parallelism internally (doesn't rely on the tool-level parallel gate)
- Returns aggregated results with per-mission success/failure status

## Alternatives Considered

### Batch Approval

Modify `_execute_tool_calls()` to approve all parallel sub-agent calls as a single batch. Rejected because:
- Requires changes to the core approval infrastructure
- More complex to implement for minimal benefit over `auto_approve`

### Always-Parallel Sub-Agents

Remove `requires_approval` from sub-agent tools entirely. Rejected because:
- Breaks the security model for profiles that don't want auto-approved sub-agents
- Not backward-compatible

## Configuration

```yaml
# In profile YAML (e.g., coding_agent.yaml)
tools:
  - type: sub_agent
    name: coding_worker
    auto_approve: true       # Enables parallel execution
    summarize_results: true

  - type: parallel_agent     # Batch dispatch tool
    max_concurrency: 3
```

## Consequences

### Positive
- Coding agent workflows can execute independent tasks concurrently
- No changes to core execution logic — works with existing `asyncio.Semaphore` infrastructure
- Backward-compatible — default behavior unchanged (`auto_approve: false`)
- Two complementary approaches: LLM-driven (multiple tool calls) and explicit (batch tool)

### Negative
- `auto_approve` reduces the security boundary for approved sub-agents
- Parallel sub-agents sharing the same filesystem may encounter file conflicts for overlapping tasks

### Mitigations
- The planner should assign non-overlapping files to different workers
- Sub-agents still enforce their own internal tool approval
- Concurrency is bounded by `max_parallel_tools` (default: 3)

## Files Changed

| File | Change |
|------|--------|
| `infrastructure/tools/orchestration/agent_tool.py` | Added `auto_approve` parameter |
| `infrastructure/tools/orchestration/sub_agent_tool.py` | Added `auto_approve` parameter |
| `infrastructure/tools/orchestration/parallel_agent_tool.py` | **New** — `ParallelAgentTool` |
| `infrastructure/tools/orchestration/__init__.py` | Export `ParallelAgentTool` |
| `infrastructure/tools/registry.py` | Register `call_agents_parallel` |
| `application/tool_builder.py` | Wire `auto_approve` and `parallel_agent` type |
| `configs/coding_agent.yaml` | Enable `auto_approve` for `coding_worker` and `coding_analyst` |
| `configs/custom/coding_analyst.yaml` | **New** — Read-only analysis sub-agent for parallel codebase exploration |
