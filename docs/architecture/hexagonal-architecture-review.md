# Hexagonal Architecture Review

**Date:** 2026-02-23
**Scope:** Full codebase analysis of `src/taskforce/` against Clean/Hexagonal Architecture principles

---

## Executive Summary

The Taskforce codebase demonstrates **strong architectural discipline** overall. The four-layer separation (Core, Infrastructure, Application, API) is well-enforced, protocol-based design is consistently applied, and the dependency direction is almost universally correct. However, the analysis uncovered several concrete improvement areas across six dimensions:

| Dimension | Score | Key Issue |
|-----------|-------|-----------|
| Layer Boundary Compliance | 9/10 | 1 import violation; some DI bypasses |
| Protocol Design | 8/10 | `dict[str, Any]` overuse; naming inconsistency |
| Dependency Injection | 7/10 | Factory inefficiencies; global singletons |
| Domain Purity | 8/10 | Pydantic in domain; anemic models |
| Application Layer Design | 8/10 | SkillManager/ToolBuilder boundary blur |
| Test Architecture | 8/10 | Good alignment; some coverage gaps |

**Overall: 8/10** - Solid hexagonal architecture with targeted improvements needed.

---

## 1. Layer Boundary Compliance

### 1.1 Import Rule Violations

Only **one direct violation** was found across the entire codebase:

| Severity | File | Line | Violation |
|----------|------|------|-----------|
| **HIGH** | `infrastructure/persistence/plugin_scanner.py` | 98 | Imports from `taskforce.application.plugin_loader` |

**Why it matters:** Infrastructure must never depend on Application. This creates an upward dependency that breaks the hexagonal model.

**Recommendation:** Move plugin scanning logic into the Application layer (where `plugin_loader.py` already lives), or extract a `PluginScannerProtocol` in `core/interfaces/` that Infrastructure implements and Application consumes.

### 1.2 Indirect Boundary Bypasses

While not import violations per se, several places bypass the DI/factory abstraction by directly instantiating infrastructure:

| File | Line | Issue |
|------|------|-------|
| `application/executor.py` | ~633 | Directly instantiates `FileAgentRegistry` instead of using injected dependency |
| `application/tool_builder.py` | 203-234, 248-280 | Hard-codes direct imports of 9+ native tool classes instead of using `ToolRegistry` |
| `application/skill_manager.py` | 122-139 | Directly instantiates `FileSkillRegistry` instead of injecting via protocol |

**Recommendation:** All infrastructure instantiation should flow through `InfrastructureBuilder` or constructor injection. Replace direct `FileAgentRegistry` creation in `executor.py` with a constructor parameter. Have `ToolBuilder` delegate to `ToolRegistry.resolve()` instead of reimplementing tool instantiation.

---

## 2. Protocol Design Quality

### 2.1 Type Safety: `dict[str, Any]` Overuse

The most pervasive issue across the codebase. ~30 occurrences in protocol signatures where concrete types should be used:

| Protocol | Method | Current Type | Suggested Type |
|----------|--------|-------------|----------------|
| `LLMProviderProtocol` | `complete()` params/return | `dict[str, Any]` | `LLMRequest` / `LLMResponse` dataclass |
| `StateManagerProtocol` | `save_state()` / `load_state()` | `dict[str, Any]` | `StateData` dataclass or `TypedDict` |
| `ToolResultStoreProtocol` | `put()` / `fetch()` | `dict[str, Any]` | Concrete `ToolResult` (already exists in `core/domain/tool_result.py`) |
| Gateway protocols | Message payloads | `dict[str, Any]` | Structured message types |

**Impact:** Weakened contracts, reduced IDE support, runtime errors that types would catch at dev time.

**Positive counter-examples:** `MemoryStoreProtocol` uses concrete `MemoryRecord` - this is the pattern to follow.

### 2.2 Naming Inconsistency Across Protocols

CRUD operations use different verbs across similar protocols:

```
StateManager:     save_state()    / load_state()    / delete_state()
ToolResultStore:  put()           / fetch()          / delete()
MemoryStore:      add()           / get()            / update()       / delete()
CheckpointStore:  save()          / latest()         / list()
RuntimeProtocols: record()        / load()           / save()
```

**Recommendation:** Standardize on a single verb set (e.g., `save`/`load`/`delete`/`list`) and document it in a Protocol Style Guide.

### 2.3 Inconsistent Error Handling in Protocols

- `OutboundSenderProtocol.send()` **raises** `ConnectionError`
- `ToolProtocol.execute()` **returns** error dict
- `LLMProviderProtocol.complete()` **returns** error dict

**Recommendation:** Adopt a consistent strategy. For protocols with fallible operations, prefer returning `Result`-style types or documenting exception contracts explicitly.

### 2.4 Incomplete Tool Implementations

Three tools are missing methods defined by `ToolProtocol`:

| Tool | Missing Methods |
|------|----------------|
| `ActivateSkillTool` | `requires_approval`, `approval_risk_level`, `supports_parallelism`, `get_approval_preview`, `validate_params` |
| `ReminderTool` | `supports_parallelism`, `get_approval_preview`, `validate_params` |
| `RuleManagerTool` | Similar gaps |

