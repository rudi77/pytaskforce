# ADR-014: SLM-Based Context Enricher (Bio-Mimetic Memory)

**Status:** Accepted
**Date:** 2026-03-26
**Deciders:** Architecture Team

## Context

The existing memory system provides keyword and semantic search to inject relevant memories into the agent's system prompt (`load_memory_context`). However, this retrieval-only approach cannot:

- Generate **associative** connections between memories that share no keywords
- Synthesise **behavioural patterns** from multiple past interactions
- Surface **dream-generated insights** in a natural, contextual way

Human cognition does not simply "look up" memories; it generates an associative context — a feeling of familiarity, relevant intuitions — before conscious reasoning begins. This is the "tip of the tongue" phenomenon: knowledge that influences thinking without explicit recall.

## Decision

We introduce an optional **SLM Context Enricher** that runs a small language model (e.g. 1-3B parameters via Ollama) to generate a concise "intuition block" before the ReAct loop starts.

### Architecture

```
User Mission
    |
    v
load_memory_context()          <-- existing: keyword/semantic retrieval
    |
    v
run_context_enrichment()       <-- NEW: SLM generates associative context
    |
    v
_build_system_prompt()
    |
    +-- base prompt
    +-- plan status
    +-- memory context            (retrieved memories)
    +-- enrichment context        (SLM-generated intuitions)  <-- NEW
    +-- skill instructions
    |
    v
ReAct Loop starts
```

### Three Enrichment Categories

1. **Factual** — Past facts, decisions, or events relevant to the mission
2. **Behavioural** — Recognised user preferences, habits, communication style
3. **Dreamed** — Optimisations and creative insights from dream/sleep cycles

### Key Design Decisions

- **Disabled by default** (`context_enricher.enabled: false`). Opt-in per profile.
- **Graceful degradation**: Timeout (default 5s) and error handling ensure the enricher never blocks or crashes agent execution.
- **Protocol-based**: `ContextEnricherProtocol` in `core/interfaces/` allows alternative implementations.
- **Reuses LLM Router**: The enricher uses `model_alias: slm` which routes through the existing `LLMRouter` infrastructure.
- **Concise output**: Max ~200 tokens to avoid bloating the context window.

## Alternatives Considered

### 1. Extend existing `load_memory_context` with generative step
Rejected because it would mix retrieval and generation concerns, making it harder to disable or swap.

### 2. LoRA fine-tuning of the SLM on agent experiences
Deferred to a future iteration. The current approach uses prompt-based enrichment which requires no training infrastructure.

### 3. RAG-only (no generative enrichment)
The baseline. Works well for exact recall but cannot synthesise patterns or produce novel associations.

## Consequences

### Positive
- Agents can leverage associative memory without explicit tool calls
- Dream cycle insights become actionable during normal execution
- Minimal latency overhead (~100-200ms for local SLM inference)
- Fully backward-compatible (disabled by default)

### Negative
- Requires a local SLM setup (Ollama) for full functionality
- Adds another optional dependency to the system
- Quality depends on the SLM's capability

## Configuration

```yaml
# In profile YAML
context_enricher:
  enabled: false          # Opt-in
  model_alias: slm        # Must match an alias in llm_config.yaml
  max_tokens: 200
  timeout_seconds: 5.0
  categories:
    - factual
    - behavioral
    - dreamed
```

```yaml
# In llm_config.yaml
models:
  slm: "ollama/qwen2:1.5b"

routing:
  rules:
    - condition: "hint:enrichment"
      model: slm
```

## Related

- [ADR-007: Unified Memory Service](adr-007-unified-memory-service.md)
- [ADR-012: Dynamic LLM Selection](adr-012-dynamic-llm-selection.md)
- [ADR-013: Memory Consolidation](adr-013-memory-consolidation.md)
