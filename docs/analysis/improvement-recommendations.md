# Codebase Improvement Recommendations

**Date:** 2026-02-23
**Scope:** Full codebase analysis of pytaskforce

---

## Codebase Health Snapshot

| Metric | Value |
|--------|-------|
| Source files | 187 (.py), ~13,300 statements |
| Test files | 124, 1,491 test cases |
| Test pass rate | 1,478 passed, 1 failed, 13 skipped |
| Line coverage | 66% (target: 80%) |
| Mypy errors | 213 |
| Ruff lint errors | 8 (7 auto-fixable) |
| Architecture violations | 8 (concentrated in butler subsystem) |

---

## 1. Type Safety — 213 mypy errors

The project configures mypy with strict settings (`disallow_untyped_defs`, `disallow_incomplete_defs`), but 213 errors remain unaddressed.

### Worst offenders

| File | Errors | Primary Issues |
|------|--------|----------------|
| `api/cli/output_formatter.py` | 13 | Missing annotations |
| `infrastructure/tools/rag/azure_search_base.py` | 9 | Incompatible types, missing annotations |
| `infrastructure/tools/native/git_tools.py` | 9 | Missing annotations |
| `api/cli/commands/run.py` | 9 | Missing annotations |
| `application/tool_builder.py` | 8 | Missing annotations |
| `core/domain/skill_workflow.py` | 5 | Type coercion bugs |

### Notable bugs

- `skill_workflow.py:71` — calls `dict.get()` with a `bool` argument instead of a string key
- `ToolProtocol.execute` signature mismatch across `search_tools.py`, `python_tool.py`, and `multimedia_tool.py`

### Recommendation

Prioritize fixing core domain mypy errors first (strictest layer), then work outward. The `skill_workflow.py` bug should be fixed immediately.

---

## 2. Test Coverage Gaps

Overall 66% coverage is below the project's own 80% target.

### Core domain (target ≥90%)

- `lean_agent.py` — 543 lines, the primary agent implementation, zero tests
- `lean_agent_components/message_history_manager.py` — 39% coverage
- `lean_agent_components/message_sanitizer.py` — 41% coverage
- `skill_workflow.py`, `memory_service.py`, `messaging.py` — untested

### Infrastructure (target ≥80%)

- All 6 RAG tools — 0% coverage (~800 LOC)
- All 4 butler tools (calendar, schedule, reminder, rule_manager) — 0% coverage
- `multimedia_tool.py` — 21% coverage
- MCP client/wrapper — 35% coverage
- `event_sources/*` — 0% coverage

### API layer

- `butler_daemon.py` — 0% (132 statements)
- `cli/commands/skills.py` — 14%
- `cli/commands/butler.py` — 16%
- `cli/simple_chat.py` — 33%

### Failing test

`test_execute_with_agent_id_and_user_context` — asserts `UserContext` object equals a `dict`, indicating the test was not updated after a refactor from dict to dataclass.

### Recommendation

Start with `lean_agent.py` (foundational), then RAG tools and butler subsystem. Fix the failing test immediately.

---

## 3. Clean Architecture Violations

8 violations found, all in the butler/gateway subsystem.

### API → Infrastructure (4 violations)

- `api/butler_daemon.py:183-184` — imports `infrastructure.event_sources.calendar_source`
- `api/butler_daemon.py:200-201` — imports `infrastructure.event_sources.webhook_source`
- `api/butler_daemon.py:136-138` — imports `taskforce_extensions.infrastructure.communication`
- `api/cli/commands/butler.py:232` — imports `infrastructure.scheduler.job_store`

### Application → Extensions Infrastructure (3 violations)

- `application/factory.py:1066-1080` — imports `taskforce_extensions.infrastructure.runtime`
- `application/epic_orchestrator.py:21` — imports `taskforce_extensions.infrastructure.messaging`
- `application/infrastructure_builder.py:339-341` — imports extensions communication