**Recommendation:** Ensure these tools inherit from `BaseTool` (which provides sensible defaults), or explicitly implement all protocol methods.

### 2.5 Async Gaps in Skills Protocol

`SkillRegistryProtocol.get_skill()` and `discover_skills()` are synchronous despite performing filesystem I/O. This can block the event loop.

**Recommendation:** Make these methods `async` to maintain consistent async I/O across all protocols.

---

## 3. Dependency Injection & Factory Patterns

### 3.1 AgentFactory: Multiple InfrastructureBuilder Instantiations

`AgentFactory` creates new `InfrastructureBuilder` instances in at least 5 different methods (lines ~213, 229, 255, 750, 1046). Each builder is lightweight, but the pattern indicates missing centralization.

**Recommendation:** Store a single `InfrastructureBuilder` instance as an `AgentFactory` attribute, initialized once during construction. All methods reference `self._infra_builder`.

### 3.2 Global Singleton ToolRegistry

`tool_registry.py` (lines ~372-405) uses module-level mutable global state:

```python
_registry: ToolRegistry | None = None

def get_tool_registry(llm_provider=None, ...):
    global _registry
    if _registry is None or llm_provider is not None:
        _registry = ToolRegistry(...)
    return _registry
```

**Problems:**
- Stateful across requests in API context
- Fragile re-creation logic when parameters change
- Difficult to test without manual cache clearing

