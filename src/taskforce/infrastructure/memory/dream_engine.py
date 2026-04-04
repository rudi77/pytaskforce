"""Generative dream engine — creates new knowledge from existing memories.

Four sub-phases mirror aspects of REM sleep:

1. **Replay with Variations** — Re-narrate strong memories with
   deliberate perturbations to extract latent lessons.
2. **Creative Recombination** — Merge memories from unrelated domains
   to discover cross-domain insights.
3. **Emotional Processing** — Reappraise negative memories, dampening
   their emotional charge over dream cycles.
4. **Predictive Simulation** — Generate forward-looking contingency
   plans from established patterns.

An LLM call budget (``DreamConfig.max_llm_calls``) caps total calls.
When the budget is exhausted, remaining phases degrade gracefully:
phases that require LLM calls are skipped, and emotional processing
falls back to a purely algorithmic dampening.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import structlog

from taskforce.core.domain.dream import (
    DreamConfig,
    DreamCycle,
    DreamInsight,
    DreamInsightType,
    DreamPhase,
    DreamStatus,
    DreamTrigger,
)
from taskforce.core.domain.memory import EmotionalValence, MemoryRecord
from taskforce.core.interfaces.llm import LLMProviderProtocol
from taskforce.core.interfaces.memory_store import MemoryStoreProtocol
from taskforce.infrastructure.memory.llm_helpers import call_llm_json

logger = structlog.get_logger(__name__)

# ------------------------------------------------------------------
# Prompt templates
# ------------------------------------------------------------------

_REPLAY_PROMPT = """\
You are an AI memory system performing dream-like replay.

Given these past experiences, imagine variations where conditions were \
different. For each experience, create one variation that reveals a \
latent lesson not obvious from the original.

Memories to replay:
{memories}

Output a JSON array of insights, each with:
- "content": string (the insight from the variation, 1-2 sentences)
- "source_ids": list of memory IDs that contributed
- "confidence": float 0.0-1.0
- "tags": list of keyword tags

Output JSON array only:
"""

_RECOMBINATION_PROMPT = """\
You are an AI memory system performing creative dream recombination.

These memory pairs come from DIFFERENT contexts. For each pair, find a \
creative connection or novel insight that bridges them.

Memory pairs:
{pairs}

Output a JSON array of insights, each with:
- "content": string (the cross-domain insight, 1-2 sentences)
- "source_ids": list of memory IDs that contributed
- "confidence": float 0.0-1.0
- "tags": list of keyword tags

Output JSON array only:
"""

_EMOTIONAL_PROMPT = """\
You are an AI memory system performing emotional reprocessing.

These memories carry negative emotional charge. For each, generate a \
constructive reframing that extracts the useful lesson while \
acknowledging the difficulty.

Negative memories:
{memories}

Output a JSON array of reappraisals, each with:
- "content": string (the constructive reframing, 1-2 sentences)
- "source_id": the memory ID being reappraised
- "tags": list of keyword tags

Output JSON array only:
"""

_PREDICTION_PROMPT = """\
You are an AI memory system performing predictive simulation.

Based on these established patterns and learned facts, generate 2-3 \
actionable predictions or contingency plans for likely future scenarios.

Pattern memories:
{memories}

Output a JSON array of predictions, each with:
- "content": string (the prediction or contingency plan, 1-3 sentences)
- "source_ids": list of memory IDs that informed this prediction
- "confidence": float 0.0-1.0
- "tags": list of keyword tags

