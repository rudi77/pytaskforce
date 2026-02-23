# Codebase Improvement & Simplification Recommendations

**Date:** 2026-02-22
**Scope:** Full codebase review across all four architectural layers (186 source files, ~41k lines)

---

## Executive Summary

The pytaskforce codebase has strong architectural foundations — Clean Architecture with protocol-based design, async-first I/O, and well-structured layering. However, several areas of accumulated complexity would benefit from simplification. The highest-impact changes are consolidating duplicated agent model definitions, reducing the factory's surface area, and eliminating unused abstractions.

Recommendations are ordered by **impact** (highest first).

---

## 1. Consolidate Agent Definition Models (HIGH IMPACT)

**Problem:** There are **three parallel sets** of agent definition models with significant overlap:

| File | Classes | Lines |
|------|---------|-------|
| `core/domain/agent_definition.py` | `AgentDefinition`, `AgentDefinitionInput`, `AgentDefinitionUpdate`, `MCPServerConfig`, `AgentSource` | 573 |
| `core/domain/agent_models.py` | `CustomAgentDefinition`, `ProfileAgentDefinition`, `PluginAgentDefinition`, `CustomAgentInput`, `CustomAgentUpdateInput` | 121 |
| `core/domain/config_schema.py` | `AgentConfigSchema`, `MCPServerConfigSchema`, `AgentSourceType` | 445 |

This creates concrete duplication:
- `AgentSource` (enum in `agent_definition.py`) vs `AgentSourceType` (enum in `config_schema.py`) — identical values, different types
- `MCPServerConfig` (dataclass) vs `MCPServerConfigSchema` (Pydantic) — identical structure, different classes
- `CustomAgentDefinition` still actively imported in **6 files** despite `AgentDefinition` being the stated "unified" replacement
- Three different classes (`CustomAgentInput`, `AgentDefinitionInput`, `AgentConfigSchema`) all represent "create an agent" input

**Recommendation:** Complete the migration to `AgentDefinition` as the single domain model. Retire `agent_models.py` entirely. Keep Pydantic validation schemas only in the API layer (`api/schemas/`) for request/response validation — not as core domain models.

Additionally, within `agent_definition.py` itself, the factory methods `from_custom()`, `from_profile()`, and `from_plugin()` (lines 264-376) each duplicate identical tool-extraction and MCP-server-extraction logic — the same list comprehension appears 3 times.

**Estimated reduction:** ~700 lines, 1 file removed, clearer single source of truth.

---

## 2. Shrink `factory.py` — Too Many Responsibilities (HIGH IMPACT)

**Problem:** `factory.py` is **1,644 lines** with **75 methods** on `AgentFactory`. It is the largest file in the project and has several structural issues:

### 2a. ~215 lines of pure delegation stubs (lines 1430-1644)

Twelve methods do nothing but forward to `self._tool_builder`:

```python
def _create_tools_from_allowlist(self, ...):
    return await self._tool_builder.create_tools_from_allowlist(...)

def _get_all_native_tools(self, ...):
    return self._tool_builder.get_all_native_tools(...)
# ... 10 more like this
```

**Fix:** Delete these. Callers should use `self._tool_builder` directly.

### 2b. `InfrastructureBuilder` instantiated 5 times

The same `InfrastructureBuilder(self.config_dir)` is created as a local variable in 5 different methods, each with a local import:

```python
# Line 286, 302, 328, 996, 1022 — same pattern repeated
from taskforce.application.infrastructure_builder import InfrastructureBuilder
infra_builder = InfrastructureBuilder(self.config_dir)
```

**Fix:** Create once in `__init__` as `self._infra_builder`.

### 2c. Legacy API alongside unified API

The file contains both:
- The "new unified API" (`create()` method, lines 200-481)
- The "legacy API" (`create_agent()`, `create_agent_with_plugin()`, lines 486-1405)

Both are actively used, but the legacy methods already delegate to `create()` internally.

**Fix:** Mark legacy methods `@deprecated` and migrate callers over time. Or, if no external consumers depend on the legacy signatures, remove them.

### 2d. Hardcoded business logic

Lines 1383-1405 contain hardcoded skill-switch conditions for `smart-booking-auto`/`smart-booking-hitl` — a specific use-case embedded in the generic factory.

