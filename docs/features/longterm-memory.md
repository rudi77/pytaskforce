# Long-Term Memory

**Version:** 3.0
**Status:** Production-Ready
**Backend:** Unified Memory Service with Human-Like Memory Mechanics

---

## Overview

Taskforce agents maintain **persistent memory across sessions** using a unified memory service inspired by **cognitive science**. Memory records are stored as Markdown files with YAML front matter and are **profile-specific**, so each agent profile (coding, rag, etc.) retains its own isolated memory store.

### Human-Like Memory Model

The memory system models key principles from human cognition:

| Principle | Implementation | Human Analogy |
|-----------|---------------|---------------|
| **Forgetting Curve** | Ebbinghaus-style exponential decay over time | Memories fade unless reinforced |
| **Spaced Repetition** | Strength boost on recall, bigger boost after longer gaps | Reviewing strengthens memory traces |
| **Emotional Encoding** | Emotionally charged memories start stronger & decay slower | Amygdala enhances emotional memory |
| **Importance Floor** | High-importance memories never fully fade | Survival-relevant memories persist |
| **Associative Network** | Bidirectional links between related memories | One memory triggers related ones |
| **Spreading Activation** | Retrieving a memory boosts its neighbours | "Tip of the tongue" phenomenon |
| **Sleep Consolidation** | Periodic pipeline: decay → strengthen → pattern extraction → schema formation | REM sleep consolidates memories |

This enables agents to:

- Remember user preferences and working styles
- Track project context and architectural decisions
- Build cumulative knowledge across conversations
- Provide personalized and context-aware responses
- Naturally forget irrelevant information over time
- Discover connections between experiences

---

## Architecture

### Memory Record Model

Each memory entry is a **record** with structured metadata and human-like properties:

**Core fields:**
- **scope**: `session`, `profile`, `user`, `org`
- **kind**: `short_term`, `long_term`, `tool_result`, `epic_log`, `preference`, `learned_fact`, `consolidated`
- **tags**: list of keywords for filtering/search and association discovery
- **content**: Markdown body
- **metadata**: free-form JSON-compatible context

**Human-like properties:**
- **strength** (0.0–1.0): Current memory strength. Decays over time, increases on recall.
- **access_count**: Number of times retrieved. More accesses → stronger trace.
- **last_accessed**: Timestamp of most recent retrieval.
- **emotional_valence**: `neutral`, `positive`, `negative`, `surprise`, `frustration`
- **importance** (0.0–1.0): Perceived significance. Acts as a strength floor.
- **associations**: IDs of related memories forming an associative network.
- **decay_rate**: Per-hour decay constant. Lower = more persistent.

### Effective Strength Formula

The **effective strength** determines whether a memory surfaces during retrieval:

```
raw = strength × e^(−decay_rate × hours_since_access)
freq_boost = min(1.0 + log(access_count + 1) × 0.1, 1.5)
effective = max(raw × freq_boost, importance)
```

Memories are sorted by effective strength (most salient first) rather than simple recency.

### Default Strength & Decay by Kind

| Kind | Initial Strength | Decay Rate (per hour) | Analogy |
|------|------------------|-----------------------|---------|
| `short_term` | 0.4 | 0.05 | Working memory — fades fast |
| `long_term` | 0.8 | 0.002 | Consolidated declarative memory |
| `preference` | 0.9 | 0.001 | Deeply encoded personal traits |
| `learned_fact` | 0.85 | 0.003 | Semantic knowledge |
| `consolidated` | 0.75 | 0.002 | Abstracted from episodes |
| `tool_result` | 0.3 | 0.08 | Sensory echo — very transient |

### Emotional Encoding Effects

| Valence | Strength Boost | Decay Factor | Example |
|---------|---------------|--------------|---------|
| `neutral` | +0% | ×1.0 | Standard facts |
| `positive` | +10% | ×0.8 | Successful mission outcomes |
| `negative` | +15% | ×0.7 | Errors and failures (learn from mistakes) |
| `surprise` | +20% | ×0.6 | Unexpected discoveries |
| `frustration` | +12% | ×0.75 | Blocked by recurring issues |

### Storage Backend

- **Format:** YAML documents in a single Markdown file (`memory.md`)
- **Location:** Profile-specific (default: `<work_dir>/memory.md`)
- **Persistence:** File-based, survives agent restarts and system reboots
- **Isolation:** Separate store per profile/work dir
- **Backward Compatibility:** Legacy records without new fields load with sensible defaults

---

## Configuration

### Enable Memory for a Profile

Add the `memory` section and the `memory` tool to your profile YAML:

```yaml
# configs/coding_agent.yaml

profile: coding_agent
specialist: coding

persistence:
  type: file
  work_dir: .taskforce_coding

# Enable unified memory
memory:
  type: file
  store_dir: .taskforce_coding/memory
  context_injection:
    max_memories: 20           # Max memories injected into system prompt
    max_chars_per_memory: 500  # Per-record truncation
    max_total_chars: 3000      # Total injection budget
    kinds:                     # Kinds to auto-inject
      - preference
      - learned_fact
      - consolidated
      - long_term
    scope: user

tools:
  - python
  - file_read
  - memory
```

**Key Configuration Fields:**

