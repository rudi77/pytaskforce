# ADR-014: Generative Dreaming System

**Status:** Accepted
**Date:** 2026-03-25
**Deciders:** Architecture Team

## Context

The memory consolidation pipeline (ADR-013) processes raw session experiences into long-term memories. However, it is purely **reactive** — it summarises what happened but never generates new knowledge. Human sleep does more than consolidate; REM dreaming actively recombines memories, processes emotions, and simulates future scenarios.

Additionally, the original 9-phase consolidation pipeline had grown overly complex with redundant phases (Decay+Strengthen both iterating all memories, Pattern Detection and Schema Formation both extracting generalisations, a full LLM call just for quality scoring).

## Decision

### 1. Simplify the Consolidation Pipeline (9 → 4 phases)

| New Phase | Replaces Old Phases | LLM Calls |
|-----------|-------------------|-----------|
| **Maintain** — decay + strengthen + associations | Phases 1, 2, 7 | 0 |
| **Distill** — summarise sessions | Phase 3 | 1 per session |
| **Integrate** — patterns + contradictions + schemas | Phases 4, 5, 8 | 1 combined |
| **Persist** — write/update/retire memories | Phase 6 | 0 |

Phase 9 (Quality Assessment) is replaced by an algorithmic score. This reduces LLM calls from 5 to 2 per consolidation run while preserving all capabilities.

### 2. Add Generative Dreaming (new component)

A `DreamEngine` runs **after** consolidation and generates novel knowledge:

| Dream Phase | Cognitive Analogue | Description |
|-------------|-------------------|-------------|
| **Replay** | Hippocampal replay | Re-narrate strong memories with variations |
| **Recombination** | Dream content mixing | Merge distant memories for cross-domain insights |
| **Emotional Processing** | REM regulation | Reappraise negative memories, dampen valence |
| **Prediction** | Threat simulation | Generate forward-looking contingency plans |

A configurable `max_llm_calls` budget caps total LLM calls. When exhausted, remaining phases degrade gracefully (skip or use algorithmic-only fallbacks).

### 3. Shared LLM Helpers

Common utilities (`call_llm_json`, `parse_json`, `resolve_valence`, `resolve_memory_kind`) are extracted into `infrastructure/memory/llm_helpers.py` to avoid duplication between `ConsolidationEngine` and `DreamEngine`.

## Architecture

### Layer Placement

| Component | Layer | File |
|-----------|-------|------|
| `DreamCycle`, `DreamInsight`, `DreamConfig` | Core/Domain | `core/domain/dream.py` |
| `DreamEngineProtocol` | Core/Interfaces | `core/interfaces/dreaming.py` |
| `DreamEngine` | Infrastructure | `infrastructure/memory/dream_engine.py` |
| LLM helpers | Infrastructure | `infrastructure/memory/llm_helpers.py` |
| `DreamService`, `build_dream_components` | Application | `application/dream_service.py` |
| CLI commands | API | `api/cli/commands/butler.py` |

### Integration Points

- **Post-consolidation hook**: `ConsolidationService` optionally triggers dreaming after each consolidation run via `DreamService.trigger_dream(trigger=POST_CONSOLIDATION)`.
- **Butler scheduler**: `ScheduleActionType.RUN_DREAM_CYCLE` allows periodic dreaming via the butler daemon.
- **EventRouter**: `RuleActionType.RUN_DREAM_CYCLE` enables event-triggered dreaming.

### Configuration

```yaml
dreaming:
  enabled: false
  max_memories_per_phase: 20
  max_llm_calls: 4
  replay_variations: 3
  recombination_pairs: 4
  emotional_decay_factor: 0.15
  novelty_threshold: 0.4
  model_alias: fast
  schedule_expression: "0 3 * * *"
  trigger_after_consolidation: true
```

## Consequences

### Positive

- Consolidation is simpler (740 → ~450 lines, 9 → 4 phases)
- LLM cost per consolidation run reduced by ~60%
- Generative dreaming produces genuinely novel knowledge
- Emotional processing naturally reduces accumulated frustration over time
- Configurable LLM budget prevents runaway costs

### Negative

- Combined Integration prompt is more complex than individual prompts
- Dream insights may occasionally be low quality (mitigated by novelty threshold filtering)
- Breaking change: existing code depending on the old 9-phase structure needs updating

### Risks

- Combined Integrate phase may produce lower quality results than separate calls (monitor quality scores)
- Dream insights add to memory volume over time (mitigated by decay/archival)