**Fix:** Move to configuration (YAML) or a plugin-level registration.

**Estimated reduction:** 1,644 → ~800 lines, 75 → ~35 methods.

---

## 3. Replace Internal `dict[str, Any]` with Typed Structures (MEDIUM IMPACT)

**Problem:** The factory and infrastructure builder use `dict[str, Any]` as the primary data carrier between internal methods. Example from `_build_infrastructure()`:

```python
return {
    "state_manager": ...,
    "llm_provider": ...,
    "context_policy": ...,
    "runtime_tracker": ...,
    "model_alias": ...,
    "mcp_contexts": [],
}
```

There are **104 `dict[str, Any]` usages** in `factory.py` alone. These are accessed by string keys in downstream methods with no type checking, violating the project's own coding standard: *"Use `dataclass`, `NamedTuple`, or Pydantic `BaseModel` instead of `dict`."*

**Recommendation:** Replace with named dataclasses:

```python
@dataclass
class InfraBundle:
    state_manager: StateManagerProtocol
    llm_provider: LLMProviderProtocol
    context_policy: ContextPolicy
    runtime_tracker: AgentRuntimeTrackerProtocol | None
    model_alias: str
    mcp_contexts: list[Any]

@dataclass
class AgentSettings:
    max_steps: int | None
    max_parallel_tools: int | None
    planning_strategy: PlanningStrategy
    model_alias: str
```

---

## 4. Simplify `tool_result_store.py` Interface File (MEDIUM IMPACT)

**Problem:** `core/interfaces/tool_result_store.py` is **409 lines** — the largest interface file by far. Only ~100 lines are the actual `ToolResultStoreProtocol`. The rest is concrete implementation:

- `ToolResultHandle` — dataclass with serialization and lineage tracking (95 lines)
- `ToolResultPreview` — dataclass (32 lines)
- `LineageNode` — dataclass (27 lines)
- `LineageGraph` — full graph implementation with DFS traversal and Mermaid diagram rendering (125 lines)

A `LineageGraph` with `to_mermaid()` is application-level visualization logic, not a protocol concern.

**Recommendation:** Move `ToolResultHandle`, `ToolResultPreview`, `LineageNode`, and `LineageGraph` to `core/domain/tool_result.py` (which already exists as a thin file). Keep only the protocol definition in the interface file.

---

## 5. Reduce Planning Strategy Duplication (MEDIUM IMPACT)

**Problem:** `planning_strategy.py` (951 lines) + `planning_helpers.py` (529 lines) = **1,480 lines** for planning. All four strategy classes share an almost identical pattern:

```python
async def execute(self, agent, mission, session_id):
    return await _collect_result(session_id, self.execute_stream(agent, mission, session_id))
```

The streaming implementations share the same core ReAct loop (call LLM → process tool calls → check completion → repeat), varying only in whether they generate a plan upfront and whether they add a reflection step. Specific large methods:

- `NativeReActStrategy.execute_stream()`: ~216 lines
- `SparStrategy.execute_stream()`: ~172 lines
- `PlanAndExecuteStrategy.execute_stream()`: ~163 lines

All three duplicate the system-prompt rebuild pattern (`messages[0] = {"role": ..., "content": agent._build_system_prompt(...)}`) and share identical state loading/resumption and error handling logic.

**Recommendation:** Extract a shared `_react_loop()` async generator that strategies compose with optional pre/post phases. For example:

```python
class SparStrategy:
    async def execute_stream(self, agent, mission, session_id):
        plan = await _generate_plan(agent, mission)   # Sense + Plan
        async for event in _react_loop(agent, ...):    # Act (shared)
            yield event
        yield from _reflect(agent, ...)                # Reflect (SPAR-specific)
```

**Estimated reduction:** 200-300 lines of near-duplicate code.

---

## 6. Unify `executor.py` Entry Points (MEDIUM IMPACT)

**Problem:** `executor.py` at **1,464 lines** is the second-largest file. It provides **6+ entry methods** that share 80%+ of their logic:

- `execute_mission()` / `execute_mission_streaming()`
- `execute_with_agent()` / `execute_with_agent_streaming()`
- `execute_mission_with_custom_agent()`
- `execute_mission_with_plugin()`

