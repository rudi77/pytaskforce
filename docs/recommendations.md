# Codebase Improvement Recommendations

**Date:** 2026-02-22
**Scope:** Full codebase audit of architecture, code quality, testing, and type safety

---

## Executive Summary

The pytaskforce codebase has **strong architectural foundations** — clean four-layer separation with no import violations, excellent protocol-based design, and proper async patterns throughout. However, the audit identified **167 mypy type errors**, **significant function-length violations**, **test coverage gaps in critical modules**, and **two God-object files** that should be refactored. This document organizes findings into actionable priorities.

---

## 1. Critical: Type Safety (167 mypy errors)

### 1.1 Protocol Implementation Mismatches (`factory.py`)

Several tool instantiations in `factory.py` have signature mismatches against `ToolProtocol`:

- `SemanticSearchTool.execute(query, top_k, filters)` doesn't match `ToolProtocol.execute(**kwargs)`
- `GetDocumentTool.execute(...)` — same issue with specific parameters vs generic `**kwargs`
- `AskUserTool` missing `supports_parallelism` abstract attribute

**Fix:** Align tool `execute` signatures to accept `**kwargs` and unpack internally, or update the protocol to accommodate named parameters.

### 1.2 Optional/None Handling (`butler_daemon.py`)

Five locations access `self._butler` (type `ButlerService | None`) without None-checks:

```python
# Lines 147, 161, 185, 197, 210
self._butler.set_gateway(gateway)      # Could be None
self._butler.set_executor(executor)    # Could be None
self._butler.add_event_source(source)  # Could be None
```

**Fix:** Add `if self._butler is not None:` guards or assert non-None at initialization.

### 1.3 Gateway Constructor Bug (`butler_daemon.py:140`)

```python
gateway = CommunicationGateway(
    inbound_adapters=components.inbound_adapters,  # Parameter doesn't exist
)
```

**Fix:** Remove the `inbound_adapters` keyword or update `CommunicationGateway.__init__` to accept it.

### 1.4 StreamEvent Type Confusion (`executor.py:601-616`)

`StreamEvent` is a dataclass but is accessed as a dict:

```python
event_type_str = event.get("type", "unknown")  # StreamEvent has no .get()
step = event.get("step", "?")
```

**Fix:** Use attribute access (`event.event_type`, `event.step`) or check type with `isinstance`.

### 1.5 Missing Await (`epic_orchestrator.py:443`)

```python
async for event in executor.execute_mission_streaming(...):  # Not awaited
```

**Fix:** `async for event in await executor.execute_mission_streaming(...):`

### 1.6 Session ID None Type (`run.py:619`)

`Agent.execute` expects `session_id: str` but receives `None`.

**Fix:** Generate a session ID before passing, or make the parameter `Optional[str]`.

### 1.7 Stricter mypy Configuration

Current config allows untyped defs. Consider gradually tightening:

```toml
# pyproject.toml - future targets
disallow_untyped_defs = true        # Currently false
disallow_incomplete_defs = true     # Currently false
disallow_any_generics = true        # Not set
```

Prioritize enforcing on `core/` first, then `application/`, then outward layers.

---

## 2. Critical: God Objects Need Decomposition

### 2.1 `factory.py` — 1,872 lines, 26+ methods

`AgentFactory` handles profile loading, LLM creation, tool instantiation, context policy, skill management, plugin integration, and sub-agent configuration all in one class.

**Recommended extractions:**

| New Class | Responsibility | Est. Lines |
|-----------|---------------|------------|
| `ToolInstantiator` | Tool instantiation and wiring | ~200 |
| `ContextPolicyBuilder` | Context policy creation from config | ~80 |
| `SkillManagerBuilder` | Skill manager setup and loading | ~100 |
| `ExtensionApplicator` | Plugin/extension integration | ~150 |

**Target:** Reduce `AgentFactory` to ~1,000 lines with clear single responsibility.

### 2.2 `planning_strategy.py` — 1,010 lines

Contains 4 strategy classes + 40+ shared helper functions in one file.

**Recommended split:**

| New Module | Contents |
|-----------|----------|
| `planning_helpers.py` | `_execute_tool_calls()`, `_collect_result()`, `_extract_tool_output()`, `_parse_tool_args()` |
| `plan_parser.py` | `_parse_plan_steps()`, `_generate_plan()`, JSON parsing utilities |
| `planning_output.py` | `_stream_final_response()`, streaming and output formatting |
| `planning_strategy.py` | Strategy classes only (protocol + 4 implementations) |

---

## 3. High: Function Length Violations

The project standard is **max 30 lines per function**. The following exceed it by 5x or more:

