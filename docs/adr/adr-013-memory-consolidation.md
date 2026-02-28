# ADR-013: Agent Memory Consolidation

**Status:** Accepted
**Date:** 2026-02-28
**Deciders:** Architecture Team

## Context

Taskforce agents operate across many sessions but lack a mechanism to consolidate experiences into high-quality long-term memories. The existing `LearningService` extracts facts from individual conversations but does not:

- Detect patterns across multiple sessions
- Resolve contradictions between new and existing knowledge
- Produce structured, categorized memories (procedural, episodic, semantic, meta-cognitive)
- Assess the quality of extracted knowledge

This is analogous to how human memory works: short-term experiences are captured during the day, then consolidated during sleep into long-term memory through pattern detection, contradiction resolution, and structured storage.

## Decision

We introduce a **Memory Consolidation** subsystem with three main components:

1. **ExperienceTracker** — a non-invasive observer that captures `StreamEvent` data during agent execution without affecting the streaming pipeline
2. **FileExperienceStore** — file-based persistence for raw session experiences
3. **ConsolidationEngine** — an LLM-powered 5-phase pipeline that processes experiences into consolidated memories

### Architecture

```
Agent Execution
    │
    ▼ StreamEvents
ExperienceTracker (sync observe, async persist)
    │
    ▼ SessionExperience
FileExperienceStore (.taskforce/experiences/)
    │
    ▼ (on demand or auto)
ConsolidationEngine (5-phase LLM pipeline)
    │
    ▼ MemoryRecord (kind=CONSOLIDATED)
FileMemoryStore (.taskforce/memory.md)
```

### Consolidation Pipeline

| Phase | Name | Description |
|-------|------|-------------|
| 1 | Summarize | Per-session structured narrative via LLM |
| 2 | Detect Patterns | Cross-session pattern identification (batch only) |
| 3 | Resolve Contradictions | Compare against existing consolidated memories |
| 4 | Write Memories | Create/update/retire `MemoryRecord` entries |
| 5 | Assess Quality | Score consolidation quality (0.0–1.0) |

### Layer Placement

| Component | Layer | Rationale |
|-----------|-------|-----------|
| `ExperienceEvent`, `SessionExperience`, `ConsolidationResult` | Core/Domain | Pure data models |
| `ExperienceStoreProtocol`, `ConsolidationEngineProtocol` | Core/Interfaces | Layer boundary contracts |
| `ExperienceTracker`, `FileExperienceStore`, `ConsolidationEngine` | Infrastructure | I/O and LLM integration |
| `ConsolidationService` | Application | Orchestration and lifecycle |
| CLI commands, API routes | API | Entry points |

### Configuration

Opt-in via profile YAML:

```yaml
consolidation:
  enabled: false
  auto_capture: true
  auto_consolidate: false
  strategy: batch
  max_sessions: 50
  model_alias: main
  work_dir: .taskforce/experiences
```

## Alternatives Considered

1. **Extend LearningService only** — Simpler but cannot do cross-session analysis or structured consolidation
2. **External vector DB** — More powerful search but adds infrastructure dependency; file-based approach is consistent with existing patterns
3. **Always-on consolidation** — Risk of high LLM costs; opt-in with explicit triggers is safer

## Consequences

### Positive

- Agents improve over time by learning from past sessions
- Cross-session pattern detection enables higher-quality memories
- Contradiction resolution prevents stale/conflicting knowledge
- Non-invasive tracker has zero impact on existing execution performance
- Fully opt-in; no changes to existing behavior when disabled

### Negative

- LLM calls during consolidation add cost (mitigated by batch processing)
- File-based experience storage has no concurrent access control (acceptable for single-user/dev mode)
- Quality assessment is subjective and LLM-dependent

### Risks

- Large numbers of accumulated experiences could slow listing operations (mitigated by pagination and `unprocessed_only` filtering)