Each duplicates session ID generation, error handling, event emission, and logging. Additionally, `ProgressUpdate` is nearly identical to the existing `StreamEvent` dataclass.

**Recommendations:**

a. **Eliminate `ProgressUpdate`** and standardize on `StreamEvent` everywhere.

b. **Consolidate to a single `execute()` method** that accepts a discriminated config:

```python
async def execute(self, config: ExecutionConfig) -> AsyncIterator[StreamEvent]:
    # Single implementation handling all modes
```

Where `ExecutionConfig` is a union of `ProfileExecution`, `CustomAgentExecution`, and `PluginExecution`.

---

## 7. Clean Up `agent.py` / `lean_agent.py` Naming (LOW IMPACT, EASY WIN)

**Problem:** `core/domain/agent.py` is a 5-line re-export shim:

```python
from taskforce.core.domain.lean_agent import Agent
__all__ = ["Agent"]
```

`lean_agent.py` still carries a docstring referencing "Key differences from legacy Agent" for a class that has been removed. The "lean" prefix suggests a transitional state that appears complete.

**Recommendation:** Rename `lean_agent.py` → `agent.py` (updating all imports) and remove the legacy references from the docstring. Alternatively, if the rename is too disruptive, just clean up the docstring.

---

## 8. Reduce Interface Proliferation for Single-Implementation Protocols (LOW IMPACT)

**Problem:** 18 interface files define ~30 protocols. Several are very thin with exactly one implementation:

| Interface File | Lines | Methods | Implementations |
|----------------|-------|---------|-----------------|
| `sub_agents.py` | 15 | 1 | 1 |
| `logging.py` | 29 | 5 | mirrors `structlog` exactly |
| `messaging.py` | 35 | 3 | 1 (InMemoryMessageBus) |
| `tool_mapping.py` | 42 | 3 | 1 |
| `memory_store.py` | 45 | 4 | 1 |

Additionally, in `skills.py` (355 lines, 4 protocols), `SkillMetadata` is a pure subset of `SkillProtocol` — it defines `name`, `description`, `source_path`, `skill_type` which `SkillProtocol` already includes. It can be removed entirely.

**Recommendation:** Remove `SkillMetadata` (use `SkillProtocol` directly). `LoggerProtocol` that mirrors `structlog` exactly adds no abstraction value — use `structlog.stdlib.BoundLogger` directly. The single-method `SubAgentSpawnerProtocol` could be inlined or merged with related protocols. This is a minor cleanup but reduces the number of files to navigate.

---

## 9. Butler Subsystem Is Over-Abstracted for Its Maturity (LOW IMPACT)

**Problem:** The Butler subsystem spans:
- 6 domain model files (`agent_event.py`, `schedule.py`, `trigger_rule.py`, etc.)
- 6 interface files (`event_source.py`, `scheduler.py`, `rule_engine.py`, `learning.py`, etc.)
- 8+ implementation files

Each interface has exactly one implementation. The full Protocol → Implementation → Service layering is premature for a subsystem at this stage.

**Recommendation:** Start with concrete classes and extract protocols only when a second implementation appears. Python's duck typing and structural subtyping make this easy to do later without breaking changes.

---

## 10. Remove Backward-Compatibility Aliases (LOW IMPACT, EASY WIN)

**Problem:** Several files exist solely as compatibility shims:
- `infrastructure/llm/openai_service.py` — re-exports `LiteLLMService` under the old name
- `core/domain/agent.py` — re-exports from `lean_agent.py`

**Recommendation:** If these are internal (not consumed by external packages), delete them and update imports. If external, add `warnings.warn("Deprecated, use X instead", DeprecationWarning)`.

---

## 11. `plugin_loader.py` Does Too Much (LOW IMPACT)

**Problem:** `application/plugin_loader.py` at **646 lines** handles plugin discovery, manifest creation, config loading, tool validation, tool instantiation, skill path resolution, and more. A separate `plugin_discovery.py` (100 lines) already exists but duplicates some of this logic.

**Recommendation:** Consolidate the discovery logic into `plugin_discovery.py` and keep `plugin_loader.py` focused on loading/instantiation only.

