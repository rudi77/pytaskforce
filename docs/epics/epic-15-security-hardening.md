# Epic 15: Security Hardening (Tool Sandbox + Allowlist + Approval Policies) - Brownfield Enhancement

**Status:** Draft  
**Priorität:** Hoch  
**Owner:** Development Team  
**Scope:** Small brownfield epic (max 3 stories)

## Epic Goal
Harden the framework against unsafe execution by constraining risky tools (Python/shell/web) via **sandboxing**, **URL allowlists**, and **configurable approval policies** based on existing `approval_risk_level`.

## Epic Description

### Existing System Context
- **Current relevant functionality:** Tools expose `approval_risk_level` in several implementations; tool execution includes safety messaging and timeouts in `shell_tool.py`.
- **Technology stack:** async tools, config profiles, FastAPI/CLI execution.
- **Integration points:**
  - `src/taskforce/infrastructure/tools/native/shell_tool.py` (high-risk execution surface)
  - `src/taskforce/infrastructure/tools/**` (tool wrappers + approval risk levels)
  - `src/taskforce/application/executor.py` (central enforcement point)

### Enhancement Details
- **What's being added/changed:**
  - Constrain Python execution (sandbox approach chosen by project constraints).
  - Add URL/domain allowlist enforcement for web-facing tools.
  - Expand approval policy into configurable behavior (e.g., block, require confirmation) based on `approval_risk_level`.
- **How it integrates:** Executor enforces approval rules; tools enforce allowlists/sandbox boundaries.
- **Success criteria:** High-risk actions are gated; SSRF-style access is reduced; unsafe Python execution is constrained.

## Stories (max 3)

1. **Story 15.1: Implement configurable tool approval policy**
   - Define policy config (per risk level) and enforce it centrally.
   - Add a clear “blocked by policy” outcome surfaced to API/CLI.

2. **Story 15.2: Add URL/domain allowlist for web tools**
   - Enforce allowlists at tool boundary and make it configurable.
   - Add tests for allowlisted vs blocked domains.

3. **Story 15.3: Sandbox Python execution**
   - Choose a sandbox mechanism aligned to constraints (minimal deps, Windows dev).
   - Ensure filesystem/network restrictions are applied.

## Compatibility Requirements
- [ ] Defaults remain permissive enough for dev (optional: strict-by-default in prod profile only)
- [ ] Existing tool behavior unchanged unless policy/allowlist configured

## Risk Mitigation
- **Primary Risk:** Over-restricting tools breaks legitimate workflows.
- **Mitigation:** Profile-based enforcement (dev vs prod), clear error messages, and easy overrides.
- **Rollback Plan:** Disable policies/allowlists/sandbox via config.

## Definition of Done
- [ ] Approval policy implemented and enforced
- [ ] Web allowlist implemented and tested
- [ ] Python sandbox implemented and tested
- [ ] Documentation updates describing configuration and safety model

---

## Story Manager Handoff

"Please develop detailed user stories for this epic. Key considerations:

- Integration points: approval policies should be enforced centrally (executor), but tools should also self-enforce allowlist/sandbox boundaries.
- Keep changes configurable; avoid introducing heavy dependencies unless required.
- Verify existing missions still run in dev profile without surprises."


