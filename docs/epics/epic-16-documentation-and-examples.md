# Epic 16: Documentation and Examples (OpenAPI + Diagrams + Tutorials) - Brownfield Enhancement

**Status:** Draft  
**Priorität:** Medium  
**Owner:** Development Team  
**Scope:** Small brownfield epic (max 3 stories)

## Epic Goal
Improve usability and onboarding by providing **richer API docs**, **architecture diagrams**, and **hands-on examples** for tools, profiles, and custom agents.

## Epic Description

### Existing System Context
- **Current relevant functionality:** FastAPI already produces OpenAPI; the repo contains extensive architecture docs under `docs/architecture/`.
- **Technology stack:** FastAPI OpenAPI, markdown docs, (optional) Jupyter notebooks.
- **Integration points:**
  - `src/taskforce/api/server.py` + routes for OpenAPI metadata
  - `docs/architecture/**` for diagrams and system explanation
  - `configs/**` for profile examples

### Enhancement Details
- **What's being added/changed:**
  - Improve OpenAPI documentation with examples for common missions and error responses.
  - Add/update diagrams for the core execution flow (legacy Agent + LeanAgent).
  - Add a tutorial notebook demonstrating custom tool and profile creation.
- **Success criteria:** A new developer can run a sample mission and extend tools with minimal guidance.

## Stories (max 3)

1. **Story 16.1: Enhance OpenAPI docs with examples**
   - Add request/response examples for `/execute` and `/execute/stream`.
   - Document `lean` vs legacy execution and error response schema (ties to Epic 11).

2. **Story 16.2: Add/refresh architecture diagrams**
   - Provide diagrams showing API → executor → factory → agent → tools/state.
   - Keep diagrams aligned to current code structure and naming.

3. **Story 16.3: Add tutorial notebook**
   - Demonstrate: creating a simple tool, adding it to config, running via CLI/API.
   - Keep dependencies minimal; prefer existing stack.

## Compatibility Requirements
- [ ] No runtime behavior changes required for docs-only work

## Risk Mitigation
- **Primary Risk:** Docs drift from implementation.
- **Mitigation:** Reference exact files/paths; keep examples tested (smoke).
- **Rollback Plan:** N/A (documentation-only changes).

## Definition of Done
- [ ] OpenAPI examples added and accurate
- [ ] Diagrams added/updated and match current architecture
- [ ] Tutorial notebook added and runnable

---

## Story Manager Handoff

"Please develop detailed user stories for this epic. Key considerations:

- Focus on high-signal docs: how to run, how to configure profiles, how to add tools/custom agents.
- Keep examples aligned to existing endpoints and CLI flags.
- Avoid adding heavy dependencies for documentation tooling."


