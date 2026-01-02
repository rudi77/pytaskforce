# Epic 19: Configuration Validation (Strict Schema + Runtime Validation) - Brownfield Enhancement

**Status:** Draft  
**Priorität:** Hoch  
**Owner:** Development Team  
**Scope:** Small brownfield epic (max 3 stories)

## Epic Goal
Prevent misconfiguration issues by validating YAML profiles and custom agent definitions with a **strict schema** at startup/registration time, returning descriptive errors.

## Epic Description

### Existing System Context
- **Current relevant functionality:** Profiles are loaded and consumed in `AgentFactory`; invalid values can surface later as runtime failures.
- **Technology stack:** Pydantic available; YAML-driven configuration across profiles and custom agents.
- **Integration points:**
  - `src/taskforce/application/factory.py` (profile parsing/usage)
  - Custom agent YAML loading (configs/custom) and API validation paths
  - Tool catalogs/mappers where tool names are resolved

### Enhancement Details
- **What's being added/changed:**
  - Pydantic models (or JSON Schema) for profile files with strict key handling (reject unknown keys).
  - Validation for custom agent definitions (unknown tools, missing required fields) with clear error messages.
  - Early validation on startup (and/or on agent registration) rather than during execution.
- **Success criteria:** Bad configs fail fast with actionable messages; supported keys are documented.

## Stories (max 3)

1. **Story 19.1: Define strict config schema for profiles**
   - Create Pydantic models for config sections (llm, tools, persistence, agent, context_policy).
   - Enforce `extra="forbid"` (or equivalent) to reject unknown keys.

2. **Story 19.2: Validate custom agent definitions on load**
   - Validate YAML structure and tool references.
   - Return descriptive errors via API (400) and CLI (human-readable).

3. **Story 19.3: Add startup/runtime validation hooks + tests**
   - Validate on app startup (server) and on CLI startup.
   - Add unit tests covering unknown keys and missing required fields.

## Compatibility Requirements
- [ ] Existing valid configs continue to work unchanged
- [ ] Validation errors are actionable and non-verbose

## Risk Mitigation
- **Primary Risk:** Strictness breaks “informal” configs currently in use.
- **Mitigation:** Introduce schema incrementally; allow a compatibility mode flag temporarily if needed.
- **Rollback Plan:** Switch to warnings-only mode for unknown keys.

## Definition of Done
- [ ] Strict schema validation for profiles
- [ ] Custom agent YAML validation with descriptive errors
- [ ] Startup/registration validation paths covered by tests

---

## Story Manager Handoff

"Please develop detailed user stories for this epic. Key considerations:

- Keep schemas minimal and aligned to existing config keys.
- Fail fast with clear errors; do not over-engineer validation rules.
- Ensure API returns 400 for invalid configs and 404 for missing agent IDs where applicable."


