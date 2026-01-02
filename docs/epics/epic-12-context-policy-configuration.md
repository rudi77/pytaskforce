# Epic 12: Context Policy Tuning via Config + Env Overrides - Brownfield Enhancement

**Status:** Draft  
**Priorität:** Medium  
**Owner:** Development Team  
**Scope:** Small brownfield epic (max 3 stories)

## Epic Goal
Allow operators to **tune context limits without code changes** by exposing `ContextPolicy` and related budgeting parameters in YAML profiles with **environment-variable overrides** for fast operational adjustments.

## Epic Description

### Existing System Context
- **Current relevant functionality:** `ContextPolicy` exists (`src/taskforce/core/domain/context_policy.py`) and is created from config in `AgentFactory` (`_create_context_policy`).
- **Technology stack:** YAML profiles, application factory wiring, LeanAgent context pack injection.
- **Integration points:**
  - `src/taskforce/core/domain/context_policy.py`
  - `src/taskforce/core/domain/context_builder.py`
  - `src/taskforce/application/factory.py` (`_create_context_policy`)

### Enhancement Details
- **What's being added/changed:** Document and formalize profile keys (e.g., `context_policy.max_total_chars`, `max_items`, `max_chars_per_item`) and introduce env overrides like `TASKFORCE_CONTEXT_MAX_TOTAL_CHARS`.
- **How it integrates:** Profile loader merges env overrides into config before constructing `ContextPolicy`.
- **Success criteria:** Operators can adjust context budgets in prod without redeploying code; invalid config is rejected with clear errors.

## Stories (max 3)

1. **Story 12.1: Define and document context policy config keys**
   - Ensure profile schema is clear and examples exist for dev/staging/prod.
   - Confirm defaults remain conservative and safe.

2. **Story 12.2: Add environment variable overrides**
   - Implement env override merge for context policy values (validated and typed).
   - Provide a single place to resolve precedence: env > profile > defaults.

3. **Story 12.3: Add tests for policy parsing and boundary behavior**
   - Unit tests for config parsing and validation behavior.
   - Integration smoke test verifying `LeanAgent` injects a budgeted pack under different limits.

## Compatibility Requirements
- [ ] Default behavior unchanged (conservative defaults still apply if no config provided)
- [ ] Invalid overrides fail fast with clear messages

## Risk Mitigation
- **Primary Risk:** Misconfigured budgets causing degraded answer quality.
- **Mitigation:** Provide safe defaults and guardrails (min/max ranges) and clear logging of effective values.
- **Rollback Plan:** Ignore env overrides (profile-only) and rely on defaults.

## Definition of Done
- [ ] Profile keys for context tuning documented and supported
- [ ] Env overrides supported with precedence and validation
- [ ] Tests cover parsing and runtime behavior

---

## Story Manager Handoff

"Please develop detailed user stories for this epic. Key considerations:

- Integration points: `ContextPolicy` (`src/taskforce/core/domain/context_policy.py`) and `AgentFactory._create_context_policy` (`src/taskforce/application/factory.py`).
- Ensure changes are config-driven and backward compatible.
- Each story must verify `LeanAgent` default behavior remains intact and context pack injection respects limits."


