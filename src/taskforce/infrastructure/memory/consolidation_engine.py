"""LLM-powered memory consolidation engine with human-like sleep-cycle.

Processes raw session experiences through a multi-phase pipeline that
mirrors how human memory consolidation works during sleep:

1. **Decay phase** — Apply the forgetting curve: weaken memories that
   haven't been accessed, archive those below threshold.
2. **Strengthen phase** — Reinforce memories accessed during the current
   session (spaced repetition effect).
3. **Summarize** — Distill each session into a structured narrative.
4. **Detect patterns** — Find recurring themes across sessions and
   create semantic/procedural memories.
5. **Build associations** — Create links between thematically related
   memories (associative network).
6. **Resolve contradictions** — Merge or retire conflicting memories.
7. **Schema formation** — When 3+ episodic memories share a pattern,
   abstract into a semantic memory.
8. **Write** — Persist new ``MemoryRecord`` entries with appropriate
   emotional valence, importance, and strength.
9. **Assess quality** — Score the consolidation run.
"""

from __future__ import annotations

import json
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

_PATTERN_DETECTION_PROMPT = """\
Analyze these session summaries and identify recurring patterns, common \
strategies, and consistent preferences across sessions.

Session summaries:
{summaries}

Existing consolidated memories (for context):
{existing_memories}

Output a JSON array of detected patterns, each with:
- "pattern": string describing the pattern (1-2 sentences)
- "frequency": number of sessions exhibiting this pattern
- "confidence": float 0.0-1.0
- "memory_kind": one of "procedural", "episodic", "semantic", "meta_cognitive"
- "tags": list of relevant tags
- "importance": float 0.0-1.0

Output JSON array only:
"""

_CONTRADICTION_PROMPT = """\
Compare these new learnings against existing consolidated memories.
Identify any contradictions or superseded information.

New learnings:
{new_learnings}

Existing memories:
{existing_memories}

Output a JSON object with:
- "contradictions": list of objects, each with:
  - "new_learning": the new information
  - "existing_memory_id": ID of the conflicting existing memory
  - "resolution": "keep_new" | "keep_existing" | "merge"
  - "merged_content": string (only if resolution is "merge")

Output JSON only:
"""

_SCHEMA_FORMATION_PROMPT = """\
These episodic memories share common themes. Extract an abstract principle \
or generalised rule that captures the underlying pattern.

Episodic memories:
{episodes}

Output a JSON object with:
- "schema": string (1-2 sentences describing the abstract principle)
- "tags": list of relevant keyword tags
- "importance": float 0.0-1.0

Output JSON only:
"""

_QUALITY_PROMPT = """\
Assess the quality of this memory consolidation run.

Sessions processed: {sessions_processed}
Memories created: {memories_created}
Memories updated: {memories_updated}
Contradictions resolved: {contradictions_resolved}

New memories:
{new_memories}

Rate the consolidation quality from 0.0 to 1.0 considering:
- Relevance and usefulness of extracted memories
- Diversity of knowledge types
- Absence of redundancy

Output a single JSON object: {{"score": <float>, "reasoning": "<brief explanation>"}}
"""


# Threshold below which memories are archived during decay phase.
_DECAY_ARCHIVE_THRESHOLD = 0.10

# Minimum episodic memories with shared tags to trigger schema formation.
_SCHEMA_MIN_EPISODES = 3


