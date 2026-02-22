# Recommended Improvements for Taskforce

**Date:** 2026-02-22
**Scope:** Full codebase analysis covering architecture, code quality, test coverage, error handling, and security.

---

## Executive Summary

| Area | Status | Key Metric |
|------|--------|------------|
| Architecture | Strong | 0 layer violations |
| Lint (ruff) | Needs work | 46 errors |
| Type safety (mypy) | Needs work | 138 errors in 58 files |
| Test coverage | Below target | 62% overall (target: 80%) |
| Core domain tests | Critical gap | ~3% of core domain files tested |
| Security | Minor hardening | 1 blocking (SSRF), 1 advisory |
| Function size | Needs refactoring | 10+ functions exceed 30-line limit |

---

## 1. Test Coverage (Priority: CRITICAL)

Overall coverage is **62%**, well below the project's stated 80% target. More importantly, coverage is *inverted* -- critical core business logic is nearly untested while less critical API plumbing has good coverage.

### 1.1 Core Domain: Near-Zero Coverage

The following core domain files have **no dedicated unit tests**:

| File | Risk | Why It Matters |
|------|------|----------------|
| `core/domain/agent.py` | Critical | ReAct loop -- the central execution engine |
| `core/domain/lean_agent.py` | Critical | Simplified agent variant used in production |
| `core/domain/planning_strategy.py` | Critical | All 4 planning strategies (native_react, plan_and_execute, plan_and_react, spar) |
| `core/domain/planning_helpers.py` | High | Shared planning utilities |
| `core/domain/context_builder.py` | High | Context construction for all prompts |
| `core/domain/token_budgeter.py` | High | Token cost control |
| `core/domain/models.py` | Medium | Core data models (ExecutionResult, StreamEvent, TokenUsage) |
| `core/domain/config_schema.py` | Medium | Configuration validation |
| `core/domain/memory_service.py` | Medium | Memory service logic |

**Lean agent components** also lack dedicated tests:
- `message_history_manager.py` (39% coverage, only via integration)
- `message_sanitizer.py` (41% coverage)
- `prompt_builder.py` (84% -- better but still gaps)
- `resource_closer.py` (69%)

**Recommendation:** Prioritize tests for `agent.py`, `lean_agent.py`, and `planning_strategy.py` first. These are the heart of the framework and should have >90% coverage per the project's own standards.

### 1.2 Infrastructure Tools: 12 of 19 Native Tools Untested

| Untested Tool | Coverage | Risk |
|---------------|----------|------|
| `shell_tool.py` | 34% | High -- security-sensitive |
| `git_tools.py` | 22% | High -- complex multi-operation tool |
| `web_tools.py` | 49% | High -- commonly used |
| `search_tools.py` | 30% | Medium -- commonly used |
| `edit_tool.py` | 32% | Medium |
| `llm_tool.py` | 43% | Medium |
| `multimedia_tool.py` | 20% | Low |
| `calendar_tool.py` | 33% | Low |

The tested tools (`browser_tool.py` at 80%, `file_tools.py` at 83%) demonstrate good patterns to follow.

### 1.3 Application Layer Gaps

| File | Coverage | Impact |
|------|----------|--------|
| `factory.py` | 49% | Critical -- central dependency injection |
| `agent_registry.py` | 18% | High -- custom agent API |
| `skill_manager.py` | 33% | High -- skill lifecycle |
| `skill_service.py` | 36% | High -- skill discovery |
| `plugin_discovery.py` | 41% | Medium |

### 1.4 Test Quality Issues

- **Trivial assertions over behavior testing:** Several test files (e.g., `test_tool_catalog.py`) only verify metadata (`tool.name == "ask_user"`) rather than actual tool behavior.
- **Timing-dependent tests:** `test_scheduler_service.py` uses `await asyncio.sleep(1.5)` which can flake on slow CI runners. Use `freezegun` or mock the clock.
- **Missing test infrastructure:** No `@pytest.mark.slow` markers, no `--maxfail` configuration, no timeout settings for hanging tests.

---

## 2. Type Safety (Priority: HIGH)

**138 mypy errors across 58 files.** Key categories:

### 2.1 Attribute Access on Wrong Types

```
factory.py:320: "Agent" has no attribute "_mcp_contexts"
factory.py:807: "Agent" has no attribute "_mcp_contexts"
factory.py:1059: "Agent" has no attribute "_mcp_contexts"
factory.py:1060: "Agent" has no attribute "_plugin_manifest"
```