**Recommendation:** Replace with request-scoped dependency injection (FastAPI's `Depends()`) or explicit factory method. The API layer's `dependencies.py` already does this correctly with `@lru_cache` - apply the same pattern here.

### 3.3 Positive Patterns (Worth Preserving)

- **API layer DI** (`api/dependencies.py`): Uses FastAPI `Depends()` with lazy initialization and `@lru_cache`. No direct infrastructure imports in routes.
- **InfrastructureBuilder**: Returns protocol types, not implementations. Uses lazy imports to avoid circular dependencies.
- **Factory abstraction**: Dependencies are properly injected into Agent instances via constructor.

---

## 4. Domain Model Purity

### 4.1 Pydantic in Domain Layer

`core/domain/config_schema.py` imports Pydantic `BaseModel` and defines 10+ schema classes with validators:

```python
# core/domain/config_schema.py line 17
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
```

**Why this is a violation:** Pydantic is a validation/serialization **framework**. Domain models should be framework-agnostic (plain dataclasses). Configuration validation is an Application/Infrastructure concern.

**Recommendation:** Move `config_schema.py` to `application/` layer. Keep domain configuration as plain dataclasses. Validation logic belongs at the boundary where external configuration enters the system.

### 4.2 Remaining `dict[str, Any]` in Domain Models

Beyond protocols, the domain layer itself uses untyped dictionaries:

| File | Location | Type Used |
|------|----------|-----------|
| `lean_agent.py` | Line ~221 | `state: dict[str, Any]` |
| `models.py` | Line ~174 | `execution_history: list[dict[str, Any]]` |
| `models.py` | Line ~176 | `pending_question: PendingQuestion \| dict[str, Any]` |
| `planning_helpers.py` | Lines 98-115 | Tool call representations as raw dicts |

**Recommendation:** Create typed alternatives:
- `StateData` TypedDict for agent state
- `ExecutionHistoryEntry` dataclass for history items
- `ToolCallRequest` (already exists at line 47) - use it consistently

### 4.3 Anemic Domain Models

Several models are pure data holders without domain behavior:

| Model | File | Issue |
|-------|------|-------|
| `TokenUsage` | `models.py` | Only serialization, no budget comparison methods |
| `UserContext` | `models.py` | Minimal behavior, mostly data + converters |
| `GatewayResponse` | `gateway.py` | Purely a data holder |

**Recommendation:** Enrich with domain behavior where appropriate. For example, `TokenUsage` should have methods like `exceeds_budget(limit)` or `remaining(budget)`.

### 4.4 Domain Strengths (Worth Preserving)

- **Event modeling** is excellent: `EventType` enum, `StreamEvent` dataclass, `AgentEvent` model
- **Enum usage** eliminates magic strings throughout (`ExecutionStatus`, `TaskStatus`, `MessageRole`)
- **LeanAgent components** (`lean_agent_components/`) demonstrate proper single-responsibility decomposition
- **Error hierarchy** (`errors.py`) is clean and domain-specific
- **No I/O in domain**: All filesystem/network operations properly delegated through protocols

---

## 5. Application Layer Design

### 5.1 SkillManager: Blurred Layer Boundaries

`application/skill_manager.py` contains domain logic that should live in `core/domain/`:

| Lines | Issue |
|-------|-------|
| 150-166 | `_build_skill_directories()` directly manipulates `Path` objects with filesystem assumptions (`cwd()`, `home()`) |
| 113-116 | Maintains execution state (`_active_skill_name`, `_previous_skill_name`) that belongs in domain |
| 335-353 | `_transfer_context()` implements domain business logic for skill transitions |
| 122-139 | Directly instantiates `FileSkillRegistry` (should be injected) |

**Recommendation:**
- Extract skill transition logic into a `SkillTransition` class in `core/domain/`
- Inject `SkillRegistry` via protocol rather than instantiating `FileSkillRegistry`
- Move filesystem path construction to Infrastructure

### 5.2 ToolBuilder: Hardcoded Infrastructure Imports

`application/tool_builder.py` directly imports and instantiates tool classes instead of using the existing `ToolRegistry`:

```python
# Lines 203-234: Hardcoded tool list
return [
    WebSearchTool(),
    WebFetchTool(),
    PythonTool(),
    # ... 6 more hardcoded instantiations
]
```

This duplicates resolution logic already in `ToolRegistry.resolve()`.

**Recommendation:** Replace all direct tool instantiation in `ToolBuilder` with calls to `ToolRegistry.resolve(tool_names)`. Remove the duplicate import lists.

### 5.3 Application Layer Strengths

Several files are exemplary:

| File | Quality | Why |
|------|---------|-----|
| `tool_registry.py` | Excellent | Proper port between application and infrastructure |
| `profile_loader.py` | Excellent | No infrastructure concerns, clean config loading |
| `system_prompt_assembler.py` | Excellent | Thin orchestrator, delegates to core domain |
| `epic_orchestrator.py` | Excellent | Clean planner/worker/judge composition via protocols |
| `infrastructure_builder.py` | Excellent | Returns protocols, lazy imports, perfect ports-and-adapters |

---

## 6. Test Architecture Alignment

### 6.1 Structure

Test structure properly mirrors the four-layer source structure:

```
tests/
├── unit/core/          # Pure domain tests
├── unit/infrastructure/ # Adapter tests
├── unit/application/   # Service tests with mocked ports
├── unit/api/           # Endpoint tests
├── integration/        # Cross-layer tests
└── conftest.py         # Protocol-based shared fixtures
```

### 6.2 Protocol-Based Mocking

`conftest.py` properly uses protocol-compatible mocks (e.g., `Mock(spec=StateManagerProtocol)`), maintaining the hexagonal boundary in tests.

### 6.3 Improvement Opportunities

- **Port/adapter boundary tests**: Consider adding dedicated tests that verify each infrastructure adapter satisfies its protocol (structural subtyping compliance tests)
- **Coverage gaps**: Butler-related components (scheduler, event sources, rule engine) may have lower test coverage given their newer addition
- **Integration test scope**: Verify that integration tests exercise the full port-adapter-port chain rather than just testing adapters in isolation

---

## Prioritized Recommendations

### High Priority

| # | Issue | Location | Impact |
|---|-------|----------|--------|
| 1 | Fix import violation: Infrastructure importing Application | `infrastructure/persistence/plugin_scanner.py:98` | Breaks layer boundary |
| 2 | Replace `dict[str, Any]` with concrete types in protocols | `core/interfaces/llm.py`, `state.py`, `tool_result_store.py` | Weakened contracts across entire system |
| 3 | Move `config_schema.py` out of domain layer | `core/domain/config_schema.py` | Pydantic framework dependency in domain |
| 4 | Inject `FileAgentRegistry` instead of direct instantiation | `application/executor.py:~633` | Bypasses DI |

### Medium Priority

| # | Issue | Location | Impact |
|---|-------|----------|--------|
| 5 | Consolidate `ToolBuilder` to use `ToolRegistry` | `application/tool_builder.py` | Duplicated tool resolution logic |
| 6 | Extract skill transition logic to domain | `application/skill_manager.py` | Domain logic in wrong layer |
| 7 | Cache `InfrastructureBuilder` in factory | `application/factory.py` | Redundant object creation |
| 8 | Standardize CRUD naming across protocols | All `core/interfaces/` files | Inconsistent API surface |
| 9 | Replace global `_registry` singleton | `application/tool_registry.py:372-405` | Mutable global state |

### Low Priority

| # | Issue | Location | Impact |
|---|-------|----------|--------|
| 10 | Make Skills protocol methods async | `core/interfaces/skills.py` | Potential event loop blocking |
| 11 | Enrich anemic domain models | `core/domain/models.py` | Missing domain behavior |
| 12 | Ensure all tools inherit from BaseTool | `activate_skill_tool.py`, `reminder_tool.py`, `rule_manager_tool.py` | Incomplete protocol compliance |
| 13 | Standardize error handling pattern across protocols | `core/interfaces/gateway.py` | Inconsistent error contracts |
| 14 | Add protocol compliance tests | `tests/` | Verify adapters satisfy ports |

---

## Conclusion

The Taskforce codebase is a **well-architected system** that takes hexagonal/clean architecture seriously. The four-layer separation is consistently enforced, protocol-based design is the norm rather than the exception, and the dependency direction is correct in 99%+ of the code.

The issues identified are refinement opportunities rather than fundamental architectural problems:

- The single import violation is straightforward to fix
- Type safety improvements (`dict[str, Any]` to concrete types) are incremental and can be done protocol-by-protocol
- The DI bypasses are localized and don't compromise the overall architecture
- Moving Pydantic out of domain is a clean refactor with clear boundaries

Addressing the high-priority items would elevate the architecture from "good" to "exemplary."