| File | Function | Lines | Standard |
|------|----------|-------|----------|
| `api/routes/execution.py` | `execute_mission_stream` | 399 | 30 |
| `infrastructure/tools/native/python_tool.py` | `execute` | 310 | 30 |
| `application/factory.py` | `create_agent_with_plugin` | 239 | 30 |
| `api/cli/commands/run.py` | `_execute_streaming_mission` | 234 | 30 |
| `infrastructure/tools/rag/list_documents_tool.py` | `execute` | 214 | 30 |
| `infrastructure/tools/rag/get_document_tool.py` | `execute` | 197 | 30 |
| `infrastructure/tools/native/git_tools.py` | `execute` | 186 | 30 |
| `infrastructure/tools/native/search_tools.py` | `execute` | 178 | 30 |
| `application/executor.py` | `execute_mission_streaming` | 169 | 30 |
| `infrastructure/llm/litellm_service.py` | `complete_stream` | 167 | 30 |

**Root causes:**
- Streaming functions combine state management + event handling + UI updates
- Tool `execute` methods mix validation + execution + result formatting
- Factory methods handle multiple initialization paths

**Recommended patterns:**
- Split tool `execute` into `_validate()`, `_execute_impl()`, `_format_result()`
- Extract nested helpers to module-level functions
- Create builder/helper classes for streaming orchestration (e.g., `StreamingDisplay`)

---

## 4. High: Test Coverage Gaps

### 4.1 Untested Critical Modules

These core modules have **zero dedicated unit tests**:

| Module | Layer | Risk |
|--------|-------|------|
| `factory.py` | Application | **Critical** — central wiring for entire framework |
| `profile_loader.py` | Application | High — config resolution affects all agents |
| `system_prompt_assembler.py` | Application | High — prompt construction is core behavior |
| `lean_agent.py` | Core/Domain | **Critical** — main agent implementation |
| `agent.py` | Core/Domain | Medium — may be legacy |
| `litellm_service.py` | Infrastructure | **Critical** — all LLM calls flow through this |
| `error_handler.py` | Infrastructure | High — retry/error classification logic |
| `butler_daemon.py` | API | Medium — daemon lifecycle |
| CLI commands (`run.py`, `chat.py`, etc.) | API | Medium — user-facing entry points |

### 4.2 Thin/Stub Tests

These test files exist but provide minimal value:

| File | Tests | Issue |
|------|-------|-------|
| `test_sub_agents.py` | 1 | Tests only a utility function, no spawning logic |
| `test_package_structure.py` | 5 | Import-only checks, 1 real assertion |
| `test_protocols.py` | — | Only verifies protocol imports, never validates contracts |
| `test_message_bus.py` | 2 | In-memory bus barely tested |

### 4.3 Missing Centralized Test Fixtures

`tests/conftest.py` (178 lines) contains only import stubs for optional dependencies. It lacks shared fixtures for:

- Mock LLM providers
- Mock state managers
- Mock agents and executors
- Test configuration objects
- Temporary directory factories

**Result:** Each test file recreates its own mocks (e.g., `test_executor.py` has 47 inline mock creations). This leads to duplication and inconsistency.

**Recommendation:** Create a `tests/fixtures/` package with:
- `mock_llm.py` — Reusable mock LLM provider
- `mock_state.py` — Reusable mock state manager
- `mock_tools.py` — Reusable mock tool implementations
- `factories.py` — Test factory functions for domain objects

### 4.4 Missing Error Path Tests

- No tests for timeout scenarios or retry logic
- No tests for partial failures in multi-tool execution
- No tests for `asyncio.CancelledError` or task cancellation
- Butler service tests (6 tests) don't cover event routing failures

---

## 5. Medium: Type Annotation Gaps

### 5.1 Files with Poor Annotation Coverage

| File | Annotated | Total | % |
|------|-----------|-------|---|
| `infrastructure/llm/error_handler.py` | 0 | 9 | **0%** |
| `api/cli/commands/missions.py` | 1 | 3 | 33% |
| `api/cli/output_formatter.py` | 21 | 50 | 42% |
| `infrastructure/tools/mcp/client.py` | 11 | 26 | 42% |
| `api/routes/execution.py` | 4 | 9 | 44% |

`error_handler.py` at 0% is the most critical — it handles retry/error classification for all LLM calls.

### 5.2 `Dict[str, Any]` Usage

73 instances of `Dict[str, Any]` across the codebase. While many are justified (external API payloads, logging contexts), some internal interfaces could use typed alternatives:

```python
# Current
result: dict[str, Any] = {...}

# Better
@dataclass
class LLMResult:
    success: bool
    content: str
    usage: TokenUsage
```