These suggest `Agent` and `LeanAgent` have diverged in their interfaces. The factory accesses attributes that exist on one but not the other.

### 2.2 Incompatible Types

```
tool_builder.py:485: Argument "specialist" has incompatible type "Any | None"; expected "str"
tool_builder.py:536: Incompatible return value type (got "AgentTool", expected "ToolProtocol | None")
executor.py:601: expression has type "dict[str, Any]", variable has type "StreamEvent"
```

### 2.3 Missing Library Stubs

```
factory.py:24: Library stubs not installed for "yaml"
server.py:92: Library stubs not installed for "yaml"
```

**Recommendation:**
- Install `types-PyYAML` to resolve yaml stub errors.
- Set `disallow_untyped_defs = true` in mypy config (currently `false`) and fix incrementally.
- Fix the `Agent`/`LeanAgent` attribute access issues in `factory.py` -- these are potential runtime errors.

---

## 3. Linting (Priority: MEDIUM)

**46 ruff errors**, breaking down as:

| Error Code | Count | Description |
|------------|-------|-------------|
| W293 | 20 | Blank line contains whitespace |
| B904 | 14 | Missing `raise ... from err` in except clauses |
| W291 | 4 | Trailing whitespace |
| F821 | 3 | Undefined names (`structlog`, `Agent`, `AgentFactory`) |
| F841 | 1 | Unused variable |
| F401 | 2 | Unused imports |
| C416 | 1 | Unnecessary list comprehension |
| B007 | 1 | Unused loop variable |

### 3.1 B904: Missing Exception Chaining (14 occurrences)

All 14 are in API route handlers (`agents.py`, `execution.py`, etc.) where exceptions are caught and re-raised as `HTTPException` without `from err`. This loses the original traceback:

```python
# Current (loses context):
except FileExistsError as e:
    raise _http_exception(status_code=409, code="agent_exists", message=str(e))

# Fixed (preserves chain):
except FileExistsError as e:
    raise _http_exception(status_code=409, code="agent_exists", message=str(e)) from e
```

### 3.2 F821: Undefined Names (3 occurrences)

These indicate references to names that aren't imported -- potential runtime `NameError` exceptions.

**Recommendation:** Run `uv run ruff check --fix src/taskforce/` to auto-fix 19 of the 46 issues (whitespace). The B904 and F821 issues need manual fixes.

---

## 4. Function Size (Priority: HIGH)

The project's own coding standard mandates max 30 lines per function. 10+ functions significantly exceed this:

### 4.1 Critical (>200 lines)

| File | Function | Lines |
|------|----------|-------|
| `factory.py` | `_build_definition_from_config()` | ~271 |
| `factory.py` | `_assemble_lean_system_prompt()` | ~250 |
| `factory.py` | `_apply_extensions()` | ~216 |

### 4.2 High (100-200 lines)

| File | Function | Lines |
|------|----------|-------|
| `executor.py` | `execute_mission_streaming()` | ~170 |
| `executor.py` | `_create_agent()` | ~168 |
| `litellm_service.py` | `complete_stream()` | ~169 |
| `litellm_service.py` | `complete()` | ~119 |
| `factory.py` | `_build_system_prompt_for_definition()` | ~165 |

**Recommendation:** Extract cohesive blocks into well-named private methods. For example, `_build_definition_from_config()` likely handles tool resolution, prompt assembly, persistence setup, and LLM configuration -- each could be a separate method.

---

## 5. Security Hardening (Priority: MEDIUM)

### 5.1 SSRF Risk in Web and Browser Tools

`web_tools.py` (`web_fetch`) and `browser_tool.py` accept arbitrary URLs with no validation. An agent could be instructed to fetch:
- `http://127.0.0.1:8080/admin` (localhost services)
- `http://169.254.169.254/latest/meta-data/` (cloud metadata endpoint)
- `http://10.0.0.1/internal-api` (internal network)

**Recommendation:** Add a URL validator that blocks private/reserved IP ranges (RFC 1918, link-local, loopback) before making requests. This is standard for any tool that fetches user-controlled URLs.

### 5.2 Python Tool Sandbox

The `python_tool.py` sandbox exposes `__import__`, allowing dynamic imports including `os`, `subprocess`, etc. While the tool has an approval gate (`requires_approval`), this is defense-in-depth concern.

