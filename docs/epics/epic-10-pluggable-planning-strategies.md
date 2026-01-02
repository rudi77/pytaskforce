# Epic 10: Pluggable Planning Strategies (LeanAgent) - Brownfield Enhancement

**Status:** Completed
**Priorität:** Hoch  
**Owner:** Development Team  
**Scope:** Small brownfield epic (max 3 stories) focused on planning strategy interchangeability

## Epic Goal
Enable **interchangeable planning strategies** for `LeanAgent` (default remains current ReAct-style native tool calling), so operators can select a strategy via **profile config** (and optionally API) without changing core agent code.

## Epic Description

### Existing System Context
- **Current relevant functionality:** `LeanAgent` executes missions via a single loop using **native tool calling** and uses `PlannerTool` for plan management and dynamic prompt injection. Legacy `Agent` still exists with a larger ReAct + TodoList path.
- **Technology stack:** Python 3.11, FastAPI (`src/taskforce/api`), Typer CLI (`src/taskforce/api/cli`), structlog, Pydantic; async execution throughout.
- **Integration points:**
  - `src/taskforce/core/domain/lean_agent.py` (execution loop + PlannerTool usage)
  - `src/taskforce/application/factory.py` (agent construction from YAML profiles)
  - `src/taskforce/api/routes/execution.py` + CLI `--lean` (request/flag wiring)

### Enhancement Details
- **What's being added/changed:** Introduce a `PlanningStrategy` abstraction and support selecting a strategy for `LeanAgent` (initially: **Native ReAct** = current behavior, plus **Plan-and-Execute**).
- **How it integrates:** `LeanAgent` delegates “what to do next” to a strategy object; `AgentFactory` reads strategy config and injects the selected strategy. API/CLI optionally exposes strategy selection as an override.
- **Success criteria (measurable):**
  - Default behavior remains unchanged (no strategy specified → current LeanAgent behavior).
  - At least one alternate strategy (“plan-and-execute”) can be selected and works end-to-end.
  - Strategy selection is configurable via profile YAML and validated.

## Stories (max 3)

1. **Story 10.1: Introduce `PlanningStrategy` interface and wire into `LeanAgent`**
   - **Brief:** Add a minimal `PlanningStrategy` protocol/ABC (and a `PlanStep`/decision model) and refactor `LeanAgent` to delegate next-step decisions to a strategy while preserving existing behavior via a default “NativeReActStrategy”.

2. **Story 10.2: Implement `PlanAndExecuteStrategy` for LeanAgent**
   - **Brief:** Implement a strategy that generates a plan up-front (using existing LLM/tooling conventions and `PlannerTool`) and then executes the plan step-by-step, updating plan status as it progresses.

3. **Story 10.3: Configuration + API/CLI selection + docs**
   - **Brief:** Add `agent.planning_strategy` (and optional `agent.planning_strategy_params`) to profile YAML, validate it, wire selection in `AgentFactory`, and (optionally) add a request/CLI override. Document examples and defaults.

## Compatibility Requirements
- [ ] **Existing APIs remain unchanged by default** (any new request field must be optional and backward compatible).
- [ ] **Default planning behavior remains current behavior** (no strategy configured → NativeReActStrategy).
- [ ] **Performance impact is minimal** (strategy abstraction overhead negligible vs LLM/tool latency).

## Risk Mitigation
- **Primary Risk:** Behavior drift or regressions in LeanAgent execution loop when delegating to a strategy layer.
- **Mitigation:** Keep NativeReActStrategy as a thin wrapper around existing logic; add regression-focused tests (smoke tests for both strategies).
- **Rollback Plan:** Disable strategy selection (force default) via config; revert strategy wiring while keeping interfaces isolated to new files.

## Definition of Done
- [ ] All 3 stories completed with acceptance criteria met
- [ ] Existing LeanAgent behavior verified unchanged when no strategy is configured
- [ ] Strategy selection works via profile config (and optional API/CLI override)
- [ ] Tests added/updated for strategy selection + execution
- [ ] Documentation updated with examples and recommended defaults

---

## Story Manager Handoff

"Please develop detailed user stories for this brownfield epic. Key considerations:

- This is an enhancement to an existing system running **Python/FastAPI/Typer** with an existing `LeanAgent` (native tool calling + `PlannerTool`).
- Integration points: `src/taskforce/core/domain/lean_agent.py`, `src/taskforce/application/factory.py`, `src/taskforce/api/routes/execution.py`, CLI `--lean`.
- Existing patterns to follow: dependency injection via `AgentFactory` profiles; backward-compatible request models; structlog logging.
- Critical compatibility requirements: **default behavior must not change**, new strategy selection must be optional, and tests must verify no regressions.
- Each story must include verification that existing functionality remains intact (LeanAgent default path and API/CLI flows).

The epic should maintain system integrity while delivering configurable, interchangeable planning strategies for LeanAgent."


