"""LLM-powered memory consolidation engine — simplified sleep-cycle.

Processes raw session experiences through a streamlined 4-phase pipeline:

1. **Maintain** — Single pass: decay + strengthen + build associations (no LLM).
2. **Distill** — LLM summarises each session into key learnings.
3. **Integrate** — LLM resolves contradictions, detects patterns, and forms
   schemas in one combined call.
4. **Persist** — Write/update/retire ``MemoryRecord`` entries.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

import structlog

from taskforce.core.domain.experience import (
    ConsolidatedMemoryKind,
    ConsolidationResult,
    SessionExperience,
)
from taskforce.core.domain.memory import (
    EmotionalValence,
    MemoryKind,
    MemoryRecord,
    MemoryScope,
)
from taskforce.core.interfaces.llm import LLMProviderProtocol
from taskforce.core.interfaces.memory_store import MemoryStoreProtocol
from taskforce.infrastructure.memory.llm_helpers import (
    call_llm_json,
    resolve_memory_kind,
    resolve_valence,
)

logger = structlog.get_logger(__name__)

# ------------------------------------------------------------------
# Prompt templates
# ------------------------------------------------------------------

_SUMMARIZE_PROMPT = """\
Summarize the following agent session experience into a structured narrative.
Focus on:
- What the agent was asked to do (mission)
- Key decisions and tool usage patterns
- What worked well and what didn't
- Important facts discovered during execution

Session:
- Mission: {mission}
- Profile: {profile}
- Steps: {steps}
- Tool calls: {tool_calls}
- Errors: {errors}

Tool usage details:
{tool_details}

Plan updates:
{plan_updates}

Final answer excerpt:
{final_answer}

Output a JSON object with:
- "narrative": string (2-4 sentences summarizing the session)
- "key_learnings": list of strings (1-3 actionable insights)
- "tool_patterns": list of strings (tool usage patterns observed)
- "memory_kind": one of "procedural", "episodic", "semantic", "meta_cognitive"
- "emotional_valence": one of "neutral", "positive", "negative", "surprise", "frustration" \
(based on outcome: success=positive, errors=frustration, unexpected results=surprise)
- "importance": float 0.0-1.0 (how significant is this experience for future tasks?)

Output JSON only:
"""

_INTEGRATE_PROMPT = """\
Analyse the following session summaries and existing memories.
Perform three tasks in one pass:

1. **Patterns**: Identify recurring themes across sessions.
2. **Contradictions**: Compare new learnings against existing memories \
and flag conflicts.
3. **Schemas**: When 3+ learnings share a theme, extract an abstract principle.

Session summaries:
{summaries}

New learnings:
{new_learnings}

Existing consolidated memories:
{existing_memories}

Output a single JSON object with:
- "patterns": list of objects, each with "pattern" (string), "frequency" (int), \
"confidence" (float 0-1), "memory_kind" (string), "tags" (list), "importance" (float 0-1)
- "contradictions": list of objects, each with "new_learning" (string), \
"existing_memory_id" (string), "resolution" ("keep_new"|"keep_existing"|"merge"), \
"merged_content" (string, only if merge)
- "schemas": list of objects, each with "schema" (string, 1-2 sentences), \
"tags" (list), "importance" (float 0-1)

