# Sub-Agent Orchestration Analysis

**Date:** 2026-02-05
**Scope:** Complete analysis of the multi-agent orchestration system
**Files analyzed:** 25+ source files across all four architecture layers

---

## Table of Contents

1. [Architecture Overview](#1-architecture-overview)
2. [Component Deep-Dive](#2-component-deep-dive)
3. [Communication Patterns](#3-communication-patterns)
4. [Identified Bugs](#4-identified-bugs)
5. [Design Weaknesses](#5-design-weaknesses)
6. [Improvement Recommendations](#6-improvement-recommendations)
7. [Comparison with Alternative Approaches](#7-comparison-with-alternative-approaches)

---

## 1. Architecture Overview

Taskforce implements two distinct multi-agent orchestration patterns:

### Pattern A: Inline Orchestration ("Agents as Tools")

An orchestrator agent delegates tasks to specialist sub-agents via tool calls.

```
Orchestrator Agent (ReAct Loop)
    ├─ LLM decides: "call_agent" with specialist="coding"
    │   └─ AgentTool.execute()
    │       └─ SubAgentSpawner.spawn(SubAgentSpec)
    │           └─ Factory.create_agent() → Agent.execute()
    │               └─ Returns SubAgentResult → parent gets dict
    │
    ├─ LLM processes result, decides next action
    │   └─ "call_agent" with specialist="reviewer"
    │       └─ (same flow)
    │
    └─ LLM produces final answer
```

**Key files:**
- `infrastructure/tools/orchestration/agent_tool.py` — Primary `call_agent` tool
- `infrastructure/tools/orchestration/sub_agent_tool.py` — Fixed-specialist wrapper
- `application/sub_agent_spawner.py` — Agent lifecycle management
- `core/domain/sub_agents.py` — `SubAgentSpec`, `SubAgentResult`, session ID builder
- `core/interfaces/sub_agents.py` — `SubAgentSpawnerProtocol`

### Pattern B: Epic Orchestration (Planner/Worker/Judge Pipeline)

A structured multi-round pipeline with specialized roles.

```
EpicOrchestrator.run_epic()
    │
    ├─ Round 1:
    │   ├─ Planner Agent → decomposes mission into tasks (JSON array)
    │   ├─ Tasks published to MessageBus ("epic.tasks" topic)
    │   ├─ N Worker Agents consume tasks in parallel (asyncio.gather)
    │   ├─ Judge Agent reviews all results → {summary, continue: bool}
    │   └─ State persisted to MISSION.md / CURRENT_STATE.md / MEMORY.md
    │
    ├─ Round 2 (if judge says continue):
    │   ├─ Planner reads MEMORY.md, adapts plan
    │   └─ ... same cycle ...
    │
    └─ Final: EpicRunResult with all tasks, results, summaries
```

**Key files:**
- `application/epic_orchestrator.py` — Round loop, task dispatch, role coordination
- `application/epic_state_store.py` — File-based state (3 Markdown files per run)
- `core/domain/epic.py` — `EpicTask`, `EpicTaskResult`, `EpicRunResult`
- `core/interfaces/messaging.py` — `MessageBusProtocol`
- `taskforce/infrastructure/messaging/in_memory_bus.py` — Queue-based bus

---

## 2. Component Deep-Dive

### 2.1 Session ID Hierarchy

Session isolation is the foundation of multi-agent coordination:

```python
# core/domain/sub_agents.py
def build_sub_agent_session_id(parent_session_id, label, suffix=None):
    safe_label = label.replace(" ", "_") if label else "generic"
    suffix_value = suffix or uuid4().hex[:8]
    return f"{parent_session_id}--sub_{safe_label}_{suffix_value}"
```

Example hierarchy:
```
session-abc123                                    # Parent
├── session-abc123--sub_coding_planner_a1b2c3d4  # Planner sub-agent
├── session-abc123--sub_coding_worker_e5f6g7h8   # Worker sub-agent
│   └── session-abc123--sub_coding_worker_e5f6g7h8--sub_reviewer_i9j0  # Nested
└── session-abc123--sub_rag_k1l2m3n4             # RAG sub-agent
```

Each session ID namespaces state completely. The `FileStateManager` stores state
by session_id, ensuring full isolation of message history, plans, and tool results.

### 2.2 AgentTool (call_agent)

The `AgentTool` has two execution modes:

**Mode 1: Via SubAgentSpawner** (when `self._spawner` is set)
- Creates `SubAgentSpec` from parameters
- Delegates to spawner which handles full lifecycle
- Returns formatted `SubAgentResult`

**Mode 2: Direct factory creation** (fallback)
- Searches for custom config via `_find_agent_config()`
- Creates agent directly via `self._factory.create_agent()`
- Executes and cleans up manually

The dual-path design introduces inconsistency (see Bug #1 below).

### 2.3 SubAgentTool (Fixed-Specialist Wrapper)

Wraps `AgentTool` with a pre-configured specialist, exposing only `mission` as parameter:

```python
class SubAgentTool:
    async def execute(self, mission, **kwargs):
        return await self._agent_tool.execute(
            mission=mission,
            specialist=self._specialist,      # Fixed
            planning_strategy=self._planning_strategy,  # Fixed
            **kwargs,
        )
```

This enables profiles like `coding_agent.yaml` to define named delegation tools
(e.g., `coding_planner`, `coding_worker`, `coding_reviewer`).

### 2.4 InMemoryMessageBus

```python
class InMemoryMessageBus:
    _topics: dict[str, asyncio.Queue[MessageEnvelope]]
    _messages: dict[str, MessageEnvelope]
```

- Pub/Sub with topic-based routing via `asyncio.Queue`
- ACK removes message from tracking dict
- NACK with `requeue=True` puts message back in queue
- No persistence, no dead letter queue, no TTL

### 2.5 Agent Communication via External Providers

A separate communication layer (Telegram, Teams) enables external user interaction:
- `CommunicationService` orchestrates inbound messages → agent execution → outbound reply
- `FileConversationStore` persists conversation history as JSON files
- Session mapping ensures conversation continuity across messages

This is **not** agent-to-agent communication but rather user-to-agent via external platforms.

---

## 3. Communication Patterns

### 3.1 How Do Agents Communicate?

**Short answer: They don't communicate directly with each other.**

The system uses a **hierarchical delegation model** where communication flows
exclusively through parent-child relationships:

```
                  ┌─────────────────┐
                  │  Parent Agent   │
                  │  (Orchestrator) │
                  └────┬───────┬────┘
                       │       │
              Result ↑ │       │ ↓ Delegate
                       │       │
              ┌────────┘       └────────┐
              │                         │
     ┌────────┴────────┐      ┌────────┴────────┐
     │  Sub-Agent A    │      │  Sub-Agent B    │
     │  (Planner)      │      │  (Worker)       │
     └─────────────────┘      └─────────────────┘
              ↕ NO DIRECT COMMUNICATION ↕
```

**Communication mechanisms that exist:**

| Mechanism | Pattern | Used For |
|-----------|---------|----------|
| Tool return value | Child → Parent (sync) | Sub-agent results to orchestrator |
| Tool call parameters | Parent → Child (sync) | Mission delegation |
| MessageBus (epic) | Planner → Workers (async, one-way) | Task distribution only |
| Shared filesystem | Implicit (via file tools) | Workers can read/write same files |
| MEMORY.md state files | Planner reads previous round results | Cross-round context |

**Communication mechanisms that DO NOT exist:**

- No direct agent-to-agent messaging (peer-to-peer)
- No shared memory or blackboard between sibling sub-agents
- No event/notification system between concurrent sub-agents
- No streaming of intermediate results from sub-agent to parent
- No ability for sub-agent to request help from a sibling

### 3.2 Epic Orchestration Data Flow

The MessageBus in epic orchestration is strictly unidirectional:

```
Planner                          Workers                    Judge
   │                                │                         │
   │ ──publish tasks──►  Queue      │                         │
   │                    ┌──────┐    │                         │
   │                    │Task 1│──► │ Worker 1                │
   │                    │Task 2│──► │ Worker 2                │
   │                    │Task 3│──► │ Worker 3                │
   │                    │STOP  │──► │ (shutdown)              │
   │                    │STOP  │──► │ (shutdown)              │
   │                    │STOP  │──► │ (shutdown)              │
   │                    └──────┘    │                         │
   │                                │                         │
   │                                │ ──results list──►       │
   │                                │ (via Python list,       │
   │                                │  not message bus)       │
```

Workers do **not** publish results to the message bus. Results are collected in a
shared Python list protected by `asyncio.Lock`. The judge receives results as a
formatted string in its prompt, not via the bus.

---

## 4. Identified Bugs

### Bug #1: SubAgentTool Never Receives Parent Session ID (CRITICAL)

**Location:** `core/domain/lean_agent.py:419`

```python
# Line 419: Only injects for tool_name == "call_agent"
if tool_name == "call_agent" and session_id:
    tool_args = {**tool_args, "_parent_session_id": session_id}
```

`SubAgentTool` instances have custom names (e.g., `"coding_planner"`,
`"delegate_to_reviewer"`), NOT `"call_agent"`. The condition `tool_name == "call_agent"`
never matches for SubAgentTools.

**Impact:**
- `AgentTool.execute()` receives `_parent_session_id = "unknown"` (default)
- Sub-agent session IDs become `"unknown--sub_coding_planner_abc123"`
- Session hierarchy is broken — no trace back to parent
- State files stored under "unknown" prefix, not linked to parent session
- Debugging and state inspection become impossible

**Fix:** The condition should check whether the tool is any orchestration tool, not
just `"call_agent"`. For example:

```python
# Option A: Check tool instance type
if hasattr(tool, 'requires_parent_session') and session_id:
    tool_args = {**tool_args, "_parent_session_id": session_id}

# Option B: Check all orchestration tool names
ORCHESTRATION_TOOLS = {"call_agent", "coding_planner", "coding_worker", ...}
if tool_name in ORCHESTRATION_TOOLS and session_id:
    tool_args = {**tool_args, "_parent_session_id": session_id}

# Option C (cleanest): Always inject, let tools ignore if unneeded
tool_args = {**tool_args, "_parent_session_id": session_id}
```

### Bug #2: Resource Leak on Sub-Agent Execution Failure

**Location:** `infrastructure/tools/orchestration/agent_tool.py:340-346`

```python
result = await sub_agent.execute(mission=mission, session_id=sub_session_id)
# Cleanup sub-agent resources (MCP connections, etc.)
await sub_agent.close()  # ← Only reached if execute() succeeds!
```

If `sub_agent.execute()` raises an exception, `sub_agent.close()` is never called.
MCP connections, file handles, and other resources leak.

**Same issue in:** `application/sub_agent_spawner.py:48-49`

```python
result = await agent.execute(mission=spec.mission, session_id=session_id)
await agent.close()  # ← Same problem
```

**Fix:** Use try/finally:

```python
try:
    result = await sub_agent.execute(...)
finally:
    await sub_agent.close()
```

### Bug #3: Epic Orchestrator Uses Static "epic" Parent Session

**Location:** `application/epic_orchestrator.py:334, 430`

```python
# Planner session — always uses "epic" as parent, ignoring run_id
session_id = build_sub_agent_session_id("epic", scope or "planner")

# Judge session — same issue
session_id = build_sub_agent_session_id("epic", "judge")
```

But worker sessions correctly use `run_id`:
```python
# Worker session — correctly uses run_id
session_id = build_sub_agent_session_id(run_id, f"worker_{task.task_id}")
```

**Impact:** Concurrent epic runs share the "epic" prefix for planner and judge
sessions. Since `build_sub_agent_session_id` appends a random suffix, session IDs
won't collide, but the hierarchy is inconsistent and confusing:
- Planner: `epic--sub_planner_abc123` (no run_id link)
- Worker: `a1b2c3d4--sub_worker_task-1_def456` (has run_id)
- Judge: `epic--sub_judge_ghi789` (no run_id link)

**Fix:** Use `run_id` consistently for all roles.

### Bug #4: EpicRunResult `started_at` Timestamp Is Wrong

**Location:** `application/epic_orchestrator.py:464-465`

```python
return EpicRunResult(
    run_id=run_id,
    started_at=_utc_now(),   # ← Set at END of execution
    completed_at=_utc_now(),
    ...
)
```

Both `started_at` and `completed_at` are set when building the result after all
rounds complete. The `started_at` should be captured at the beginning of `run_epic()`.

### Bug #5: Blocking I/O in SubAgentSpawner

**Location:** `application/sub_agent_spawner.py:105-106`

```python
with open(config_path) as handle:
    return yaml.safe_load(handle) or None
```

Uses synchronous `open()` in what is called from an async context. This blocks the
event loop. Should use `aiofiles` consistent with the project's async-everywhere policy.

---

## 5. Design Weaknesses

### 5.1 Dual Execution Paths in AgentTool

`AgentTool.execute()` has two completely separate code paths:

```python
if self._spawner:
    # Path A: Delegate to spawner (20 lines)
    spec = SubAgentSpec(...)
    result = await self._spawner.spawn(spec)
    return self._format_spawner_result(result)

# Path B: Direct factory creation (60 lines)
sub_agent = await self._factory.create_agent(...)
result = await sub_agent.execute(...)
await sub_agent.close()
return {...}
```

Both paths do essentially the same thing but with different error handling, different
session ID generation, and different result formatting. Path B builds its own session
ID (line 267-268) but Path A lets the spawner build it. Path B has the resource leak
bug; Path A inherits the same bug from the spawner.

**Recommendation:** Remove Path B entirely. Always use the spawner. The `AgentTool`
should not duplicate factory/lifecycle logic.

### 5.2 No Timeout Mechanism for Sub-Agents

Sub-agents are limited only by `max_steps`. There is no wall-clock timeout:

```python
# Current: no timeout
result = await agent.execute(mission=spec.mission, session_id=session_id)

# Missing: timeout wrapper
result = await asyncio.wait_for(
    agent.execute(mission=spec.mission, session_id=session_id),
    timeout=300,  # 5 minutes
)
```

A stuck LLM call or infinite tool loop can block the parent indefinitely.

### 5.3 Worker Agent Reuse in Epic Orchestration

**Location:** `application/epic_orchestrator.py:385-396`

```python
async def _worker_loop(self, ...):
    agent = await self._factory.create_agent(profile=worker_profile)
    async for message in self._bus.subscribe("epic.tasks"):
        # Same agent instance processes multiple tasks!
        task = EpicTask.from_dict(payload)
        result = await self._execute_worker(agent, ...)
```

The worker agent accumulates message history across tasks. After processing 3-4
tasks, the context window fills up with previous task histories, potentially causing:
- Context overflow (hitting token limits)
- Cross-contamination between task contexts
- Degraded LLM performance from irrelevant context

Each task uses a different `session_id`, but the agent's in-memory message list
may not be cleared between executions depending on the `execute()` implementation.

### 5.4 No File Conflict Resolution Between Workers

Multiple workers can read and write the same files simultaneously. The shared
filesystem is the only "communication channel" between workers, but there's no:
- File locking mechanism
- Merge conflict detection
- Write ordering guarantees

Worker 1 and Worker 2 both editing `src/app.py` will silently overwrite each other.
The judge is expected to "consolidate conflicts" but has no diff/merge tools — only
`file_read`, `file_write`, and `git`.

### 5.5 Message Bus Has No Durability or Error Recovery

The `InMemoryMessageBus` is purely ephemeral:

- **No persistence:** Process crash = all messages lost
- **No dead letter queue:** Failed messages after ACK are gone forever
- **No message TTL:** Unprocessed messages remain in queue forever
- **No retry policy:** If NACK without requeue, message is dropped
- **Single consumer:** No fan-out/broadcast capability (competing consumers only)

For local development this is acceptable, but the protocol claims to be swappable
with Redis/NATS/SQS implementations that don't exist yet.

### 5.6 No Observability for Sub-Agent Execution

When a parent agent delegates to a sub-agent, the parent receives only the final
result. There is no:
- Streaming of intermediate progress from sub-agent to parent
- Event emission visible to the user during sub-agent execution
- Progress tracking (how many steps has the sub-agent taken?)
- Cancellation mechanism (parent can't cancel a running sub-agent)

The user sees the parent agent "thinking" for the entire duration of the sub-agent
execution with no visibility into what's happening.

### 5.7 Hardcoded Specialist Names in Description

**Location:** `agent_tool.py:88-93`

```python
"Available specialists: "
"'coding' (file operations, shell commands, git), "
"'rag' (semantic search, document retrieval), "
"'wiki' (Wikipedia research). "
```

Available specialists are hardcoded in the tool description. Custom agents in
`configs/custom/` are mentioned generically but not enumerated. The LLM may not
discover custom specialists effectively.

---

## 6. Improvement Recommendations

### 6.1 Immediate Fixes (Bugs)

| Priority | Issue | Fix |
|----------|-------|-----|
| **P0** | SubAgentTool missing `_parent_session_id` | Generalize injection in `lean_agent.py` to all tools with `requires_approval` or a new marker |
| **P0** | Resource leak on execution failure | Wrap `execute()` + `close()` in try/finally in both `AgentTool` and `SubAgentSpawner` |
| **P1** | Epic planner/judge use static "epic" parent | Use `run_id` consistently |
| **P1** | Blocking I/O in `SubAgentSpawner` | Replace `open()` with `aiofiles.open()` |
| **P2** | Wrong `started_at` timestamp | Capture timestamp at start of `run_epic()` |

### 6.2 Architectural Improvements

#### A. Eliminate Dual Code Paths in AgentTool

Remove the direct factory creation path. `AgentTool` should always delegate to
`SubAgentSpawner`. This eliminates duplicated lifecycle management and ensures
consistent behavior:

```python
class AgentTool:
    def __init__(self, sub_agent_spawner: SubAgentSpawnerProtocol, ...):
        self._spawner = sub_agent_spawner  # Required, not optional

    async def execute(self, mission, specialist=None, ...):
        spec = SubAgentSpec(...)
        result = await self._spawner.spawn(spec)
        return self._format_result(result)
```

#### B. Add Sub-Agent Timeout

Wrap sub-agent execution in `asyncio.wait_for()`:

```python
async def spawn(self, spec: SubAgentSpec) -> SubAgentResult:
    timeout = spec.timeout or self._default_timeout
    try:
        result = await asyncio.wait_for(
            agent.execute(mission=spec.mission, session_id=session_id),
            timeout=timeout,
        )
    except asyncio.TimeoutError:
        return SubAgentResult(status="timeout", success=False, ...)
    finally:
        await agent.close()
```

#### C. Add Sub-Agent Progress Streaming

Instead of blocking on `agent.execute()`, use `agent.execute_stream()` and forward
events to the parent's stream:

```python
async def spawn_streaming(self, spec: SubAgentSpec) -> AsyncIterator[StreamEvent]:
    agent = await self._create_agent(spec)
    async for event in agent.execute_stream(spec.mission, session_id):
        yield event  # Parent can forward to user
    yield SubAgentResult(...)
```

#### D. Fresh Agent Per Task in Epic Workers

Create a new agent instance per task to prevent context accumulation:

```python
async def _worker_loop(self, ...):
    async for message in self._bus.subscribe("epic.tasks"):
        if payload.get("type") == "shutdown":
            break
        task = EpicTask.from_dict(payload)
        agent = await self._factory.create_agent(profile=worker_profile)
        try:
            result = await self._execute_worker(agent, ...)
        finally:
            await agent.close()
```

#### E. Dynamic Specialist Discovery

Build the tool description dynamically from available configs:

```python
@property
def description(self) -> str:
    custom_agents = self._discover_custom_agents()
    agents_text = ", ".join(f"'{a}'" for a in custom_agents)
    return f"Delegate to sub-agent. Available: {agents_text}"
```

### 6.3 Future Architecture Considerations

#### Shared Context / Blackboard Pattern

For tasks requiring coordination between sibling sub-agents, consider a shared
context store (blackboard pattern):

```
┌─────────────────────────────────────┐
│           Blackboard                │
│  ┌─────────────────────────────┐   │
│  │ "file_changes": [...]       │   │
│  │ "decisions": [...]          │   │
│  │ "blockers": [...]           │   │
│  └─────────────────────────────┘   │
└──────┬──────────┬──────────┬───────┘
       │          │          │
    Worker 1   Worker 2   Worker 3
```

Workers would read/write to the blackboard instead of implicitly conflicting on
the filesystem.

#### Event-Driven Architecture

Replace the current request-response model with event-driven coordination:

```python
class AgentEvent(Protocol):
    event_type: str    # "task_started", "file_modified", "help_needed"
    agent_id: str
    payload: dict

class EventBus(Protocol):
    async def emit(self, event: AgentEvent) -> None
    async def subscribe(self, event_type: str) -> AsyncIterator[AgentEvent]
```

This would enable:
- Sub-agent progress visible to parent and user
- Cross-agent notifications (e.g., "I modified file X, you should re-read")
- Dynamic re-planning when a sub-agent encounters blockers

#### Structured Result Protocol

Replace the current `dict[str, Any]` return from tools with a typed protocol:

```python
@dataclass(frozen=True)
class OrchestrationResult:
    success: bool
    result: str
    session_id: str
    status: ExecutionStatus
    error: str | None
    artifacts: list[str]  # Files created/modified
    token_usage: TokenUsage
    steps_taken: int
    duration_seconds: float
```

---

## 7. Comparison with Alternative Approaches

### 7.1 Current: Hierarchical Delegation (Agents as Tools)

```
Pros:
+ Simple mental model (parent delegates, child returns)
+ Clean session isolation
+ Supports nested sub-agents naturally
+ Protocol-based, extensible

Cons:
- No peer-to-peer communication
- No streaming of sub-agent progress
- Parent blocks during sub-agent execution
- No shared context between siblings
```

### 7.2 Alternative: Graph-Based Orchestration (e.g., LangGraph)

```
Define agent workflow as directed graph:
  Planner → [Worker1 || Worker2 || Worker3] → Reviewer → (conditional → Planner)

Pros:
+ Explicit workflow definition
+ Conditional routing built-in
+ Visual debugging (graph visualization)
+ Streaming and checkpoints native

Cons:
- Requires upfront workflow definition
- Less flexible for dynamic delegation
- Additional framework dependency
```

### 7.3 Alternative: Actor Model (e.g., Erlang/Akka-style)

```
Each agent is an actor with:
  - Own mailbox (message queue)
  - Own state (isolated)
  - Can send messages to any other actor by ID

Pros:
+ True peer-to-peer communication
+ Fault isolation (supervisor patterns)
+ Location transparency (local or distributed)
+ Natural for concurrent execution

Cons:
- Harder to reason about (no central coordinator)
- Debugging distributed message flows
- More complex implementation
```

### 7.4 Alternative: Crew/Team Pattern (e.g., CrewAI)

```
Define a crew with:
  - Roles (researcher, writer, reviewer)
  - Tasks with dependencies
  - Sequential or parallel execution

Pros:
+ Role-based thinking (natural for humans)
+ Built-in task dependencies
+ Delegation and collaboration patterns

Cons:
- Fixed role assignments
- Less dynamic than tool-based delegation
- Overhead for simple single-delegation cases
```

### 7.5 Recommendation

The current hierarchical delegation model is appropriate for Taskforce's use case
(autonomous task execution). The key improvements needed are:

1. **Fix the identified bugs** (especially `_parent_session_id` injection)
2. **Add progress streaming** from sub-agents to parent
3. **Add timeout and cancellation** for sub-agent executions
4. **Consider a lightweight shared context** (blackboard) for epic workers
5. **Keep the protocol-based design** — it allows future migration to actor model
   or graph-based orchestration without changing the core domain

The protocol-based architecture (`SubAgentSpawnerProtocol`, `MessageBusProtocol`)
already provides the extension points needed. The implementation gaps are in the
concrete implementations, not the architecture.

---

## Summary of Findings

| Area | Status | Notes |
|------|--------|-------|
| Architecture design | Good | Clean Architecture respected, protocol-based |
| Session isolation | Good | Hierarchical IDs, separate state per session |
| AgentTool (call_agent) | Has bugs | Dual paths, resource leaks, works for basic cases |
| SubAgentTool | Broken | `_parent_session_id` never injected |
| Epic orchestration | Functional | Works but has timestamp and session ID issues |
| Inter-agent communication | Limited | No direct agent-to-agent messaging |
| MessageBus | Minimal | In-memory only, no durability, no monitoring |
| Error handling | Incomplete | Resource leaks, no timeouts |
| Observability | Missing | No sub-agent progress streaming |
| Testing | Adequate | Integration tests cover main paths, edge cases missing |
