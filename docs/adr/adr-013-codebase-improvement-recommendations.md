# ADR-013: Codebase Improvement Recommendations

**Status:** Proposed
**Date:** 2026-02-24
**Author:** Automated audit

---

## Context

A comprehensive audit of the pytaskforce codebase was performed covering all four architectural layers (Core, Infrastructure, Application, API), the test suite, and cross-cutting concerns. This ADR documents the findings and prioritized recommendations.

### Current Health Snapshot

| Metric | Value | Target | Status |
|--------|-------|--------|--------|
| Tests | 1,751 passed / 13 skipped / 0 failed | All pass | OK |
| Ruff linting | 0 issues | 0 | OK |
| Mypy type errors | 196 errors in 53 files | 0 | Needs work |
| Test coverage | 68% | 80% | Below target |
| Source files | 188 | — | — |
| Test files | 107 (57% ratio) | — | — |

---

## Findings

### 1. Type Safety (196 mypy errors)

**Severity: HIGH** — The 196 mypy errors are concentrated in three layers:

| Layer | Errors | Share | Dominant Error Type |
|-------|--------|-------|---------------------|
| Infrastructure | 90 | 46% | `no-untyped-def` |
| API | 74 | 38% | `no-untyped-def` |
| Application | 31 | 16% | `no-any-return`, `arg-type` |
| Core | 1 | <1% | — |

The majority (90 occurrences) are `no-untyped-def` — missing type annotations on function signatures. Other categories include `no-any-return` (22), `arg-type` (20), and `override` (15).

**Recommendation:** Fix in batches by layer, starting with Infrastructure (highest count, most mechanical fixes). Most `no-untyped-def` errors are straightforward annotation additions.

---

### 2. Test Coverage Gaps (68% vs 80% target)

**Severity: HIGH** — Coverage is 12 percentage points below the 80% project target.

#### Untested modules (0% coverage)

| Module | Layer |
|--------|-------|
| `infrastructure/tools/native/llm_tool.py` | Infrastructure |
| `infrastructure/tools/native/memory_tool.py` | Infrastructure |
| `infrastructure/tools/native/multimedia_tool.py` | Infrastructure |
| `api/dependencies.py` | API |
| `api/errors.py` | API |
| `api/butler_daemon.py` | API |
| `core/prompts/` (entire directory) | Core |

#### Weakly-covered areas

| Area | Coverage | Notes |
|------|----------|-------|
| CLI commands | 14–58% | Only integration tests, no unit tests |
| LiteLLM service | ~52% | Complex streaming paths untested |
| RAG tools | 0–3% | Only partial integration stubs |
| Butler daemon | 0% | No tests at all |
| Multimedia tool | 21% | Minimal coverage |

**Recommendation:** Prioritize tests for the three zero-coverage native tools, the Butler daemon, and CLI commands. These are the largest coverage gaps per effort.

---

### 3. Function Length Violations

**Severity: MEDIUM** — The CLAUDE.md coding standard requires functions ≤30 lines. Several functions significantly exceed this.

#### Core layer (`planning_helpers.py`)

| Function | Lines | Exceeds by |
|----------|-------|------------|
| `_react_loop()` | 193 | +163 |
| `_llm_call_and_process()` | 76 | +46 |
| `_process_tool_calls()` | 69 | +39 |
| `_resume_from_pause()` | 66 | +36 |
| `_stream_final_response()` | 63 | +33 |

#### Infrastructure layer

| Function | File | Lines |
|----------|------|-------|
| `PowerShellTool.execute()` | `shell_tool.py` | ~155 |
| `PythonTool.execute()` | `python_tool.py` | ~200 |
| Multiple methods | `browser_tool.py` | 50–80 each |

#### Application layer

| Function | File | Lines |
|----------|------|-------|
| `_create_agent_from_inline_params()` | `factory.py` | 103 |
| `create_agent_with_plugin()` | `factory.py` | 123 |

**Recommendation:** Decompose `_react_loop()` first (it is the most critical path). Extract streaming, tool processing, and state management into separate focused functions. For tool `execute()` methods, extract validation, execution, and result formatting phases.

---

### 4. Blocking I/O in Async Code

**Severity: HIGH** — Several async methods perform synchronous file I/O, blocking the event loop.