**Recommendation:** Document this as an accepted risk in the tool's docstring and in security documentation. Consider restricting `__builtins__` more aggressively for untrusted execution contexts.

### 5.3 Shell Tool Blocklist

The shell tool uses a blocklist approach (blocking known-dangerous commands like `rm -rf /`). Blocklists are inherently incomplete.

**Recommendation:** For production deployments, consider switching to an allowlist approach or running shell commands in a sandboxed environment (container, VM). Document the current blocklist-based approach as suitable for development/trusted contexts only.

---

## 6. Error Handling (Priority: MEDIUM)

### 6.1 Silent Failures in Executor and Factory

```python
# executor.py (lines ~715, 725, 760)
except Exception:
    return None  # Silent failure -- caller gets None with no context
```

When the executor fails to create an agent or load state, it returns `None` silently. The caller must then handle `None` defensively, often without knowing *why* the operation failed.

**Recommendation:** Either re-raise with context or return a typed error result (e.g., `Result[Agent, CreateError]`).

### 6.2 Blocking I/O in Async Context

Two locations use synchronous `open()` + `yaml.safe_load()` inside async code paths:

| File | Location | Issue |
|------|----------|-------|
| `litellm_service.py` | `__init__` (~line 144) | Blocking file read in constructor |
| `factory.py` | `_create_agent_from_config_file()` (~line 643) | Blocking YAML load |

**Recommendation:** Replace with `aiofiles.open()` + async YAML loading, or move to a synchronous initialization phase that runs before the event loop starts.

---

## 7. Dependency and Configuration (Priority: LOW)

### 7.1 Duplicate Dev Dependencies

`pyproject.toml` defines dev dependencies in both `[project.optional-dependencies].dev` and `[dependency-groups].dev` with identical content. This is redundant and could lead to drift.

**Recommendation:** Keep only `[dependency-groups].dev` (the modern `uv`-native approach) and remove the `[project.optional-dependencies].dev` section.

### 7.2 Mypy Configuration Too Lenient

```toml
disallow_untyped_defs = false
disallow_incomplete_defs = false
```

With these set to `false`, mypy won't flag functions missing type annotations at all. This undermines the project's stated requirement of "type annotations required on ALL function signatures."

**Recommendation:** Enable `disallow_untyped_defs = true` and `disallow_incomplete_defs = true`. Fix violations incrementally, starting with the core domain layer.

### 7.3 Large File: `file_agent_registry.py`

At 600+ lines, this file handles multiple concerns (agent CRUD, file I/O, serialization, validation). Consider splitting into focused modules.

---

## 8. Documentation Consistency (Priority: LOW)

### 8.1 Stale Project URLs

```toml
Homepage = "https://github.com/yourorg/pytaskforce"
```

The `yourorg` placeholder in `pyproject.toml` URLs should be updated to the actual organization.

### 8.2 Missing CHANGELOG

`pyproject.toml` references `Changelog = ".../CHANGELOG.md"` but no `CHANGELOG.md` file exists in the repository.

---

## Summary: Top 10 Improvements by Impact

| # | Improvement | Impact | Effort |
|---|-------------|--------|--------|
| 1 | Add unit tests for `agent.py`, `lean_agent.py`, `planning_strategy.py` | Critical -- core logic untested | Large |
| 2 | Add unit tests for `factory.py` | Critical -- DI wiring untested | Large |
| 3 | Fix 138 mypy errors (especially `Agent` attribute access in factory) | High -- potential runtime errors | Medium |
| 4 | Refactor oversized functions in `factory.py` (3 functions >200 lines) | High -- maintainability | Medium |
| 5 | Refactor oversized functions in `executor.py` and `litellm_service.py` | High -- maintainability | Medium |
| 6 | Add SSRF validation to `web_tools.py` and `browser_tool.py` | High -- security | Small |
| 7 | Fix 46 ruff lint errors (especially B904 exception chaining) | Medium -- code quality | Small |
| 8 | Add tests for high-risk tools (`shell_tool`, `git_tools`, `web_tools`) | Medium -- safety | Medium |
| 9 | Replace blocking I/O with async in `litellm_service.py` and `factory.py` | Medium -- event loop safety | Small |
| 10 | Enable strict mypy settings (`disallow_untyped_defs = true`) | Medium -- long-term type safety | Large (incremental) |
