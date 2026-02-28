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

The engine runs 5 phases:

### Phase 1: Summarize
Each session experience is summarized into a structured narrative with key learnings and tool patterns.

### Phase 2: Detect Patterns (Batch Only)
Cross-session analysis identifies recurring patterns, strategies, and preferences.

### Phase 3: Resolve Contradictions
New learnings are compared against existing consolidated memories. Contradictions are resolved by keeping the newer information, keeping the existing, or merging.

### Phase 4: Write Memories
Consolidated memories are written as `MemoryRecord` entries with `kind=CONSOLIDATED` and metadata including `consolidation_kind` (procedural, episodic, semantic, meta_cognitive).

### Phase 5: Quality Assessment
The consolidation run is scored on a 0.0–1.0 scale for relevance, diversity, and non-redundancy.

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