| File | Issue |
|------|-------|
| `infrastructure/memory/file_memory_store.py` | **All methods** marked `async` but use `path.write_text()` / `path.read_text()` |
| `infrastructure/event_sources/calendar_source.py` | `with open(creds_path) as f:` in async context |
| `infrastructure/llm/llm_config_loader.py` | `with open(config_file) as f:` in `_load_config_sync()` |
| `infrastructure/persistence/agent_serializer.py` | Synchronous YAML loading |
| `infrastructure/tools/native/calendar_tool.py` | Synchronous credential file reads |

**Recommendation:** Convert `file_memory_store.py` to use `aiofiles` as the highest priority — every method is affected. The config/credential loaders can be addressed next.

---

### 5. Security Concerns

**Severity: HIGH**

#### 5a. Missing API security headers (`api/server.py`)

The FastAPI server lacks standard security headers:
- No `X-Content-Type-Options: nosniff`
- No `X-Frame-Options: DENY`
- No `Strict-Transport-Security`
- CORS defaults to `*` (wildcard), allowing any origin

#### 5b. Path traversal risk in file tools (`infrastructure/tools/native/file_tools.py`)

`FileReadTool` and `FileWriteTool` do not validate paths against symlink traversal or directory escape. `Path(path)` follows symlinks without restriction.

#### 5c. Shell tool uses blocklist instead of allowlist (`infrastructure/tools/native/shell_tool.py`)

Command filtering uses a blocklist of dangerous patterns (lines 98–110), which is inherently incomplete. Uses `asyncio.create_subprocess_shell()` (shell=True equivalent).

#### 5d. Missing request size/rate limits on gateway routes (`api/routes/gateway.py`)

No rate limiting on webhook endpoints. `conversation_id` has no format validation (potential path traversal in file-based conversation store).

**Recommendation:** Add security headers middleware, restrict CORS defaults, add `Path.resolve()` validation in file tools, and add rate limiting on gateway webhooks.

---

### 6. Architectural Violations

**Severity: MEDIUM**

| Location | Violation |
|----------|-----------|
| `core/domain/config_schema.py` (line 11) | Core layer imports from Application layer via re-export shim. Documented as deprecated but still present. |
| `application/butler_service.py` (line 23) | Direct import of `SchedulerService` from Infrastructure. Should use `SchedulerProtocol`. |
| `infrastructure/persistence/plugin_scanner.py` (line 41) | Lazy import of `PluginLoader` from Application layer. Mitigated by dependency injection but still technically violates layer direction. |

**Recommendation:** Remove the `config_schema.py` re-export shim entirely. Replace direct `SchedulerService` import with protocol-based injection.

---

### 7. Error Handling Patterns

**Severity: MEDIUM**

Broad `except Exception` without type discrimination appears in multiple locations:

| File | Lines | Impact |
|------|-------|--------|
| `application/executor.py` | 315–320, 1072, 1102, 1179, 1304 | Masks programming errors in streaming path |
| `application/task_complexity_classifier.py` | 104 | Silently falls back on any error type |
| `application/tool_registry.py` | 360 | Returns `None` silently on tool instantiation failure |
| `api/server.py` | 192–197, 216–221 | Silently skips failed plugin middleware |
| `infrastructure/memory/file_memory_store.py` | All methods | No error handling at all — exceptions propagate raw |

**Recommendation:** Replace `except Exception` with specific exception types (`TaskforceError`, `LLMError`, `ToolError`, `FileNotFoundError`, etc.). Log at appropriate levels and re-raise programming errors.

---

### 8. Input Validation Gaps in API Routes

**Severity: MEDIUM**

| Route | Issue |
|-------|-------|
| `POST /execute` | `mission` field has no `min_length` or `max_length` validation |
| `POST /gateway/{channel}/messages` | `conversation_id` has no format validation |
| Session routes | `session_id` path parameter not validated for length/format |
| All routes | `profile` parameter not validated against available profiles |

**Recommendation:** Add Pydantic field validators (`min_length`, `max_length`, `pattern`) to request models. Validate `profile` names against the config registry early.

---

### 9. Flaky Test Patterns

**Severity: MEDIUM**

| Test File | Issue |
|-----------|-------|
| `tests/unit/infrastructure/scheduler/test_scheduler_service.py` | `await asyncio.sleep(1.5)` with acknowledgment it "may flake on slow CI runners" |
| `tests/core/domain/test_planning_strategy_parallel_tools.py` | Timing-dependent assertions using `asyncio.sleep(self._delay)` |
| `tests/unit/infrastructure/tools/test_search_tools.py` | Blocking `time.sleep(0.05)` inside async test |
| `tests/unit/application/test_executor_performance.py` | Performance counter thresholds (50ms) sensitive to CI environment |

