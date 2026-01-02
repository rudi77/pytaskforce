# Epic 14: Agent Reuse and Pooling - Brownfield Enhancement

**Status:** Draft  
**Priorität:** Medium  
**Owner:** Development Team  
**Scope:** Small brownfield epic (max 3 stories)

## Epic Goal
Reduce startup latency and improve throughput by **reusing heavy dependencies** (LLM clients, MCP clients, tool resources) across sessions when safe, without changing mission semantics.

## Epic Description

### Existing System Context
- **Current relevant functionality:** `AgentFactory` creates agents per request and already manages MCP tool contexts for lifecycle.
- **Technology stack:** async Python, dependency injection via `AgentFactory`, per-session state in `StateManagerProtocol`.
- **Integration points:**
  - `src/taskforce/application/factory.py` (construction + MCP contexts)
  - `src/taskforce/infrastructure/llm/**` (LLM provider instantiation)
  - `src/taskforce/infrastructure/tools/mcp/client.py` (MCP client lifecycle)

### Enhancement Details
- **What's being added/changed:** A small pooling/caching layer for reusable clients, with clear boundaries (stateless, thread-safe, no session leakage).
- **How it integrates:** `AgentFactory` obtains providers from a pool instead of constructing fresh instances each time.
- **Success criteria:** Reduced per-request setup overhead; no cross-session state bleed.

## Stories (max 3)

1. **Story 14.1: Pool LLM provider instances**
   - Cache/pool LLM provider clients keyed by profile/provider config.
   - Ensure configuration changes invalidate the pool entry.

2. **Story 14.2: Pool MCP clients / heavy tool dependencies**
   - Reuse MCP client connections where possible (respecting close semantics).
   - Ensure per-session authorization/context is not shared incorrectly.

3. **Story 14.3: Add measurements and regression checks**
   - Track and log agent construction duration.
   - Add a small integration test ensuring pooling does not leak state across sessions.

## Compatibility Requirements
- [ ] Mission behavior and outputs unchanged (pooling is internal optimization)
- [ ] No cross-session data leakage

## Risk Mitigation
- **Primary Risk:** Shared client state leaks or concurrency bugs.
- **Mitigation:** Only pool truly stateless clients; add guardrails and tests.
- **Rollback Plan:** Disable pooling via config and revert to per-request construction.

## Definition of Done
- [ ] LLM provider pooling implemented and validated
- [ ] MCP/tool pooling implemented where safe
- [ ] Metrics/logging demonstrate reduced setup overhead
- [ ] Tests verify no session leakage

---

## Story Manager Handoff

"Please develop detailed user stories for this epic. Key considerations:

- Integration points: `AgentFactory` and provider/tool construction.
- Ensure pooling is optional and safe by default.
- Verify both API and CLI flows behave unchanged."


