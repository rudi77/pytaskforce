"""LLM-powered memory consolidation engine.

Processes raw session experiences through a multi-phase pipeline to
produce high-quality consolidated long-term memories.  The pipeline
mirrors how human memory consolidation works during sleep:

1. **Summarize** each session experience into a structured narrative.
2. **Detect patterns** across sessions (batch mode only).
3. **Resolve contradictions** against existing consolidated memories.
4. **Write** new ``MemoryRecord`` entries (kind=CONSOLIDATED).
5. **Assess quality** of the consolidation run.
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
from taskforce.core.domain.memory import MemoryKind, MemoryRecord, MemoryScope
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


class ConsolidationEngine:
    """Multi-phase LLM-powered experience consolidation.

    Args:
        llm_provider: LLM service for analysis (must implement ``complete()``).
        memory_store: Memory store for persisting consolidated memories.
        model_alias: Model alias to use for LLM calls.
    """

    def __init__(
        self,
        llm_provider: Any,
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
        """Run the consolidation pipeline.

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

        # Phase 1: Summarize each experience
        summaries = await self._phase_summarize(experiences)
        total_tokens += sum(s.get("_tokens", 0) for s in summaries)

        # Phase 2: Cross-session pattern detection (batch only)
        patterns: list[dict[str, Any]] = []
        if strategy == "batch" and len(experiences) > 1:
            patterns = await self._phase_detect_patterns(summaries, existing_memories)
            total_tokens += sum(p.get("_tokens", 0) for p in patterns)

        # Phase 3: Contradiction resolution
        new_learnings = self._collect_learnings(summaries, patterns)
        contradictions = await self._phase_resolve_contradictions(new_learnings, existing_memories)
        total_tokens += contradictions.get("_tokens", 0)

        # Phase 4: Write memories
        created, updated, retired = await self._phase_write_memories(
            summaries=summaries,
            patterns=patterns,
            contradictions=contradictions,
            consolidation_id=result.consolidation_id,
        )
        result.memories_created = created
        result.memories_updated = updated
        result.memories_retired = retired
        result.contradictions_resolved = len(contradictions.get("contradictions", []))

        # Phase 5: Quality assessment
        score = await self._phase_assess_quality(result)
        total_tokens += score.get("_tokens", 0)
        result.quality_score = score.get("score", 0.0)

        result.total_tokens = total_tokens
        result.ended_at = datetime.now(UTC)

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

    async def _phase_summarize(self, experiences: list[SessionExperience]) -> list[dict[str, Any]]:
        """Phase 1: Summarize each session experience."""
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
        """Phase 2: Detect cross-session patterns."""
        summary_text = "\n\n".join(
            f"Session {s.get('session_id', '?')}:\n{s.get('narrative', '')}" for s in summaries
        )
        memory_text = "\n".join(f"- [{m.id[:8]}] {m.content}" for m in existing_memories[:20])

        prompt = _PATTERN_DETECTION_PROMPT.format(
            summaries=summary_text,
            existing_memories=memory_text or "(none)",
        )

        parsed = await self._call_llm_json(prompt)
        if isinstance(parsed, list):
            return parsed
        # _call_llm_json wraps raw arrays under "items"
        if "items" in parsed:
            return parsed["items"]
        return parsed.get("patterns", [])

    async def _phase_resolve_contradictions(
        self,
        new_learnings: list[str],
        existing_memories: list[MemoryRecord],
    ) -> dict[str, Any]:
        """Phase 3: Find and resolve contradictions."""
        if not new_learnings or not existing_memories:
            return {"contradictions": [], "_tokens": 0}

        learnings_text = "\n".join(f"- {item}" for item in new_learnings[:20])
        memory_text = "\n".join(f"- [{m.id}] {m.content}" for m in existing_memories[:20])

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
        """Phase 4: Create/update/retire memory records.

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
                    existing.content = contradiction.get("merged_content", existing.content)
                    existing.metadata["last_consolidation"] = consolidation_id
                    await self._memory_store.update(existing)
                    updated += 1
            elif resolution == "keep_new" and existing_id:
                existing = await self._memory_store.get(existing_id)
                if existing:
                    existing.metadata["retired_by"] = consolidation_id
                    existing.tags.append("retired")
                    await self._memory_store.update(existing)
                    retired += 1

        # Create memories from summaries
        for summary in summaries:
            for learning in summary.get("key_learnings", []):
                kind = self._resolve_memory_kind(summary.get("memory_kind", "semantic"))
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
                )
                await self._memory_store.add(record)
                created += 1

        # Create memories from cross-session patterns
        for pattern in patterns:
            if pattern.get("confidence", 0) < 0.5:
                continue
            kind = self._resolve_memory_kind(pattern.get("memory_kind", "procedural"))
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
            )
            await self._memory_store.add(record)
            created += 1

        return created, updated, retired

    async def _phase_assess_quality(self, result: ConsolidationResult) -> dict[str, Any]:
        """Phase 5: Assess consolidation quality."""
        if result.memories_created == 0 and result.memories_updated == 0:
            return {"score": 0.0, "reasoning": "No memories produced", "_tokens": 0}

        # Retrieve newly created memories for review
        all_memories = await self._memory_store.list(
            scope=MemoryScope.USER, kind=MemoryKind.CONSOLIDATED
        )
        recent = [
            m for m in all_memories if m.metadata.get("consolidation_id") == result.consolidation_id
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

    async def _call_llm_json(self, prompt: str) -> dict[str, Any]:
        """Call the LLM and parse the response as JSON.

        Returns a dict on success.  On parse failure returns a dict
        with ``"_raw"`` containing the raw content.
        """
        try:
            response = await self._llm.complete(
                messages=[{"role": "user", "content": prompt}],
                model_alias=self._model_alias,
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
        # Prefer array when content starts with "[" to avoid extracting inner dicts
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