class ConsolidationEngine:
    """Multi-phase LLM-powered experience consolidation with sleep-cycle.

    Args:
        llm_provider: LLM service for analysis (must implement ``complete()``).
        memory_store: Memory store for persisting consolidated memories.
        model_alias: Model alias to use for LLM calls.
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
        """Run the full sleep-cycle consolidation pipeline.

        Args:
            experiences: Session experiences to consolidate.
            existing_memories: Current consolidated memories.
            strategy: ``immediate`` (skip pattern detection) or ``batch``.

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

        # Phase 1: DECAY — apply forgetting curve to existing memories
        decayed, archived = await self._phase_decay(existing_memories)
        result.memories_retired += archived
        logger.info("consolidation.decay_phase", decayed=decayed, archived=archived)

        # Phase 2: STRENGTHEN — reinforce memories accessed in recent sessions
        strengthened = await self._phase_strengthen(experiences, existing_memories)
        logger.info("consolidation.strengthen_phase", strengthened=strengthened)

        # Phase 3: SUMMARIZE — distill each session experience
        summaries = await self._phase_summarize(experiences)
        total_tokens += sum(s.get("_tokens", 0) for s in summaries)

        # Phase 4: PATTERN DETECTION (batch only)
        patterns: list[dict[str, Any]] = []
        if strategy == "batch" and len(experiences) > 1:
            patterns = await self._phase_detect_patterns(summaries, existing_memories)
            total_tokens += sum(p.get("_tokens", 0) for p in patterns)

        # Phase 5: CONTRADICTION RESOLUTION
        new_learnings = self._collect_learnings(summaries, patterns)
        contradictions = await self._phase_resolve_contradictions(
            new_learnings, existing_memories
        )
        total_tokens += contradictions.get("_tokens", 0)

        # Phase 6: WRITE MEMORIES (with emotional valence and strength)
        created, updated, retired = await self._phase_write_memories(
            summaries=summaries,
            patterns=patterns,
            contradictions=contradictions,
            consolidation_id=result.consolidation_id,
        )
        result.memories_created = created
        result.memories_updated = updated
        result.memories_retired += retired
        result.contradictions_resolved = len(contradictions.get("contradictions", []))

        # Phase 7: ASSOCIATION BUILDING
        assoc_count = await self._phase_build_associations()
        logger.info("consolidation.associations_built", count=assoc_count)

        # Phase 8: SCHEMA FORMATION
        schema_tokens, schemas_created = await self._phase_schema_formation(
            result.consolidation_id
        )
        total_tokens += schema_tokens
        result.memories_created += schemas_created

        # Phase 9: QUALITY ASSESSMENT
        score = await self._phase_assess_quality(result)
        total_tokens += score.get("_tokens", 0)
        result.quality_score = score.get("score", 0.0)

        result.total_tokens = total_tokens
        result.ended_at = datetime.now(UTC)

        # Flush deferred memory writes in a single disk operation.
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
    # Pipeline phases
    # ------------------------------------------------------------------

    async def _phase_decay(
        self,
        existing_memories: list[MemoryRecord],
    ) -> tuple[int, int]:
        """Phase 1: Apply forgetting curve and archive weak memories."""
        now = datetime.now(UTC)
        decayed = 0
        archived = 0
        for record in existing_memories:
            eff = record.effective_strength(now)
            if eff < _DECAY_ARCHIVE_THRESHOLD:
                if "archived" not in record.tags:
                    record.tags.append("archived")
                    record.strength = eff
                    await self._memory_store.update(record)
                    archived += 1
            elif eff < record.strength * 0.9:
                record.strength = eff
                await self._memory_store.update(record)
                decayed += 1
        return decayed, archived

    async def _phase_strengthen(
        self,
        experiences: list[SessionExperience],
        existing_memories: list[MemoryRecord],
    ) -> int:
        """Phase 2: Reinforce memories referenced during recent sessions."""
        now = datetime.now(UTC)
        strengthened = 0
        # Collect tool names and mission keywords from sessions.
        session_keywords: set[str] = set()
        for exp in experiences:
            session_keywords.update(exp.mission.lower().split()[:20])
            for tc in exp.tool_calls:
                session_keywords.add(tc.tool_name.lower())
        if not session_keywords:
            return 0
        for record in existing_memories:
            if "archived" in record.tags:
                continue
            haystack = f"{record.content} {' '.join(record.tags)}".lower()
            overlap = sum(1 for kw in session_keywords if kw in haystack)
            if overlap >= 2:
                record.reinforce(now)
                await self._memory_store.update(record)
                strengthened += 1
        return strengthened

    async def _phase_summarize(
        self,
        experiences: list[SessionExperience],
    ) -> list[dict[str, Any]]:
        """Phase 3: Summarize each session experience."""
        summaries: list[dict[str, Any]] = []
        for exp in experiences:
            tool_details = "\n".join(
                f"- {tc.tool_name}: {'success' if tc.success else 'FAILED'}"
                f" ({tc.duration_ms}ms)"
                for tc in exp.tool_calls[:20]
            )
            plan_text = "\n".join(
                f"- Step {pu.get('step', '?')}: {pu.get('action', '')}"
                for pu in exp.plan_updates[:10]
            )

            prompt = _SUMMARIZE_PROMPT.format(
                mission=exp.mission[:500],
                profile=exp.profile,
                steps=exp.total_steps,
                tool_calls=len(exp.tool_calls),
                errors=len(exp.errors),
                tool_details=tool_details or "(none)",
                plan_updates=plan_text or "(none)",
                final_answer=exp.final_answer[:300] if exp.final_answer else "(none)",
            )

            parsed = await self._call_llm_json(prompt)
            parsed["session_id"] = exp.session_id
            summaries.append(parsed)

        return summaries

    async def _phase_detect_patterns(
        self,
        summaries: list[dict[str, Any]],
        existing_memories: list[MemoryRecord],
    ) -> list[dict[str, Any]]:
        """Phase 4: Detect cross-session patterns."""
        summary_text = "\n\n".join(
            f"Session {s.get('session_id', '?')}:\n{s.get('narrative', '')}"
            for s in summaries
        )
        memory_text = "\n".join(
            f"- [{m.id[:8]}] {m.content}" for m in existing_memories[:20]
        )

        prompt = _PATTERN_DETECTION_PROMPT.format(
            summaries=summary_text,
            existing_memories=memory_text or "(none)",
        )

        parsed = await self._call_llm_json(prompt)
        if isinstance(parsed, list):
            return parsed
        if "items" in parsed:
            return parsed["items"]
        return parsed.get("patterns", [])

    async def _phase_resolve_contradictions(
        self,
        new_learnings: list[str],
        existing_memories: list[MemoryRecord],
    ) -> dict[str, Any]:
        """Phase 5: Find and resolve contradictions."""
        if not new_learnings or not existing_memories:
            return {"contradictions": [], "_tokens": 0}

        learnings_text = "\n".join(f"- {item}" for item in new_learnings[:20])
        memory_text = "\n".join(
            f"- [{m.id}] {m.content}" for m in existing_memories[:20]
        )

        prompt = _CONTRADICTION_PROMPT.format(
            new_learnings=learnings_text,
            existing_memories=memory_text,
        )

        return await self._call_llm_json(prompt)

    async def _phase_write_memories(
        self,
        summaries: list[dict[str, Any]],
        patterns: list[dict[str, Any]],
        contradictions: dict[str, Any],
        consolidation_id: str,
    ) -> tuple[int, int, int]:
        """Phase 6: Create/update/retire memory records with emotional valence.

        Returns:
            Tuple of (created, updated, retired) counts.
        """
        created = 0
        updated = 0
        retired = 0

        # Handle contradictions first (update or retire existing)
        for contradiction in contradictions.get("contradictions", []):
            resolution = contradiction.get("resolution", "keep_new")
            existing_id = contradiction.get("existing_memory_id", "")

            if resolution == "keep_existing":
                continue
            elif resolution == "merge" and existing_id:
                existing = await self._memory_store.get(existing_id)
                if existing:
                    existing.content = contradiction.get(
                        "merged_content", existing.content
                    )
                    existing.metadata["last_consolidation"] = consolidation_id
                    existing.reinforce()
                    await self._memory_store.update(existing)
                    updated += 1
            elif resolution == "keep_new" and existing_id:
                existing = await self._memory_store.get(existing_id)
                if existing:
                    existing.metadata["retired_by"] = consolidation_id
                    existing.tags.append("retired")
                    existing.tags.append("archived")
                    existing.strength = 0.0
                    await self._memory_store.update(existing)
                    retired += 1

        # Create memories from summaries with emotional valence
        for summary in summaries:
            valence = self._resolve_valence(
                summary.get("emotional_valence", "neutral")
            )
            importance = min(1.0, max(0.0, summary.get("importance", 0.5)))
            for learning in summary.get("key_learnings", []):
                kind = self._resolve_memory_kind(
                    summary.get("memory_kind", "semantic")
                )
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

        # Create memories from cross-session patterns
        for pattern in patterns:
            if pattern.get("confidence", 0) < 0.5:
                continue
            kind = self._resolve_memory_kind(
                pattern.get("memory_kind", "procedural")
            )
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

        return created, updated, retired

    async def _phase_build_associations(self) -> int:
        """Phase 7: Build associations between thematically related memories.

        Scans all non-archived memories and creates bidirectional links
        between those sharing tags.
        """
        all_memories = await self._memory_store.list()
        active = [m for m in all_memories if "archived" not in m.tags]
        associations_created = 0

        for i, mem_a in enumerate(active):
            if not mem_a.tags:
                continue
            tags_a = set(mem_a.tags)
            for mem_b in active[i + 1 :]:
                if not mem_b.tags:
                    continue
                shared = tags_a & set(mem_b.tags)
                if shared and mem_b.id not in mem_a.associations:
                    mem_a.associate_with(mem_b.id)
                    mem_b.associate_with(mem_a.id)
                    associations_created += 1

        # Persist updated associations
        for mem in active:
            if mem.associations:
                await self._memory_store.update(mem)

        return associations_created

    async def _phase_schema_formation(
        self,
        consolidation_id: str,
    ) -> tuple[int, int]:
        """Phase 8: Form abstract schemas from groups of episodic memories.

        When 3+ episodic/consolidated memories share common tags, use
        the LLM to extract an abstract principle — similar to how the
        hippocampus generalises from specific episodes to form semantic
        knowledge during sleep.

        Returns:
            Tuple of (total_tokens_used, schemas_created).
        """
        all_memories = await self._memory_store.list(kind=MemoryKind.CONSOLIDATED)
        active = [m for m in all_memories if "archived" not in m.tags]

        # Group by tags
        tag_groups: dict[str, list[MemoryRecord]] = {}
        for mem in active:
            for tag in mem.tags:
                if tag in ("cross_session", "retired", "archived"):
                    continue
                tag_groups.setdefault(tag, []).append(mem)

        total_tokens = 0
        schemas_created = 0

        for tag, group in tag_groups.items():
            if len(group) < _SCHEMA_MIN_EPISODES:
                continue
            # Check if a schema for this tag already exists
            existing_schemas = [
                m
                for m in active
                if m.metadata.get("source") == "schema_formation"
                and tag in m.tags
            ]
            if existing_schemas:
                continue

            episodes_text = "\n".join(
                f"- {m.content}" for m in group[:8]
            )
            prompt = _SCHEMA_FORMATION_PROMPT.format(episodes=episodes_text)
            parsed = await self._call_llm_json(prompt)
            total_tokens += parsed.get("_tokens", 0)

            schema_text = parsed.get("schema", "")
            if not schema_text:
                continue

            importance = min(1.0, max(0.0, parsed.get("importance", 0.7)))
            schema_tags = parsed.get("tags", [tag])[:5]
            if tag not in schema_tags:
                schema_tags.append(tag)

            record = MemoryRecord(
                scope=MemoryScope.USER,
                kind=MemoryKind.CONSOLIDATED,
                content=schema_text,
                tags=schema_tags,
                metadata={
                    "source": "schema_formation",
                    "consolidation_id": consolidation_id,
                    "consolidation_kind": ConsolidatedMemoryKind.SEMANTIC.value,
                    "source_count": len(group),
                },
                importance=importance,
                emotional_valence=EmotionalValence.NEUTRAL,
            )
            await self._memory_store.add(record)
            schemas_created += 1

        return total_tokens, schemas_created

    async def _phase_assess_quality(
        self,
        result: ConsolidationResult,
    ) -> dict[str, Any]:
        """Phase 9: Assess consolidation quality."""
        if result.memories_created == 0 and result.memories_updated == 0:
            return {"score": 0.0, "reasoning": "No memories produced", "_tokens": 0}

        all_memories = await self._memory_store.list(
            scope=MemoryScope.USER, kind=MemoryKind.CONSOLIDATED
        )
        recent = [
            m
            for m in all_memories
            if m.metadata.get("consolidation_id") == result.consolidation_id
        ]
        memory_text = "\n".join(f"- {m.content}" for m in recent[:20])

        prompt = _QUALITY_PROMPT.format(
            sessions_processed=result.sessions_processed,
            memories_created=result.memories_created,
            memories_updated=result.memories_updated,
            contradictions_resolved=result.contradictions_resolved,
            new_memories=memory_text or "(none)",
        )

        return await self._call_llm_json(prompt)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _collect_learnings(
        summaries: list[dict[str, Any]],
        patterns: list[dict[str, Any]],
    ) -> list[str]:
        """Collect all new learnings for contradiction checking."""
        learnings: list[str] = []
        for s in summaries:
            learnings.extend(s.get("key_learnings", []))
        for p in patterns:
            if p.get("pattern"):
                learnings.append(p["pattern"])
        return learnings

    @staticmethod
    def _resolve_memory_kind(kind_str: str) -> ConsolidatedMemoryKind:
        """Resolve a string to a ``ConsolidatedMemoryKind`` enum value."""
        try:
            return ConsolidatedMemoryKind(kind_str)
        except ValueError:
            return ConsolidatedMemoryKind.SEMANTIC

    @staticmethod
    def _resolve_valence(valence_str: str) -> EmotionalValence:
        """Resolve a string to an ``EmotionalValence`` enum value."""
        try:
            return EmotionalValence(valence_str)
        except ValueError:
            return EmotionalValence.NEUTRAL

    async def _call_llm_json(self, prompt: str) -> dict[str, Any]:
        """Call the LLM and parse the response as JSON.

        Returns a dict on success.  On parse failure returns a dict
        with ``"_raw"`` containing the raw content.
        """
        try:
            response = await self._llm.complete(
                messages=[{"role": "user", "content": prompt}],
                model=self._model_alias,
            )
            content = response.get("content", "")
            tokens = response.get("usage", {}).get("total_tokens", 0)

            parsed = self._parse_json(content)
            if isinstance(parsed, dict):
                parsed["_tokens"] = tokens
            elif isinstance(parsed, list):
                return {"items": parsed, "_tokens": tokens}
            else:
                return {"_raw": content, "_tokens": tokens}
            return parsed

        except Exception as exc:
            logger.warning("consolidation.llm_call_failed", error=str(exc))
            return {"_error": str(exc), "_tokens": 0}

    @staticmethod
    def _parse_json(content: str) -> Any:
        """Parse JSON from LLM response, handling common formatting.

        Tries ``[`` before ``{`` when the content starts with an array
        bracket, so that ``[{"key": "value"}]`` is correctly parsed as
        a list rather than extracting the inner dict.
        """
        content = content.strip()
        pairs: list[tuple[str, str]] = [("{", "}"), ("[", "]")]
        if content.startswith("["):
            pairs = [("[", "]"), ("{", "}")]
        for start_char, end_char in pairs:
            start = content.find(start_char)
            end = content.rfind(end_char)
            if start != -1 and end != -1 and end > start:
                try:
                    return json.loads(content[start : end + 1])
                except json.JSONDecodeError:
                    continue
        return {}
