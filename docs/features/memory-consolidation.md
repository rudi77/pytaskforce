# Memory Consolidation

Memory consolidation allows Taskforce agents to learn from past execution sessions by automatically capturing experiences and consolidating them into high-quality long-term memories.

## Overview

The consolidation system works in two phases:

1. **Experience Capture** — During agent execution, the `ExperienceTracker` silently observes all `StreamEvent`s and builds a structured `SessionExperience` record (tool calls, plan updates, errors, token usage, etc.).

2. **Consolidation** — On demand (or automatically), the `ConsolidationEngine` processes accumulated experiences through a 5-phase LLM pipeline to produce consolidated memories.

## Quick Start

### 1. Enable in Profile

Add a `consolidation` section to your profile YAML:

```yaml
# src/taskforce/configs/dev.yaml (or your custom profile)
consolidation:
  enabled: true
  auto_capture: true        # Capture experiences during execution
  auto_consolidate: false   # Set true for immediate consolidation after each session
  strategy: batch            # immediate | batch | scheduled
  max_sessions: 50
  model_alias: main
  work_dir: .taskforce/experiences
```

### 2. Run Missions (Experiences Are Captured Automatically)

```bash
taskforce run mission "Analyze the sales data"
taskforce run mission "Generate monthly report"
```

### 3. Trigger Consolidation

```bash
# Consolidate all unprocessed experiences
taskforce memory consolidate --strategy batch

# Dry run to see what would be consolidated
taskforce memory consolidate --dry-run

# View captured experiences
taskforce memory experiences

# View consolidation statistics
taskforce memory stats
```

## CLI Commands

| Command | Description |
|---------|-------------|
| `taskforce memory consolidate` | Trigger consolidation of captured experiences |
| `taskforce memory experiences` | List captured session experiences |
| `taskforce memory stats` | Show memory and consolidation statistics |

### Consolidate Options

| Option | Default | Description |
|--------|---------|-------------|
| `--strategy` | `batch` | Strategy: `immediate` or `batch` |
| `--max-sessions` | `20` | Maximum sessions to process |
| `--dry-run` | `false` | Preview what would be consolidated |
| `--profile` | `dev` | Configuration profile to use |

## REST API

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/v1/memory/consolidate` | POST | Trigger consolidation |
| `/api/v1/memory/experiences` | GET | List experiences |
| `/api/v1/memory/consolidations` | GET | List past consolidation runs |

## Consolidation Pipeline

The engine runs a simplified 4-phase pipeline (see [ADR-014](../adr/adr-014-generative-dreaming.md)):

### Phase 1: Maintain (no LLM)
Single pass over all existing memories: apply the forgetting curve (decay), archive weak memories, reinforce session-related memories, and build tag-based associations.

### Phase 2: Distill (1 LLM call per session)
Each session experience is summarized into a structured narrative with key learnings, tool patterns, memory kind, emotional valence, and importance.

### Phase 3: Integrate (1 combined LLM call)
A single LLM call detects cross-session patterns, resolves contradictions with existing memories, and forms abstract schemas from groups of related learnings.

### Phase 4: Persist
Write, update, and retire `MemoryRecord` entries with `kind=CONSOLIDATED` and metadata including `consolidation_kind` (procedural, episodic, semantic, meta_cognitive). Quality is scored algorithmically.

## Generative Dreaming

After consolidation, an optional **dreaming** phase can generate genuinely new knowledge by recombining existing memories. See [Generative Dreaming](./generative-dreaming.md) for details.

## Memory Kinds

Consolidated memories are categorized:

| Kind | Description |
|------|-------------|
| `procedural` | How-to knowledge (tool patterns, workflows) |
| `episodic` | Specific session outcomes and experiences |
| `semantic` | General facts and relationships |
| `meta_cognitive` | Self-awareness about agent capabilities/limitations |

## Storage

- **Experiences**: `.taskforce/experiences/{session_id}.json`
- **Consolidation results**: `.taskforce/experiences/_consolidations/{id}.json`
- **Consolidated memories**: Stored in the standard memory file (`.taskforce/memory.md`) with `kind: consolidated`

## Architecture

See [ADR-013: Memory Consolidation](../adr/adr-013-memory-consolidation.md) for the full architectural decision record.