**Recommendation:** Replace timing-based assertions with deterministic approaches (events, barriers, mock clocks). Make performance thresholds configurable or use relative comparisons.

---

### 10. Design Inefficiencies

**Severity: LOW**

#### 10a. N+1 agent creation in session routes (`api/routes/sessions.py`)

Every session endpoint creates a full `Agent` instance just to access the state manager:
```python
agent = await factory.create_agent(profile=profile)
sessions = await agent.state_manager.list_sessions()
await agent.close()
```

Should inject `StateManager` directly via FastAPI dependency.

#### 10b. Conversation history unbounded in gateway (`application/gateway.py`)

Large conversation histories are loaded entirely into memory with no size checking or pagination. A chat with 10K+ messages could cause memory exhaustion.

#### 10c. `ToolCallStatus` is a bare class, not an Enum (`core/domain/planning_helpers.py`, lines 67–72)

Uses plain class attributes instead of `str, Enum` — inconsistent with the project's pattern of using enums from `core/domain/enums.py`.

#### 10d. Browser session lifecycle (`infrastructure/tools/native/browser_tool.py`)

Global `_session` variable persists across tool calls but is never explicitly closed unless the agent exits. Orphaned browser processes possible on crashes.

---

### 11. Test Suite Structural Issues

**Severity: LOW**

- Test-to-source file ratio is 57% (107 test files for 188 source files)
- API layer has the weakest ratio: 7 test files for 29 source files (24%)
- `tests/core/domain/test_planning_strategy_parallel_tools.py` duplicates conftest.py stub code instead of using shared fixtures
- 55 tests carry `skip` or `xfail` markers — unclear which are conditional vs incomplete
- Error-path / negative test cases are underrepresented across the suite

---

## Prioritized Action Plan

### P0 — Critical (address first)

| # | Area | Action | Effort |
|---|------|--------|--------|
| 1 | Type safety | Fix 196 mypy errors, starting with 90 `no-untyped-def` in Infrastructure | Batch by file |
| 2 | Blocking I/O | Convert `file_memory_store.py` to `aiofiles` | Small |
| 3 | Security | Add security headers middleware to FastAPI server | Small |
| 4 | Security | Restrict CORS default from `*` to explicit origins | Small |
| 5 | Coverage | Add tests for `llm_tool`, `memory_tool`, `multimedia_tool` (0% coverage) | Medium |

### P1 — High (next sprint)

| # | Area | Action | Effort |
|---|------|--------|--------|
| 6 | Coverage | Add Butler daemon tests, CLI command unit tests | Medium |
| 7 | Function length | Decompose `_react_loop()` (193 lines) into 3–4 functions | Medium |
| 8 | Security | Add `Path.resolve()` symlink validation to file tools | Small |
| 9 | Input validation | Add `min_length`/`max_length` to API request models | Small |
| 10 | Architecture | Remove `config_schema.py` re-export shim (core→application violation) | Small |

### P2 — Medium (subsequent sprints)

| # | Area | Action | Effort |
|---|------|--------|--------|
| 11 | Error handling | Replace `except Exception` with specific types in executor, registry, server | Medium |
| 12 | Function length | Refactor `PowerShellTool.execute()`, `PythonTool.execute()` | Medium |
| 13 | Architecture | Replace direct `SchedulerService` import in `butler_service.py` with protocol | Small |
| 14 | Flaky tests | Replace timing-based tests with deterministic approaches | Medium |
| 15 | Design | Inject `StateManager` directly in session routes instead of full agent | Small |

### P3 — Low (when convenient)

| # | Area | Action | Effort |
|---|------|--------|--------|
| 16 | Design | Convert `ToolCallStatus` to `str, Enum` | Trivial |
| 17 | Design | Add conversation history pagination in gateway | Medium |
| 18 | Design | Add explicit browser session cleanup on crash | Small |
| 19 | Tests | Refactor duplicated fixtures in parallel tools tests | Small |
| 20 | Tests | Triage 55 skipped/xfailed tests | Small |

---

## Decision

This ADR documents the current state and serves as a backlog of improvements. Each item should be tracked as a separate issue or story and addressed according to the priority tiers above.
