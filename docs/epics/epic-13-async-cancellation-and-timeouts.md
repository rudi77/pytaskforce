# Epic 13: Async I/O, Cancellation, and Timeouts - Brownfield Enhancement

**Status:** Draft  
**Priorität:** Hoch  
**Owner:** Development Team  
**Scope:** Small brownfield epic (max 3 stories)

## Epic Goal
Improve reliability under load by ensuring **blocking work doesn’t stall the event loop**, adding **consistent cancellation handling**, and making **timeouts configurable** for both tool executions and LLM calls.

## Epic Description

### Existing System Context
- **Current relevant functionality:** Some tools already implement timeout handling (e.g., `shell_tool.py`) and catch `asyncio.CancelledError` in places.
- **Technology stack:** asyncio, FastAPI, async tools, LLM provider abstraction.
- **Integration points:**
  - `src/taskforce/infrastructure/tools/native/shell_tool.py` (timeouts + cancellation)
  - LLM provider (`src/taskforce/infrastructure/llm/**`) and protocol (`src/taskforce/core/interfaces/llm.py`)
  - `src/taskforce/application/executor.py` (mission orchestration boundary)

### Enhancement Details
- **What's being added/changed:** A consistent, configurable timeout/cancellation story across tools and LLM calls, plus use of `asyncio.to_thread()` where unavoidable blocking I/O exists.
- **How it integrates:** Executor provides cancellation/timeout context; tools/LLM respect it; `CancelledError` is handled gracefully with cleanup.
- **Success criteria:** Long-running tasks can be cancelled without leaving corrupted state; runaway tasks are bounded by timeouts.

## Stories (max 3)

1. **Story 13.1: Standardize timeout configuration**
   - Add profile config keys for `llm.timeout_seconds` and default tool timeouts (where applicable).
   - Ensure explicit per-tool timeout parameters still work.

2. **Story 13.2: Propagate cancellation cleanly**
   - Ensure `asyncio.CancelledError` is treated as cancellation (not “generic failure”).
   - Ensure state persistence and tool contexts are cleaned up on cancellation.

3. **Story 13.3: Wrap blocking operations**
   - Identify any blocking operations in tools and wrap with `asyncio.to_thread()` or an executor pool where appropriate.
   - Add focused tests/smoke checks that event loop remains responsive.

## Compatibility Requirements
- [ ] Default behavior unchanged unless timeouts configured
- [ ] Cancellation does not corrupt persisted session state

## Risk Mitigation
- **Primary Risk:** Over-aggressive timeouts causing premature failures.
- **Mitigation:** Conservative defaults; clear logging of effective timeout values.
- **Rollback Plan:** Disable new timeout enforcement via config.

## Definition of Done
- [ ] Configurable timeouts for LLM + key tools
- [ ] Consistent cancellation handling and cleanup
- [ ] Blocking work wrapped where needed
- [ ] Tests cover cancellation/timeout scenarios

---

## Story Manager Handoff

"Please develop detailed user stories for this epic. Key considerations:

- Integration points: tools (especially `shell_tool.py`), LLM provider abstraction, and `AgentExecutor`.
- Preserve backward compatibility: explicit tool timeouts still override defaults.
- Verify both legacy `Agent` and `LeanAgent` flows handle cancellation/timeout gracefully."