Output JSON only:
"""

# Threshold below which memories are archived during the maintain phase.
_DECAY_ARCHIVE_THRESHOLD = 0.10

# Minimum keyword overlap to trigger reinforcement.
_REINFORCE_MIN_OVERLAP = 2


class ConsolidationEngine:
    """Simplified 4-phase consolidation pipeline.

    Args:
        llm_provider: LLM service for analysis.
        memory_store: Memory store for persistence.
        model_alias: Model alias for LLM calls.
    """

    def __init__(
        self,
        llm_provider: LLMProviderProtocol,
        memory_store: MemoryStoreProtocol,
        model_alias: str = "main",
    ) -> None:
        self._llm = llm_provider
        self._memory_store = memory_store
        self._model_alias = model_alias

    async def consolidate(
        self,
        experiences: list[SessionExperience],
        existing_memories: list[MemoryRecord],
        strategy: str = "immediate",
    ) -> ConsolidationResult:
        """Run the simplified consolidation pipeline.

        Args:
            experiences: Session experiences to consolidate.
            existing_memories: Current consolidated memories.
            strategy: ``immediate`` or ``batch`` (batch enables patterns).

        Returns:
            Consolidation result with metrics.
        """
        result = ConsolidationResult(
            consolidation_id=uuid4().hex,
            strategy=strategy,
            sessions_processed=len(experiences),
            started_at=datetime.now(UTC),
            session_ids=[e.session_id for e in experiences],
        )

        if not experiences:
            result.ended_at = datetime.now(UTC)
            return result

        total_tokens = 0
        session_keywords = _extract_session_keywords(experiences)

        # Phase 1: MAINTAIN — decay + strengthen + associations (no LLM)
        maintain = await self._phase_maintain(existing_memories, session_keywords)
        result.memories_retired += maintain["archived"]
        logger.info(
            "consolidation.maintain_phase",
            decayed=maintain["decayed"],
            archived=maintain["archived"],
            strengthened=maintain["strengthened"],
            associations=maintain["associations"],
        )

        # Phase 2: DISTILL — LLM summarises sessions
        summaries = await self._phase_distill(experiences)
        total_tokens += sum(s.get("_tokens", 0) for s in summaries)

        # Phase 3: INTEGRATE — patterns + contradictions + schemas (1 LLM call)
        new_learnings = _collect_learnings(summaries)
        integration: dict[str, Any] = {"patterns": [], "contradictions": [], "schemas": []}
        if new_learnings:
            integration = await self._phase_integrate(
                summaries, new_learnings, existing_memories, strategy
            )
            total_tokens += integration.get("_tokens", 0)

        # Phase 4: PERSIST — write/update/retire memories
        created, updated, retired = await self._phase_persist(
            summaries=summaries,
            integration=integration,
            consolidation_id=result.consolidation_id,
        )
        result.memories_created = created
        result.memories_updated = updated
        result.memories_retired += retired
        result.contradictions_resolved = len(integration.get("contradictions", []))

        # Algorithmic quality score (replaces old LLM quality assessment)
        result.quality_score = _compute_quality_score(result)
        result.total_tokens = total_tokens
        result.ended_at = datetime.now(UTC)

        if hasattr(self._memory_store, "flush"):
            await self._memory_store.flush()

        logger.info(
            "consolidation.completed",
            consolidation_id=result.consolidation_id,
            strategy=strategy,
            sessions=result.sessions_processed,
            created=result.memories_created,
            updated=result.memories_updated,
            quality=result.quality_score,
        )
        return result

    # ------------------------------------------------------------------
    # Phase 1: MAINTAIN (no LLM)
    # ------------------------------------------------------------------

    async def _phase_maintain(
        self,
        existing_memories: list[MemoryRecord],
        session_keywords: set[str],
    ) -> dict[str, int]:
        """Decay, strengthen, and build associations in a single pass.

        Returns:
            Dict with counts: decayed, archived, strengthened, associations.
        """
        now = datetime.now(UTC)
        counts = {"decayed": 0, "archived": 0, "strengthened": 0, "associations": 0}
        active: list[MemoryRecord] = []

        for record in existing_memories:
            eff = record.effective_strength(now)
            if eff < _DECAY_ARCHIVE_THRESHOLD:
                if "archived" not in record.tags:
                    record.tags.append("archived")
                    record.strength = eff
                    await self._memory_store.update(record)
                    counts["archived"] += 1
                continue

            if eff < record.strength * 0.9:
                record.strength = eff
                await self._memory_store.update(record)
                counts["decayed"] += 1

            # Strengthen if session keywords overlap
            if "archived" not in record.tags and session_keywords:
                haystack = f"{record.content} {' '.join(record.tags)}".lower()
                overlap = sum(1 for kw in session_keywords if kw in haystack)
                if overlap >= _REINFORCE_MIN_OVERLAP:
                    record.reinforce(now)
                    await self._memory_store.update(record)
                    counts["strengthened"] += 1

            if "archived" not in record.tags:
                active.append(record)

        # Build tag-based associations
        counts["associations"] = _build_associations(active)
        for mem in active:
            if mem.associations:
                await self._memory_store.update(mem)

        return counts

    # ------------------------------------------------------------------
    # Phase 2: DISTILL (1 LLM call per session)
    # ------------------------------------------------------------------

    async def _phase_distill(
        self,
        experiences: list[SessionExperience],
    ) -> list[dict[str, Any]]:
        """Summarise each session experience via LLM."""
        summaries: list[dict[str, Any]] = []
        for exp in experiences:
            prompt = _format_summarize_prompt(exp)
            parsed = await call_llm_json(self._llm, prompt, self._model_alias)
            parsed["session_id"] = exp.session_id
            summaries.append(parsed)
        return summaries

    # ------------------------------------------------------------------
    # Phase 3: INTEGRATE (1 combined LLM call)
    # ------------------------------------------------------------------

    async def _phase_integrate(
        self,
        summaries: list[dict[str, Any]],
        new_learnings: list[str],
        existing_memories: list[MemoryRecord],
        strategy: str,
    ) -> dict[str, Any]:
        """Detect patterns, resolve contradictions, form schemas."""
        if strategy == "immediate" and not existing_memories:
            return {"patterns": [], "contradictions": [], "schemas": [], "_tokens": 0}

        summary_text = "\n\n".join(
            f"Session {s.get('session_id', '?')}:\n{s.get('narrative', '')}"
            for s in summaries
        )
        learnings_text = "\n".join(f"- {item}" for item in new_learnings[:20])
        memory_text = "\n".join(
            f"- [{m.id[:8]}] {m.content}" for m in existing_memories[:20]
        )

        prompt = _INTEGRATE_PROMPT.format(
            summaries=summary_text,
            new_learnings=learnings_text,
            existing_memories=memory_text or "(none)",
        )

        parsed = await call_llm_json(self._llm, prompt, self._model_alias)
        # Normalise: ensure all expected keys exist
        parsed.setdefault("patterns", [])
        parsed.setdefault("contradictions", [])
        parsed.setdefault("schemas", [])
        return parsed

    # ------------------------------------------------------------------
    # Phase 4: PERSIST
    # ------------------------------------------------------------------

    async def _phase_persist(
        self,
        summaries: list[dict[str, Any]],
        integration: dict[str, Any],
        consolidation_id: str,
    ) -> tuple[int, int, int]:
        """Write, update, and retire memory records.

        Returns:
            Tuple of (created, updated, retired) counts.
        """
        created = 0
        updated = 0
        retired = 0

        # Handle contradictions
        c_upd, c_ret = await self._handle_contradictions(
            integration.get("contradictions", []), consolidation_id
        )
        updated += c_upd
        retired += c_ret

        # Create memories from session summaries
        created += await self._write_summary_memories(summaries, consolidation_id)

        # Create memories from patterns
        created += await self._write_pattern_memories(
            integration.get("patterns", []), consolidation_id
        )

        # Create memories from schemas
        created += await self._write_schema_memories(
            integration.get("schemas", []), consolidation_id
        )

        return created, updated, retired

    async def _handle_contradictions(
        self,
        contradictions: list[dict[str, Any]],
        consolidation_id: str,
    ) -> tuple[int, int]:
        """Process contradiction resolutions.

        Returns:
            Tuple of (updated, retired) counts.
        """
        updated = 0
        retired = 0
        for contradiction in contradictions:
            resolution = contradiction.get("resolution", "keep_new")
            existing_id = contradiction.get("existing_memory_id", "")
            if resolution == "keep_existing" or not existing_id:
                continue

            existing = await self._memory_store.get(existing_id)
            if not existing:
                continue

            if resolution == "merge":
                existing.content = contradiction.get(
                    "merged_content", existing.content
                )
                existing.metadata["last_consolidation"] = consolidation_id
                existing.reinforce()
                await self._memory_store.update(existing)
                updated += 1
            elif resolution == "keep_new":
                existing.metadata["retired_by"] = consolidation_id
                existing.tags.extend(["retired", "archived"])
                existing.strength = 0.0
                await self._memory_store.update(existing)
                retired += 1
        return updated, retired

    async def _write_summary_memories(
        self,
        summaries: list[dict[str, Any]],
        consolidation_id: str,
    ) -> int:
        """Create memory records from session summaries."""
        created = 0
        for summary in summaries:
            valence = resolve_valence(summary.get("emotional_valence", "neutral"))
            importance = min(1.0, max(0.0, summary.get("importance", 0.5)))
            kind = resolve_memory_kind(summary.get("memory_kind", "semantic"))

            for learning in summary.get("key_learnings", []):
                record = MemoryRecord(
                    scope=MemoryScope.USER,
                    kind=MemoryKind.CONSOLIDATED,
                    content=learning,
                    tags=summary.get("tool_patterns", [])[:5],
                    metadata={
                        "source": "consolidation",
                        "consolidation_id": consolidation_id,
                        "consolidation_kind": kind.value,
                        "session_id": summary.get("session_id", ""),
                    },
                    emotional_valence=valence,
                    importance=importance,
                )
                await self._memory_store.add(record)
                created += 1
        return created

    async def _write_pattern_memories(
        self,
        patterns: list[dict[str, Any]],
        consolidation_id: str,
    ) -> int:
        """Create memory records from detected patterns."""
        created = 0
        for pattern in patterns:
            if pattern.get("confidence", 0) < 0.5:
                continue
            kind = resolve_memory_kind(pattern.get("memory_kind", "procedural"))
            importance = min(1.0, max(0.0, pattern.get("importance", 0.6)))
            record = MemoryRecord(
                scope=MemoryScope.USER,
                kind=MemoryKind.CONSOLIDATED,
                content=pattern.get("pattern", ""),
                tags=pattern.get("tags", [])[:5] + ["cross_session"],
                metadata={
                    "source": "consolidation",
                    "consolidation_id": consolidation_id,
                    "consolidation_kind": kind.value,
                    "frequency": pattern.get("frequency", 1),
                    "confidence": pattern.get("confidence", 0),
                },
                importance=importance,
            )
            await self._memory_store.add(record)
            created += 1
        return created

    async def _write_schema_memories(
        self,
        schemas: list[dict[str, Any]],
        consolidation_id: str,
    ) -> int:
        """Create memory records from extracted schemas."""
        created = 0
        for schema in schemas:
            schema_text = schema.get("schema", "")
            if not schema_text:
                continue
            importance = min(1.0, max(0.0, schema.get("importance", 0.7)))
            record = MemoryRecord(
                scope=MemoryScope.USER,
                kind=MemoryKind.CONSOLIDATED,
                content=schema_text,
                tags=schema.get("tags", [])[:5],
                metadata={
                    "source": "schema_formation",
                    "consolidation_id": consolidation_id,
                    "consolidation_kind": ConsolidatedMemoryKind.SEMANTIC.value,
                },
                importance=importance,
                emotional_valence=EmotionalValence.NEUTRAL,
            )
            await self._memory_store.add(record)
            created += 1
        return created


# ------------------------------------------------------------------
# Module-level helpers
# ------------------------------------------------------------------


def _extract_session_keywords(experiences: list[SessionExperience]) -> set[str]:
    """Extract keywords from session missions and tool calls."""
    keywords: set[str] = set()
    for exp in experiences:
        keywords.update(exp.mission.lower().split()[:20])
        for tc in exp.tool_calls:
            keywords.add(tc.tool_name.lower())
    return keywords


def _collect_learnings(summaries: list[dict[str, Any]]) -> list[str]:
    """Collect all new learnings from session summaries."""
    learnings: list[str] = []
    for s in summaries:
        learnings.extend(s.get("key_learnings", []))
    return learnings


def _build_associations(active_memories: list[MemoryRecord]) -> int:
    """Build bidirectional tag-based associations between memories."""
    associations_created = 0
    for i, mem_a in enumerate(active_memories):
        if not mem_a.tags:
            continue
        tags_a = set(mem_a.tags)
        for mem_b in active_memories[i + 1 :]:
            if not mem_b.tags:
                continue
            shared = tags_a & set(mem_b.tags)
            if shared and mem_b.id not in mem_a.associations:
                mem_a.associate_with(mem_b.id)
                mem_b.associate_with(mem_a.id)
                associations_created += 1
    return associations_created


def _format_summarize_prompt(exp: SessionExperience) -> str:
    """Format the summarize prompt for a single session."""
    tool_details = "\n".join(
        f"- {tc.tool_name}: {'success' if tc.success else 'FAILED'}"
        f" ({tc.duration_ms}ms)"
        for tc in exp.tool_calls[:20]
    )
    plan_text = "\n".join(
        f"- Step {pu.get('step', '?')}: {pu.get('action', '')}"
        for pu in exp.plan_updates[:10]
    )
    return _SUMMARIZE_PROMPT.format(
        mission=exp.mission[:500],
        profile=exp.profile,
        steps=exp.total_steps,
        tool_calls=len(exp.tool_calls),
        errors=len(exp.errors),
        tool_details=tool_details or "(none)",
        plan_updates=plan_text or "(none)",
        final_answer=exp.final_answer[:300] if exp.final_answer else "(none)",
    )


def _compute_quality_score(result: ConsolidationResult) -> float:
    """Compute a simple algorithmic quality score.

    Replaces the old LLM-based quality assessment with a heuristic
    based on consolidation output counts.
    """
    if result.memories_created == 0 and result.memories_updated == 0:
        return 0.0
    # Score based on: memories produced per session, contradiction handling
    per_session = result.memories_created / max(result.sessions_processed, 1)
    # 1-3 memories per session is ideal; more is diminishing
    production_score = min(per_session / 3.0, 1.0)
    # Bonus for handling contradictions
    contradiction_bonus = min(result.contradictions_resolved * 0.1, 0.2)
    return min(production_score + contradiction_bonus, 1.0)
