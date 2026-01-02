# Epic 18: Observability (Granular Logging + Metrics Export) - Brownfield Enhancement

**Status:** Draft  
**Priorität:** Medium  
**Owner:** Development Team  
**Scope:** Small brownfield epic (max 3 stories)

## Epic Goal
Add operational visibility by emitting **structured metrics** (counts/latencies/errors) and formalizing log categories so operators can monitor health and performance over time.

## Epic Description

### Existing System Context
- **Current relevant functionality:** structlog is used broadly; API includes health endpoints; there is no Prometheus metrics export in the codebase.
- **Technology stack:** FastAPI, structlog, async execution.
- **Integration points:**
  - `src/taskforce/application/executor.py` (central place to instrument missions/tools/LLM calls)
  - `src/taskforce/api/server.py` / routes (where to expose `/metrics`)
  - Tool execution wrappers (tool-level timings and failures)

### Enhancement Details
- **What's being added/changed:**
  - Emit counters and histograms: tool calls, tool failures, LLM call latency, mission duration, memory/context pack sizes.
  - Add `/metrics` endpoint (Prometheus format) behind optional config flag if desired.
  - Introduce log categories (e.g., `performance`, `security`) via consistent event naming/fields.
- **Success criteria:** Operators can graph mission throughput, failure rates, and latency; logs are filterable by category and session.

## Stories (max 3)

1. **Story 18.1: Define metric set and instrumentation points**
   - Decide metric names/labels (tool_name, agent_type, status).
   - Instrument executor boundaries for mission + LLM + tool metrics.

2. **Story 18.2: Expose Prometheus `/metrics` endpoint**
   - Add a simple metrics export (minimal dependency choice).
   - Add config to enable/disable metrics endpoint.

3. **Story 18.3: Log categorization and dashboards guidance**
   - Standardize log fields for performance/security categories.
   - Add doc guidance for recommended dashboards/alerts.

## Compatibility Requirements
- [ ] No breaking changes to API routes (new endpoint additive)
- [ ] Minimal overhead (metrics collection lightweight)

## Risk Mitigation
- **Primary Risk:** High-cardinality labels or heavy metrics overhead.
- **Mitigation:** Keep label sets small; avoid mission text as a label; sample if needed.
- **Rollback Plan:** Disable metrics via config.

## Definition of Done
- [ ] Metrics emitted for key events
- [ ] `/metrics` endpoint available (configurable)
- [ ] Logging categories standardized
- [ ] Basic docs for operators

---

## Story Manager Handoff

"Please develop detailed user stories for this epic. Key considerations:

- Instrument centrally in the executor to avoid scattered logic.
- Keep metric labels low-cardinality and privacy-safe.
- Ensure metrics work for both legacy `Agent` and `LeanAgent` flows."