---

## 6. Medium: Linting Issues (11 total)

| Category | Count | Files |
|----------|-------|-------|
| Import organization (I001) | 2 | `chat.py`, `run.py` |
| Unused imports (F401) | 1 | `config.py` (`sys`) |
| Whitespace in blank lines (W293) | 3 | `config.py` |
| Missing `from` clause (B904) | 1 | `run.py:633` |
| Deprecated `timezone.utc` (UP017) | 1 | `chat.py` |
| Late imports inside functions | 2 | `run.py` |

**Fix:** Run `uv run ruff check --fix src/taskforce` for auto-fixable issues.

---

## 7. Medium: Ruff Configuration Gaps

Current ruff config lacks some valuable checkers:

```toml
# Current
select = ["E", "W", "F", "I", "B", "C4", "UP"]

# Recommended additions
select = [
    "E", "W", "F", "I", "B", "C4", "UP",
    "S",      # flake8-bandit — security checks
    "C901",   # McCabe complexity — flag functions > threshold
    "ASYNC",  # async/await correctness checks
]
```

Adding `C901` with a threshold of 15 would automatically flag the most complex functions.

---

## 8. Low: Miscellaneous Issues

### 8.1 Agent vs LeanAgent Clarification

`agent.py` is now only 5 lines — effectively a stub. `lean_agent.py` (550 lines) is the actual implementation. The relationship should be documented or `agent.py` should be consolidated.

### 8.2 Global/Module-Level State

Three module-level registries exist for plugin extensibility:
- `factory.py`: `_factory_extensions` list
- `plugin_discovery.py`: `_plugin_registry` singleton
- `skills.py`: `_cli_skill_service`

These are intentional extension points but are not thread-safe. Consider `contextvars` or explicit registry injection for production multi-tenant use.

### 8.3 Generic Exception Handling

30+ instances of `except Exception as e:` across the codebase. Most include structured logging (acceptable in orchestration layers), but a few use bare `pass`:

- `executor.py` lines 703, 713, 748 — silent `except Exception: pass`

These should at minimum log a warning.

### 8.4 Hardcoded Agent Limits

Constants in `lean_agent.py` could be profile-configurable:

```python
TOOL_RESULT_STORE_THRESHOLD = 5000
DEFAULT_MAX_INPUT_TOKENS = 100000
DEFAULT_COMPRESSION_TRIGGER = 80000
```

---

## Recommended Action Plan

### Phase 1: Critical Fixes (1-2 days)

1. Fix mypy errors in `factory.py`, `executor.py`, `butler_daemon.py`
2. Add missing `await` in `epic_orchestrator.py:443`
3. Fix `CommunicationGateway` constructor call in `butler_daemon.py`
4. Add `supports_parallelism` to `AskUserTool`
5. Fix `StreamEvent` dict-access pattern in `executor.py`

### Phase 2: High-Impact Refactoring (1-2 sprints)

6. Decompose `AgentFactory` into focused classes (~1,872 → ~1,000 lines)
7. Split `planning_strategy.py` into 4 modules (~1,010 → ~250 each)
8. Break down the 10 largest functions (399-line `execute_mission_stream`, etc.)
9. Add type annotations to `error_handler.py` (0% coverage)
10. Create centralized test fixtures in `tests/conftest.py`

### Phase 3: Coverage & Quality (ongoing)

11. Write unit tests for untested critical modules (`factory.py`, `lean_agent.py`, `litellm_service.py`)
12. Add error-path and cancellation tests
13. Strengthen protocol validation tests beyond import checks
14. Increase type annotation coverage to >80% in all layers
15. Enable stricter mypy settings incrementally (start with `core/`)

### Phase 4: Long-Term Hardening (next quarter)

16. Enable `C901` complexity checker in ruff
17. Enable `S` (bandit) security checker in ruff
18. Target `disallow_untyped_defs = true` in mypy
19. Make agent constants profile-configurable
20. Address thread-safety in module-level registries for multi-tenant deployment

---

## What's Working Well

These areas are strong and should be maintained:

- **Architecture:** Clean four-layer separation with zero import violations
- **Protocol design:** 18 interface files, ~30 protocols, proper duck typing
- **Async patterns:** 350+ async functions, proper semaphores, no blocking I/O
- **Domain modeling:** Comprehensive enums (no magic strings), typed domain models
- **Structured logging:** Consistent `structlog` usage with contextual data
- **Technical debt:** Only 2 TODO comments in entire codebase
- **Documentation:** Extensive CLAUDE.md, ADRs, feature docs, architecture docs
