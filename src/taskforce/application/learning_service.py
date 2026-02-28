"""Learning service for automatic knowledge extraction from conversations.

Analyzes completed agent conversations to extract facts, preferences,
and decisions, storing them as long-term memory records.
"""

from __future__ import annotations

import json
from typing import Any

import structlog

from taskforce.core.domain.memory import MemoryKind, MemoryRecord, MemoryScope
from taskforce.core.interfaces.memory_store import MemoryStoreProtocol
from taskforce.core.utils.time import utc_now

logger = structlog.get_logger(__name__)

_EXTRACTION_PROMPT = """\
Analyze the following conversation and extract important facts, user preferences, \
and decisions that should be remembered for future interactions.

For each piece of knowledge, output a JSON array of objects with these fields:
- "kind": either "preference" (user preference/habit) or "learned_fact" (factual knowledge)
- "content": the knowledge to remember (1-2 sentences, clear and concise)
- "tags": list of relevant tags for retrieval

Only extract genuinely useful knowledge. Skip trivial or temporary information.
If there is nothing worth remembering, return an empty array: []

Conversation:
{conversation}

Output (JSON array only, no other text):
"""


class LearningService:
    """Extracts and manages learned knowledge from agent conversations.

    Uses the LLM to analyze conversations and extract knowledge,
    then stores it in the memory system.
    """

    def __init__(
        self,
        memory_store: MemoryStoreProtocol,
        llm_provider: Any = None,
        model_alias: str = "main",
        auto_extract: bool = True,
        user_scope: str = "user",
        consolidation_service: Any = None,
    ) -> None:
        self._memory_store = memory_store
        self._llm_provider = llm_provider
        self._model_alias = model_alias
        self._auto_extract = auto_extract
        self._user_scope = user_scope
        self._consolidation_service = consolidation_service

    @property
    def auto_extract(self) -> bool:
        """Whether automatic extraction is enabled."""
        return self._auto_extract

    async def extract_learnings(
        self,
        conversation: list[dict[str, Any]],
        session_context: dict[str, Any],
    ) -> list[MemoryRecord]:
        """Extract facts and preferences from a conversation.

        Args:
            conversation: The message history to analyze.
            session_context: Context (profile, user_id, session_id, etc.).

        Returns:
            List of new MemoryRecords created from the extraction.
        """
        if not self._auto_extract or not self._llm_provider:
            return []

        if len(conversation) < 2:
            return []

        try:
            conv_text = self._format_conversation(conversation)
            prompt = _EXTRACTION_PROMPT.format(conversation=conv_text)

            response = await self._llm_provider.complete(
                messages=[{"role": "user", "content": prompt}],
                model_alias=self._model_alias,
            )

            content = response.get("content", "[]")
            items = self._parse_extraction(content)

            records: list[MemoryRecord] = []
            for item in items:
                kind_str = item.get("kind", "learned_fact")
                try:
                    kind = MemoryKind(kind_str)
                except ValueError:
                    kind = MemoryKind.LEARNED_FACT

                record = MemoryRecord(
                    scope=MemoryScope(self._user_scope),
                    kind=kind,
                    content=item.get("content", ""),
                    tags=item.get("tags", []),
                    metadata={
                        "source": "auto_extraction",
                        "session_id": session_context.get("session_id", ""),
                        "profile": session_context.get("profile", ""),
                    },
                )
                saved = await self._memory_store.add(record)
                records.append(saved)

            if records:
                logger.info(
                    "learning_service.extracted",
                    count=len(records),
                    session_id=session_context.get("session_id", ""),
                )

            return records

        except Exception as exc:
            logger.warning("learning_service.extraction_failed", error=str(exc))
            return []

    async def enrich_context(
        self,
        mission: str,
        user_id: str,
    ) -> list[MemoryRecord]:
        """Retrieve relevant memories for the current mission.

        Searches long-term memory for records that might be relevant
        to the current task.

        Args:
            mission: The mission description.
            user_id: The user making the request.

        Returns:
            List of relevant MemoryRecords.
        """
        # Search across preferences and learned facts
        results: list[MemoryRecord] = []

        # Search by mission keywords
        keywords = self._extract_keywords(mission)
        for keyword in keywords[:5]:
            matches = await self._memory_store.search(
                query=keyword,
                scope=MemoryScope.USER,
                limit=3,
            )
            for match in matches:
                if match.id not in {r.id for r in results}:
                    results.append(match)

        # Also get recent preferences
        prefs = await self._memory_store.list(
            scope=MemoryScope.USER,
            kind=MemoryKind.PREFERENCE,
        )
        for pref in prefs[:5]:
            if pref.id not in {r.id for r in results}:
                results.append(pref)

        return results[:10]

    async def compact_memories(
        self,
        scope: MemoryScope,
        max_age_days: int,
    ) -> int:
        """Compact old memories by summarizing related groups.

        Args:
            scope: Memory scope to compact.
            max_age_days: Records older than this are candidates.

        Returns:
            Number of records processed.
        """
        if not self._llm_provider:
            return 0

        from datetime import timedelta

        cutoff = utc_now() - timedelta(days=max_age_days)
        all_records = await self._memory_store.list(scope=scope)

        # Find old records
        old_records = [r for r in all_records if r.updated_at < cutoff]
        if len(old_records) < 3:
            return 0

        # Group by kind
        groups: dict[str, list[MemoryRecord]] = {}
        for record in old_records:
            groups.setdefault(record.kind.value, []).append(record)

        processed = 0
        for kind_str, records in groups.items():
            if len(records) < 2:
                continue

            # Summarize the group
            content_block = "\n".join(f"- {r.content}" for r in records)
            summary_prompt = (
                f"Summarize these related memory entries into 1-3 concise entries:\n\n"
                f"{content_block}\n\n"
                f"Output a JSON array of objects with 'content' and 'tags' fields."
            )

            try:
                response = await self._llm_provider.complete(
                    messages=[{"role": "user", "content": summary_prompt}],
                    model_alias=self._model_alias,
                )
                items = self._parse_extraction(response.get("content", "[]"))

                # Delete old records and create summaries
                for record in records:
                    await self._memory_store.delete(record.id)

                for item in items:
                    try:
                        kind = MemoryKind(kind_str)
                    except ValueError:
                        kind = MemoryKind.LEARNED_FACT
                    summary_record = MemoryRecord(
                        scope=scope,
                        kind=kind,
                        content=item.get("content", ""),
                        tags=item.get("tags", []) + ["compacted"],
                        metadata={"source": "compaction"},
                    )
                    await self._memory_store.add(summary_record)

                processed += len(records)
            except Exception as exc:
                logger.warning(
                    "learning_service.compaction_failed",
                    kind=kind_str,
                    error=str(exc),
                )

        if processed:
            logger.info("learning_service.compacted", count=processed, scope=scope.value)

        return processed

    def _format_conversation(self, conversation: list[dict[str, Any]]) -> str:
        """Format conversation messages for the extraction prompt."""
        lines: list[str] = []
        for msg in conversation[-20:]:  # Last 20 messages max
            role = msg.get("role", "unknown")
            content = msg.get("content", "")
            if isinstance(content, str) and content.strip():
                lines.append(f"{role}: {content[:500]}")
        return "\n".join(lines)

    def _parse_extraction(self, content: str) -> list[dict[str, Any]]:
        """Parse the LLM's extraction response as JSON."""
        content = content.strip()
        # Find JSON array in the response
        start = content.find("[")
        end = content.rfind("]")
        if start == -1 or end == -1:
            return []
        try:
            return json.loads(content[start : end + 1])
        except json.JSONDecodeError:
            return []

    def _extract_keywords(self, text: str) -> list[str]:
        """Extract simple keywords from text for memory search."""
        stop_words = {
            "the",
            "a",
            "an",
            "is",
            "are",
            "was",
            "were",
            "be",
            "been",
            "being",
            "have",
            "has",
            "had",
            "do",
            "does",
            "did",
            "will",
            "would",
            "could",
            "should",
            "may",
            "might",
            "can",
            "shall",
            "to",
            "of",
            "in",
            "for",
            "on",
            "with",
            "at",
            "by",
            "from",
            "as",
            "into",
            "through",
            "during",
            "before",
            "after",
            "and",
            "but",
            "or",
            "nor",
            "not",
            "so",
            "yet",
            "both",
            "either",
            "neither",
            "each",
            "every",
            "all",
            "any",
            "few",
            "more",
            "most",
            "other",
            "some",
            "such",
            "no",
            "only",
            "own",
            "same",
            "than",
            "too",
            "very",
            "just",
            "because",
            "if",
            "when",
            "while",
            "ich",
            "du",
            "er",
            "sie",
            "es",
            "wir",
            "ihr",
            "und",
            "oder",
            "aber",
            "nicht",
            "ein",
            "eine",
            "der",
            "die",
            "das",
            "mit",
            "von",
            "zu",
            "auf",
            "für",
            "über",
            "nach",
        }

        words = text.lower().split()
        keywords = [w for w in words if len(w) > 2 and w not in stop_words]
        return keywords[:10]

    async def consolidate_experiences(
        self,
        session_ids: list[str] | None = None,
        strategy: str = "batch",
    ) -> Any:
        """Consolidate session experiences into long-term memories.

        Delegates to the ``ConsolidationService`` if configured.

        Args:
            session_ids: Specific sessions to consolidate. If ``None``,
                processes all unprocessed experiences.
            strategy: Consolidation strategy (``immediate`` or ``batch``).

        Returns:
            ``ConsolidationResult`` if consolidation service is available,
            ``None`` otherwise.
        """
        if self._consolidation_service is None:
            logger.info("learning_service.no_consolidation_service")
            return None

        return await self._consolidation_service.trigger_consolidation(
            session_ids=session_ids,
            strategy=strategy,
        )
