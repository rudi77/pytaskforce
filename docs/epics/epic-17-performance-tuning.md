# Epic 17: Performance Tuning (Step Limits + Parallelization Opportunities) - Brownfield Enhancement

**Status:** Draft  
**Priorität:** Medium  
**Owner:** Development Team  
**Scope:** Small brownfield epic (max 3 stories)

## Epic Goal
Improve runtime efficiency by tuning step budgets and reducing latency where safe, without changing mission results.

## Epic Description

### Existing System Context
- **Current relevant functionality:** `LeanAgent` supports configurable `max_steps` via profile config (`AgentFactory` reads `agent.max_steps`). Some fast-path behavior exists in legacy `Agent`.
- **Technology stack:** async execution, tool calling, context budgeting already present.
- **Integration points:**
  - `src/taskforce/core/domain/lean_agent.py` (step loop limits)
  - `src/taskforce/application/factory.py` (config wiring for max_steps)
  - Tool execution and batching opportunities depend on strategy/plan (ties to Epic 10)

### Enhancement Details
- **What's being added/changed:**
  - Allow step limits to be derived from mission complexity (optional heuristic) while preserving explicit overrides.
  - Where independent tool calls are possible (e.g., plan-and-execute), execute in parallel to reduce wall-clock time.
- **Success criteria:** Reduced average mission latency for multi-tool workflows; fewer “max steps reached” failures for complex missions when configured.

## Stories (max 3)

1. **Story 17.1: Adaptive step limit policy (optional)**
   - Implement a minimal heuristic to suggest/choose `max_steps` based on mission size/agent type.
   - Preserve explicit `agent.max_steps` overrides.

2. **Story 17.2: Parallelize independent tool calls (strategy-scoped)**
   - Add parallel execution only where the plan declares independence (ties to `PlanAndExecuteStrategy` from Epic 10).
   - Ensure output ordering and state persistence are deterministic.

3. **Story 17.3: Add performance measurements**
   - Capture per-step/tool durations and total mission timing.
   - Add a lightweight benchmark/regression guard (non-flaky).

## Compatibility Requirements
- [ ] Explicit config values take precedence (no surprise behavior)
- [ ] Parallelization must be opt-in and safe

## Risk Mitigation
- **Primary Risk:** Parallel tool calls cause race conditions or nondeterminism.
- **Mitigation:** Constrain parallelization to read-only tools and/or explicitly independent steps.
- **Rollback Plan:** Disable parallelization via config.

## Definition of Done
- [ ] Adaptive step policy implemented (opt-in)
- [ ] Safe parallel execution implemented for eligible cases
- [ ] Measurements available for tuning

---

## Story Manager Handoff

"Please develop detailed user stories for this epic. Key considerations:

- Keep performance tuning configurable and backward compatible.
- Parallelization must not change correctness; restrict scope to safe tool sets or strategy-scoped execution."