### Root cause

Butler/event-driven subsystem was added without proper application-layer service abstractions. Infrastructure components are instantiated directly in API code instead of being injected through the application layer.

### Recommendation

Create a `ButlerComponentBuilder` in the application layer that encapsulates all infrastructure instantiation. API layer should only receive protocol-typed objects.

---

## 4. Module Size & Complexity

Several files significantly exceed maintainability thresholds:

| File | Lines | Issue |
|------|-------|-------|
| `application/executor.py` | 1,464 | Streaming + epic orchestration mixed |
| `application/factory.py` | 1,091 | ~215 lines of delegation stubs, 75 methods |
| `application/plugin_loader.py` | 1,007 | Plugin discovery overly complex |
| `core/domain/planning_helpers.py` | 911 | Same patterns repeated across 4 strategies |
| `infrastructure/llm/litellm_service.py` | 726 | LLM integration + routing combined |
| `core/domain/agent_definition.py` | 681 | Overlaps with `agent_models.py` (314 lines) |

`factory.py` has ~215 lines of stub methods that forward calls to `_tool_builder`. These should be removed with callers using `_tool_builder` directly.

### Recommendation

Extract common planning strategy patterns into shared helpers. Consolidate `agent_definition.py` + `agent_models.py` into a single model. Remove factory delegation stubs.

---

## 5. Duplicate Domain Models

Three overlapping model systems for agent definitions:

- `core/domain/agent_definition.py` (681 lines) — `AgentDefinition`, `AgentSource` enum
- `core/domain/agent_models.py` (314 lines) — `CustomAgentDefinition`, `AgentSourceType` enum
- `core/domain/config_schema.py` (445 lines) — `MCPServerConfigSchema` (duplicate of `MCPServerConfig`)

6 files still import the deprecated `CustomAgentDefinition`.

### Recommendation

Complete migration to `AgentDefinition`, retire `agent_models.py`, remove duplicate enums.

---

## 6. Logging Pattern Inconsistency

~50+ instances of f-string formatting in logger calls instead of structlog structured keyword arguments:

```python
# Current (scattered throughout skill_registry.py, skill_loader.py, etc.)
logger.debug(f"Loading skill: {skill_name}")

# Project standard
logger.debug("skill.loading", skill_name=skill_name)
```

### Recommendation

Batch-fix with a focused pass through infrastructure and application layers.

---

## 7. Broad Exception Handling

17 instances of `except Exception:` without specific exception types. Most follow acceptable patterns, but some are too broad:

- `plugin_loader.py:393-395` — catches all exceptions during plugin loading
- `tool_result_store.py:378-379` — silently handles serialization failures

### Recommendation

Narrow to specific exception types where possible. Ensure all broad catches log the exception.

---

## 8. Lint Errors

8 ruff errors (7 auto-fixable): primarily import sorting in `url_validator.py` and an unused loop variable.

Fix with: `uv run ruff check --fix src/taskforce`

---

## Priority Action Plan

| # | Action | Impact | Effort |
|---|--------|--------|--------|
| 1 | Fix the 1 failing test + `skill_workflow.py` bug | Correctness | Low |
| 2 | Fix 8 ruff lint errors | CI hygiene | Trivial |
| 3 | Add tests for `lean_agent.py` and core components | Coverage of foundational code | Medium |
| 4 | Fix butler architecture violations (4 API→Infra imports) | Architecture integrity | Medium |
| 5 | Reduce mypy errors (start with core domain) | Type safety | Medium |
| 6 | Add tests for RAG tools and butler subsystem | Coverage of untested subsystems | Medium |
| 7 | Consolidate agent definition models | Eliminate duplication | Medium |
| 8 | Refactor `factory.py` (remove stubs) | Maintainability | Medium |
| 9 | Standardize structlog usage (~50 f-string fixes) | Production observability | Low |
| 10 | Extract common planning strategy patterns | Reduce duplication | Medium |