Output JSON array only:
"""

# Emotional valence dampening targets: negative → neutral over cycles.
_VALENCE_DAMPENING: dict[EmotionalValence, EmotionalValence] = {
    EmotionalValence.FRUSTRATION: EmotionalValence.NEGATIVE,
    EmotionalValence.NEGATIVE: EmotionalValence.NEUTRAL,
}


class DreamEngine:
    """Generative dream engine with configurable LLM budget.

    Args:
        llm_provider: LLM service for generative phases.
        memory_store: Memory store for persisting emotional updates.
    """

    def __init__(
        self,
        llm_provider: LLMProviderProtocol,
        memory_store: MemoryStoreProtocol,
    ) -> None:
        self._llm = llm_provider
        self._memory_store = memory_store

    async def dream(
        self,
        memories: list[MemoryRecord],
        config: DreamConfig,
    ) -> DreamCycle:
        """Run a dream cycle on the given memories.

        Args:
            memories: Active (non-archived) memories to dream about.
            config: Dream configuration (phases, budget, etc.).

        Returns:
            Completed dream cycle with generated insights.
        """
        cycle = DreamCycle(
            started_at=datetime.now(UTC),
            status=DreamStatus.RUNNING,
            memories_processed=len(memories),
            trigger=DreamTrigger.MANUAL,
        )
        llm_calls_remaining = config.max_llm_calls
        total_tokens = 0

        phase_handlers = {
            DreamPhase.REPLAY: self._phase_replay,
            DreamPhase.RECOMBINATION: self._phase_recombination,
            DreamPhase.EMOTIONAL_PROCESSING: self._phase_emotional,
            DreamPhase.PREDICTION: self._phase_prediction,
        }

        try:
            for phase in config.phases:
                handler = phase_handlers.get(phase)
                if not handler:
                    continue
                insights, tokens, calls = await handler(
                    memories, config, llm_calls_remaining
                )
                cycle.insights.extend(insights)
                total_tokens += tokens
                llm_calls_remaining -= calls
        except Exception as exc:
            logger.error("dream.cycle_failed", error=str(exc))
            cycle.status = DreamStatus.FAILED
            cycle.ended_at = datetime.now(UTC)
            cycle.total_tokens = total_tokens
            return cycle

        # Filter by novelty threshold
        cycle.insights = [
            i for i in cycle.insights if i.novelty_score >= config.novelty_threshold
        ]

        cycle.status = DreamStatus.COMPLETED
        cycle.ended_at = datetime.now(UTC)
        cycle.total_tokens = total_tokens
        return cycle

    # ------------------------------------------------------------------
    # Phase A: Replay with Variations
    # ------------------------------------------------------------------

    async def _phase_replay(
        self,
        memories: list[MemoryRecord],
        config: DreamConfig,
        budget: int,
    ) -> tuple[list[DreamInsight], int, int]:
        """Replay strong memories with variations.

        Returns:
            Tuple of (insights, tokens_used, llm_calls_made).
        """
        if budget <= 0:
            return [], 0, 0

        candidates = _select_strongest(memories, config.replay_variations)
        if not candidates:
            return [], 0, 0

        memories_text = "\n".join(
            f"- [{m.id[:8]}] {m.content}" for m in candidates
        )
        prompt = _REPLAY_PROMPT.format(memories=memories_text)
        parsed = await call_llm_json(self._llm, prompt, config.model_alias)
        tokens = parsed.get("_tokens", 0)

        raw_items = parsed.get("items", []) if "items" in parsed else []
        insights = _parse_insights(raw_items, DreamInsightType.VARIATION, memories)
        return insights, tokens, 1

    # ------------------------------------------------------------------
    # Phase B: Creative Recombination
    # ------------------------------------------------------------------

    async def _phase_recombination(
        self,
        memories: list[MemoryRecord],
        config: DreamConfig,
        budget: int,
    ) -> tuple[list[DreamInsight], int, int]:
        """Combine distant memories for cross-domain insights.

        Returns:
            Tuple of (insights, tokens_used, llm_calls_made).
        """
        if budget <= 0:
            return [], 0, 0

        pairs = _select_distant_pairs(memories, config.recombination_pairs)
        if not pairs:
            return [], 0, 0

        pairs_text = "\n\n".join(
            f"Pair {i + 1}:\n  A: [{a.id[:8]}] {a.content}\n  B: [{b.id[:8]}] {b.content}"
            for i, (a, b) in enumerate(pairs)
        )
        prompt = _RECOMBINATION_PROMPT.format(pairs=pairs_text)
        parsed = await call_llm_json(self._llm, prompt, config.model_alias)
        tokens = parsed.get("_tokens", 0)

        raw_items = parsed.get("items", []) if "items" in parsed else []
        insights = _parse_insights(raw_items, DreamInsightType.RECOMBINATION, memories)
        return insights, tokens, 1

    # ------------------------------------------------------------------
    # Phase C: Emotional Processing
    # ------------------------------------------------------------------

    async def _phase_emotional(
        self,
        memories: list[MemoryRecord],
        config: DreamConfig,
        budget: int,
    ) -> tuple[list[DreamInsight], int, int]:
        """Process emotionally charged memories.

        If LLM budget allows, generates constructive reframings.
        Always applies algorithmic valence dampening.

        Returns:
            Tuple of (insights, tokens_used, llm_calls_made).
        """
        negative = [
            m
            for m in memories
            if m.emotional_valence in (EmotionalValence.NEGATIVE, EmotionalValence.FRUSTRATION)
            and m.effective_strength() > 0.3
        ]

        insights: list[DreamInsight] = []
        tokens = 0
        calls = 0

        # LLM reappraisal if budget allows
        if budget > 0 and negative:
            mem_text = "\n".join(
                f"- [{m.id[:8]}] ({m.emotional_valence.value}) {m.content}"
                for m in negative[: config.max_memories_per_phase]
            )
            prompt = _EMOTIONAL_PROMPT.format(memories=mem_text)
            parsed = await call_llm_json(self._llm, prompt, config.model_alias)
            tokens = parsed.get("_tokens", 0)
            calls = 1

            raw_items = parsed.get("items", []) if "items" in parsed else []
            for item in raw_items:
                if not isinstance(item, dict) or not item.get("content"):
                    continue
                source_id = item.get("source_id", "")
                insights.append(
                    DreamInsight(
                        content=item["content"],
                        source_memory_ids=[source_id] if source_id else [],
                        insight_type=DreamInsightType.REAPPRAISAL,
                        confidence=0.6,
                        novelty_score=0.5,
                        tags=item.get("tags", [])[:5],
                        emotional_valence=EmotionalValence.POSITIVE,
                    )
                )

        # Algorithmic dampening (always runs)
        _dampen_emotional_valence(negative, config.emotional_decay_factor)
        for m in negative:
            await self._memory_store.update(m)

        return insights, tokens, calls

    # ------------------------------------------------------------------
    # Phase D: Predictive Simulation
    # ------------------------------------------------------------------

    async def _phase_prediction(
        self,
        memories: list[MemoryRecord],
        config: DreamConfig,
        budget: int,
    ) -> tuple[list[DreamInsight], int, int]:
        """Generate forward-looking predictions from patterns.

        Returns:
            Tuple of (insights, tokens_used, llm_calls_made).
        """
        if budget <= 0:
            return [], 0, 0

        # Use semantic/consolidated memories with pattern metadata
        patterns = [
            m
            for m in memories
            if m.metadata.get("source") in ("consolidation", "schema_formation")
            and m.effective_strength() > 0.4
        ]
        if not patterns:
            return [], 0, 0

        mem_text = "\n".join(
            f"- [{m.id[:8]}] {m.content}"
            for m in patterns[: config.max_memories_per_phase]
        )
        prompt = _PREDICTION_PROMPT.format(memories=mem_text)
        parsed = await call_llm_json(self._llm, prompt, config.model_alias)
        tokens = parsed.get("_tokens", 0)

        raw_items = parsed.get("items", []) if "items" in parsed else []
        insights = _parse_insights(raw_items, DreamInsightType.PREDICTION, memories)
        return insights, tokens, 1


# ------------------------------------------------------------------
# Module-level helpers
# ------------------------------------------------------------------


def _select_strongest(
    memories: list[MemoryRecord],
    count: int,
) -> list[MemoryRecord]:
    """Select the N strongest non-archived memories."""
    active = [m for m in memories if "archived" not in m.tags]
    active.sort(key=lambda m: m.effective_strength(), reverse=True)
    return active[:count]


def _select_distant_pairs(
    memories: list[MemoryRecord],
    count: int,
) -> list[tuple[MemoryRecord, MemoryRecord]]:
    """Select memory pairs with minimal tag overlap (maximum distance).

    Prefers pairs from different consolidation kinds for diversity.
    """
    active = [m for m in memories if "archived" not in m.tags and m.tags]
    if len(active) < 2:
        return []

    scored: list[tuple[float, int, int]] = []
    for i in range(len(active)):
        tags_i = set(active[i].tags)
        for j in range(i + 1, len(active)):
            tags_j = set(active[j].tags)
            overlap = len(tags_i & tags_j)
            total = len(tags_i | tags_j) or 1
            distance = 1.0 - (overlap / total)
            scored.append((distance, i, j))

    scored.sort(reverse=True)
    pairs: list[tuple[MemoryRecord, MemoryRecord]] = []
    used: set[int] = set()
    for _distance, i, j in scored:
        if i in used or j in used:
            continue
        pairs.append((active[i], active[j]))
        used.add(i)
        used.add(j)
        if len(pairs) >= count:
            break
    return pairs


def _parse_insights(
    raw_items: list[Any],
    insight_type: DreamInsightType,
    all_memories: list[MemoryRecord],
) -> list[DreamInsight]:
    """Parse raw LLM output items into DreamInsight objects."""
    memory_ids = {m.id[:8]: m.id for m in all_memories}
    insights: list[DreamInsight] = []

    for item in raw_items:
        if not isinstance(item, dict) or not item.get("content"):
            continue
        # Resolve short IDs to full IDs
        source_ids = [
            memory_ids.get(sid, sid) for sid in item.get("source_ids", [])
        ]
        insights.append(
            DreamInsight(
                content=item["content"],
                source_memory_ids=source_ids,
                insight_type=insight_type,
                confidence=item.get("confidence", 0.5),
                novelty_score=0.5,  # Default; can be refined later
                tags=item.get("tags", [])[:5],
            )
        )
    return insights


def _dampen_emotional_valence(
    memories: list[MemoryRecord],
    factor: float,
) -> None:
    """Algorithmically reduce negative emotional charge.

    Shifts valence one step toward neutral and reduces strength
    of the negative encoding by the given factor.
    """
    for m in memories:
        new_valence = _VALENCE_DAMPENING.get(m.emotional_valence)
        if new_valence:
            m.emotional_valence = new_valence
        m.strength = max(0.1, m.strength * (1.0 - factor))
