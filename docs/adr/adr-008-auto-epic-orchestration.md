# ADR 008: Auto-Epic Orchestration

**Status:** Accepted
**Date:** 2026-02-17
**Decision makers:** Project team

## Context

Epic Orchestration (planner/worker/judge pipeline) is a powerful capability for
complex, multi-step missions. Until now it required explicit invocation via the
`taskforce epic run` command. Users had to decide upfront whether a mission was
complex enough to warrant multi-agent orchestration — a decision that often
requires domain knowledge the user may lack.

## Decision

We introduce **automatic epic detection**: a lightweight LLM-based classifier
that analyses the mission description before agent creation and routes complex
missions to the `EpicOrchestrator` automatically.

### Key design choices

| Choice | Rationale |
|--------|-----------|
| **LLM-based classification** (not rule-based) | Natural language nuance; adapts to new task types without code changes |
| **Fallback to SIMPLE on any error** | Safe default — classification failures must never block execution |
| **Confidence threshold (default 0.7)** | Only escalate when the classifier is sufficiently certain |
| **Fast/cheap model for classification** | Classification is a ~100-200 token call; latency and cost stay negligible |
| **Integration in `AgentExecutor`** | Single integration point covers CLI, API, and chat transparently |
| **Per-profile configuration** | Teams can enable auto-epic in `dev` but disable it in `prod` |
| **CLI override** | `--auto-epic` / `--no-auto-epic` provides explicit per-invocation control |

## Architecture

```
AgentExecutor.execute_mission_streaming()
    │
    ├── _classify_and_route_epic()
    │   ├── _resolve_auto_epic_config()   → AutoEpicConfig from profile
    │   └── TaskComplexityClassifier
    │       └── LLM call → TaskComplexityResult
    │
    ├─ SIMPLE → standard agent execution
    └─ EPIC   → _execute_epic_streaming() → EpicOrchestrator.run_epic()
```

### New components

| Component | Layer | File |
|-----------|-------|------|
| `TaskComplexity` enum | Core/Domain | `core/domain/epic.py` |
| `TaskComplexityResult` dataclass | Core/Domain | `core/domain/epic.py` |
| `AutoEpicConfig` Pydantic model | Core/Domain | `core/domain/config_schema.py` |
| `EventType.EPIC_ESCALATION` | Core/Domain | `core/domain/enums.py` |
| `TaskComplexityClassifier` | Application | `application/task_complexity_classifier.py` |
| Executor integration | Application | `application/executor.py` |

## Consequences

### Positive
- Users no longer need to know when to use epic mode
- Simple missions incur minimal overhead (~one fast LLM call)
- Fully backward-compatible — disabled by default
- Explicit `taskforce epic run` still works unchanged

### Negative
- Additional LLM call adds ~1-2 seconds latency per mission when enabled
- Classification accuracy depends on model quality (mitigated by confidence threshold)
- Subtle edge cases where classification may disagree with user intent (mitigated by `--no-auto-epic`)

## Alternatives Considered

1. **Rule-based classification** (keyword matching, regex): Simpler but brittle;
   fails for nuanced or domain-specific missions.
2. **Always-on epic mode**: Wasteful for simple tasks; slower and more expensive.
3. **User confirmation before escalation**: UX friction; auto-epic loses value
   if the user has to approve every time (can be added later as optional).