| Field | Description |
|-------|-------------|
| `memory.type` | `file` (default file-backed store) |
| `memory.store_dir` | Directory for memory records |
| `memory.context_injection` | Controls auto-injection into system prompt |
| `tools` | Include `memory` to expose the memory tool |

---

## Memory Tool

The unified `memory` tool provides CRUD operations and human-like memory management.

### Core Actions

**`add`** — store a memory record with optional emotional tagging

```json
{
  "action": "add",
  "scope": "user",
  "kind": "learned_fact",
  "tags": ["decision", "architecture"],
  "content": "We standardized on file-backed memory with Markdown records.",
  "emotional_valence": "positive",
  "importance": 0.8
}
```

**`search`** — search with combined keyword relevance × memory strength scoring

```json
{
  "action": "search",
  "query": "architecture decisions",
  "scope": "user",
  "limit": 5
}
```

**`list`** / **`get`** / **`update`** / **`delete`** — standard CRUD (unchanged)

### Human-Like Actions

**`reinforce`** — strengthen a memory (spaced repetition effect)

```json
{
  "action": "reinforce",
  "record_id": "<id>"
}
```

The boost is larger when more time has passed since last access, mirroring the spacing effect in human memory research.

**`associate`** — link two memories bidirectionally

```json
{
  "action": "associate",
  "record_id": "<id_a>",
  "target_id": "<id_b>"
}
```

Associations create an interconnected knowledge network. When one memory is recalled, associated memories receive a transient strength boost (spreading activation).

**`decay_sweep`** — run a forgetting pass

```json
{
  "action": "decay_sweep"
}
```

Calculates effective strength for all memories. Weak memories (below threshold) are archived. This mimics the natural forgetting of irrelevant information.

---

## Automatic Memory Injection

At session start, the **MemoryContextLoader** automatically injects the most salient memories into the system prompt:

1. Fetches all memories of configured kinds
2. Filters out archived and very weak memories (effective strength < 0.15)
3. Sorts by **effective strength** (not recency)
4. Reinforces injected memories (they're being "recalled")
5. Formats with strength indicators and emotion icons

Example injected section:

```
## LONG-TERM MEMORY
The following memories were automatically loaded...

- **[PREFERENCE]** [vivid] User prefers Python over JavaScript
- **[LEARNED FACT]** [clear] (+) Project uses FastAPI for REST APIs
- **[CONSOLIDATED]** [fading] Architecture follows clean patterns
- **[LEARNED FACT]** [dim] (!?) Old deployment process was problematic
```

Strength indicators: `[vivid]` (≥0.8), `[clear]` (≥0.5), `[fading]` (≥0.3), `[dim]` (<0.3)

Emotion icons: `(+)` positive, `(-)` negative, `(!)` surprise, `(?!)` frustration

---

## Memory Consolidation (Sleep Cycle)

The consolidation engine runs a multi-phase pipeline inspired by human sleep-based memory consolidation:

### Pipeline Phases

1. **Decay** — Apply the forgetting curve to all existing memories. Archive those below threshold.
2. **Strengthen** — Reinforce memories that were referenced during recent sessions.
3. **Summarize** — Distill each session experience into a structured narrative with emotional valence and importance scoring.
4. **Detect Patterns** — Find recurring themes across sessions (batch mode).
5. **Resolve Contradictions** — Merge or retire conflicting memories.
6. **Write Memories** — Persist new consolidated records with appropriate strength, emotion, and importance.
7. **Build Associations** — Create links between thematically related memories.
8. **Schema Formation** — When 3+ episodic memories share a pattern, abstract into semantic knowledge (like hippocampal generalization during sleep).
9. **Quality Assessment** — Score the consolidation run.

Enable via `consolidation.enabled: true` in your profile YAML.

---

## Best Practices

✅ **At conversation start:** memories are auto-injected — no explicit search needed

✅ **When learning:** tag memories with emotional context (`emotional_valence`) and importance

✅ **When important:** set high `importance` (0.8–1.0) to prevent forgetting

✅ **Use tags:** enable automatic association discovery between related memories

✅ **Periodic consolidation:** run consolidation to extract patterns and form schemas

✅ **Trust the decay:** don't manually delete — let irrelevant memories naturally fade

---

## Troubleshooting

**Symptom:** memory records are not appearing

1. Verify the `memory` tool is enabled in the profile.
2. Check `memory.store_dir` points to a writable directory.
3. Confirm the profile `work_dir` exists and is writable.

**Symptom:** important memories are fading

1. Set `importance` to 0.8+ when creating the record.
2. Use `reinforce` action to strengthen on explicit access.
3. Check `emotional_valence` — emotional memories decay slower.

**Symptom:** too many weak memories in prompt

1. Adjust `context_injection.max_memories` in profile YAML.
2. Run a `decay_sweep` to archive weak memories.
3. The min injection strength threshold is 0.15.

---

## Roadmap

- [x] Automatic summarization/compaction via Memory Consolidation
- [x] Human-like forgetting curve (Ebbinghaus)
- [x] Spaced repetition reinforcement on recall
- [x] Emotional valence encoding
- [x] Associative memory network with spreading activation
- [x] Schema formation from episodic patterns
- [ ] Optional vector index for semantic recall
- [ ] Multi-user memory with access control
- [ ] Web UI for memory visualization and network graph
