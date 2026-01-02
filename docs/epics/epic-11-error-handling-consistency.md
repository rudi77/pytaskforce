# Epic 11: Error-Handling Consistency & Standardized API Errors - Brownfield Enhancement

**Status:** Completed  
**Priorität:** Hoch  
**Owner:** Development Team  
**Scope:** Small brownfield epic (max 3 stories)

## Epic Goal
Make error handling **predictable and consistent** across tools, executor, and API by introducing a **unified exception hierarchy** and returning **standardized error objects** from the FastAPI layer.

## Epic Description

### Existing System Context
- **Current relevant functionality:** Execution flows through `AgentExecutor` (application) and returns via `src/taskforce/api/routes/execution.py`, which currently maps most failures to HTTP 500 with `detail=str(e)`.
- **Technology stack:** FastAPI + Pydantic, structlog, async tool execution.
- **Integration points:**
  - `src/taskforce/application/executor.py` (mission orchestration)
  - `src/taskforce/api/routes/execution.py` (error mapping to HTTP responses)
  - Tool implementations in `src/taskforce/infrastructure/tools/**` (many `except Exception` blocks)

### Enhancement Details
- **What's being added/changed:** A small set of **domain/application exceptions** (e.g., `LLMError`, `ToolError`, `PlanningError`, `ConfigError`, `CancelledError`) and a **single API error response shape** (e.g., `{code, message, details}`).
- **How it integrates:** Tools/executor raise typed exceptions; API converts them into uniform HTTP responses with stable codes.
- **Success criteria:** Clients can reliably parse error responses and differentiate error categories; logs remain structured with relevant context (`session_id`, `tool_name`, etc.).

## Stories (max 3)

1. **Story 11.1: Add unified exception hierarchy**
   - Add a minimal exception tree in a shared location (e.g., `src/taskforce/core/domain/errors.py` or `src/taskforce/core/interfaces/errors.py`).
   - Replace generic `raise Exception` / ad-hoc exceptions in key paths with typed exceptions.

2. **Story 11.2: Centralize error logging with structured context**
   - Ensure executor logs exceptions consistently with `session_id`, `agent_id/lean`, `tool_name` when applicable.
   - Avoid scattered `try/except` where possible; centralize handling in executor boundary.

3. **Story 11.3: Standardize FastAPI error responses**
   - Define a Pydantic schema for error responses (`code`, `message`, `details`).
   - Map known exception types to appropriate HTTP status codes (e.g., 400/404/408/409/500) consistently.

## Compatibility Requirements
- [ ] Existing success responses unchanged
- [ ] Error responses become more structured but remain backward compatible where feasible (optional: keep `detail` while adding structured fields)

## Risk Mitigation
- **Primary Risk:** Breaking clients that rely on `detail` strings.
- **Mitigation:** Version error response carefully (or include both `detail` + structured payload during transition).
- **Rollback Plan:** Revert API mapping to legacy `HTTPException(detail=str(e))` while keeping exception types internally.

## Definition of Done
- [ ] Typed exceptions used in executor/tools for common failure modes
- [ ] Consistent structured logging for failures
- [ ] API returns standardized error schema for known errors
- [ ] Regression tests updated/added for error cases

---

## Story Manager Handoff

"Please develop detailed user stories for this epic. Key considerations:

- Integration points: `src/taskforce/application/executor.py`, `src/taskforce/api/routes/execution.py`, tool implementations under `src/taskforce/infrastructure/tools/**`.
- Maintain backward compatibility where possible; error schema changes should not break existing happy paths.
- Each story must include verification that existing mission execution remains intact for both legacy `Agent` and `LeanAgent` flows."


