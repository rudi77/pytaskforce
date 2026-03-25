# Generative Dreaming

Generative Dreaming extends the memory consolidation system by creating **new knowledge** from existing memories. Inspired by REM sleep, it recombines, varies, and simulates against the memory corpus to produce novel insights.

## Overview

While consolidation is **reactive** (analyses what happened), dreaming is **generative** (creates what could be). Four dream phases mirror different aspects of sleep:

| Phase | Cognitive Analogue | What It Does |
|-------|-------------------|-------------|
| **Replay** | Hippocampal replay | Re-narrates strong memories with deliberate variations |
| **Recombination** | Dream content mixing | Merges memories from unrelated domains for cross-domain insights |
| **Emotional Processing** | REM regulation | Reappraises negative memories, dampens emotional charge over cycles |
| **Prediction** | Threat simulation | Generates forward-looking contingency plans from patterns |

## Quick Start

### 1. Enable in Profile

```yaml
# src/taskforce/configs/butler.yaml (or your custom profile)
dreaming:
  enabled: true
  max_llm_calls: 4
  trigger_after_consolidation: true
```

### 2. Trigger a Dream Cycle

```bash
# Manual trigger
taskforce butler dream

# View past cycles
taskforce butler dream history

# Show details
taskforce butler dream show <dream_id>
```

### 3. Automatic Dreaming

When `trigger_after_consolidation: true`, dreaming runs automatically after each consolidation pass. Alternatively, use the butler scheduler with a cron expression:

```yaml
dreaming:
  schedule_expression: "0 3 * * *"  # Dream at 3 AM daily
```

## Configuration

| Option | Default | Description |
|--------|---------|-------------|
| `enabled` | `false` | Enable/disable dreaming |
| `phases` | all 4 | Which phases to run (list of: replay, recombination, emotional_processing, prediction) |
| `max_memories_per_phase` | `20` | Maximum memories fed into each phase |
| `max_llm_calls` | `4` | Total LLM call budget across all phases |
| `replay_variations` | `3` | Number of memories to replay with variations |
| `recombination_pairs` | `4` | Number of cross-domain memory pairs |
| `emotional_decay_factor` | `0.15` | How much to dampen negative valence (0.0-1.0) |
| `novelty_threshold` | `0.4` | Filter out insights below this novelty score |
| `model_alias` | `fast` | LLM model alias to use |
| `schedule_expression` | `0 3 * * *` | Cron expression for scheduled dreaming |
| `trigger_after_consolidation` | `true` | Run dreaming after each consolidation |

## LLM Budget Control

The `max_llm_calls` setting caps total LLM calls per dream cycle. When the budget is exhausted, remaining phases degrade gracefully:

- **Replay** → skipped (no output)
- **Recombination** → skipped
- **Emotional Processing** → algorithmic only (dampens valence without LLM reappraisal)
- **Prediction** → skipped

Phases execute in configured order. Priority phases should be listed first.

## Dream Insights

Each dream phase produces `DreamInsight` objects with:

- **content**: The insight text
- **insight_type**: `variation`, `recombination`, `reappraisal`, or `prediction`
- **confidence**: How confident the insight is (0.0-1.0)
- **novelty_score**: How different from existing memories (0.0-1.0)
- **source_memory_ids**: Which memories contributed

Insights passing the `novelty_threshold` filter are persisted as `MemoryRecord` entries with `kind=CONSOLIDATED` and `metadata.source="dreaming"`.

## Storage

- **Dream cycles**: `.taskforce/dreams/{dream_id}.json`
- **Dream-generated memories**: Standard memory file with `metadata.source: dreaming`

## Architecture

See [ADR-014: Generative Dreaming](../adr/adr-014-generative-dreaming.md) for the full architectural decision record.

## CLI Commands

| Command | Description |
|---------|-------------|
| `taskforce butler dream` | Trigger a dream cycle manually |
| `taskforce butler dream history` | List past dream cycles |
| `taskforce butler dream show <id>` | Show dream cycle details |