---

## 12. Split `litellm_service.py` — Monolithic LLM Class (MEDIUM IMPACT)

**Problem:** `infrastructure/llm/litellm_service.py` at **908 lines** is a single class handling 6 distinct jobs: config loading, model resolution, request preparation, completion with retry logic, response parsing, streaming, and tracing. Each concern is interleaved.

**Recommendation:** Extract into focused classes:
- `LiteLLMService` — completion + streaming only (~300 lines)
- `LLMConfigLoader` — config management (~100 lines)
- `ResponseParser` — response normalization (~100 lines)
- `RetryStrategy` — retry logic (~60 lines)

---

## 13. Tool Boilerplate Across 18 Native Tools (MEDIUM IMPACT)

**Problem:** All 18 native tools implement identical property stubs (`name`, `description`, `parameters_schema`, `requires_approval`, `approval_risk_level`, `supports_parallelism`, `get_approval_preview`, `validate_params`). Each tool has 30-50 lines of boilerplate before actual logic begins. Additionally, all tools share the same error-handling wrapper pattern:

```python
try:
    # tool logic
except Exception as e:
    tool_error = ToolError(f"{self.name} failed: {e}", ...)
    return tool_error_payload(tool_error)
```

**Recommendation:** Create a `BaseTool` dataclass or decorator that provides defaults for metadata properties and an error-handling wrapper. Each tool would only declare its unique metadata and implement `execute()`. Estimated reduction: ~15-20 lines per tool × 18 tools = ~300 lines total.

---

## 14. Delete Deprecated Infrastructure Files (LOW IMPACT, EASY WIN)

**Problem:** Two files are explicitly marked deprecated and confirmed unused via grep:
- `infrastructure/llm/parameter_mapper.py` (23 lines) — "Deprecated: Parameter mapping is no longer needed"
- `infrastructure/llm/error_handler.py` (42 lines) — "Deprecated: Error handling is now simplified"

**Recommendation:** Delete both. Zero callers.

---

## 15. Fix `file_state_manager._get_lock()` Race Condition (LOW IMPACT)

**Problem:** `infrastructure/persistence/file_state_manager.py` line 147 has a non-async `_get_lock()` method that modifies a shared dict without thread safety:

```python
def _get_lock(self, session_id: str) -> asyncio.Lock:  # NOT async
    if session_id not in self.locks:
        self.locks[session_id] = asyncio.Lock()
    return self.locks[session_id]
```

The `tool_result_store.py` version correctly uses a master lock for protection. The inconsistency is a latent race condition.

**Recommendation:** Align `file_state_manager` with the `tool_result_store` pattern using `async with self._locks_lock`.

---

## Summary Table

| # | Area | Impact | Effort | Key Metric |
|---|------|--------|--------|------------|
| 1 | Consolidate agent definition models | High | Medium | 3 overlapping files → 1 |
| 2 | Shrink `factory.py` | High | Medium | 1,644 → ~800 lines, 75 → ~35 methods |
| 3 | Replace `dict[str, Any]` internally | Medium | Low | Type safety for ~104 usages |
| 4 | Move concrete types out of interface file | Medium | Low | 409 → ~100 lines in protocol file |
| 5 | Reduce planning strategy duplication | Medium | Medium | ~200-300 lines eliminated |
| 6 | Unify executor entry points | Medium | Medium | 6 methods → 1, eliminate `ProgressUpdate` |
| 7 | Clean up agent.py / lean_agent.py | Low | Low | Remove dead shim |
| 8 | Consolidate thin interfaces | Low | Low | Fewer files to navigate |
| 9 | Simplify Butler abstractions | Low | Medium | Less premature abstraction |
| 10 | Remove compat aliases | Low | Low | Cleaner import graph |
| 11 | Consolidate plugin loader | Low | Low | Better separation of concerns |
| 12 | Split `litellm_service.py` | Medium | Medium | 908 → ~300 lines main class |
| 13 | Reduce tool boilerplate | Medium | Medium | ~300 lines eliminated across 18 tools |
| 14 | Delete deprecated LLM files | Low | Low | 2 dead files removed |
| 15 | Fix state manager race condition | Low | Low | Thread-safety bug fix |
