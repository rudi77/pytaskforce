# Epic 20: Tool Lifecycle Management (Async Close + Context Managers) - Brownfield Enhancement

**Status:** Draft  
**Priorität:** Medium  
**Owner:** Development Team  
**Scope:** Small brownfield epic (max 3 stories)

## Epic Goal
Ensure tools that maintain external resources (HTTP sessions, DB clients, MCP connections) are cleaned up reliably by formalizing a **tool lifecycle contract** (optional `close()` / async context manager support) and invoking it consistently.

## Epic Description

### Existing System Context
- **Current relevant functionality:** Both `Agent` and `LeanAgent` provide `close()` and maintain MCP contexts; some infrastructure clients implement async context management (e.g., Azure Search base client).
- **Technology stack:** async Python, tool wrappers, MCP client.
- **Integration points:**
  - `src/taskforce/core/interfaces/tools.py` (ToolProtocol contract)
  - `src/taskforce/core/domain/agent.py` and `src/taskforce/core/domain/lean_agent.py` (`close()` implementations)
  - `src/taskforce/infrastructure/tools/mcp/client.py` and other tools with external resources

### Enhancement Details
- **What's being added/changed:**
  - Extend tool contract to optionally support `async close()` (or `__aenter__/__aexit__`) and define expectation.
  - Executor/agent ensures cleanup at the right times (normal completion, failure, cancellation).
  - Add tests verifying cleanup is called.
- **Success criteria:** No leaked connections/resources after missions; shutdown is predictable.

## Stories (max 3)

1. **Story 20.1: Extend ToolProtocol with optional async close lifecycle**
   - Add an optional `close()` contract (or separate protocol) and update wrappers to preserve it.

2. **Story 20.2: Ensure executor invokes lifecycle hooks**
   - Guarantee cleanup on completion/failure/cancellation for both agent types.
   - Ensure MCP contexts are closed consistently.

3. **Story 20.3: Add tests for lifecycle behavior**
   - Unit tests with fake tools verifying `close()` is awaited.
   - Integration smoke tests verifying no resource warnings/leaks (where feasible).

## Compatibility Requirements
- [ ] Tools without `close()` continue to work unchanged
- [ ] Cleanup must not change mission results

## Risk Mitigation
- **Primary Risk:** Double-closing resources or closing too early.
- **Mitigation:** Idempotent close patterns and clear ordering.
- **Rollback Plan:** Keep lifecycle optional and only enforced for tools that implement it.

## Definition of Done
- [ ] Tool lifecycle contract defined and documented
- [ ] Cleanup invoked reliably in all exit paths
- [ ] Tests cover lifecycle behavior

---

## Story Manager Handoff

"Please develop detailed user stories for this epic. Key considerations:

- Integration points: ToolProtocol, both agents' `close()`, and executor orchestration.
- Keep lifecycle optional and backward compatible.
- Verify cleanup occurs even on cancellation/timeouts (ties to Epic 13)."


