"""Application service for memory consolidation orchestration.

Coordinates the experience store, consolidation engine, and memory store
to manage the full consolidation lifecycle.
"""

from __future__ import annotations

from typing import Any

import structlog

from taskforce.core.domain.enums import ConsolidationStrategy
from taskforce.core.domain.experience import ConsolidationResult, SessionExperience
from taskforce.core.domain.memory import MemoryKind, MemoryScope
from taskforce.core.interfaces.consolidation import ConsolidationEngineProtocol
from taskforce.core.interfaces.experience import ExperienceStoreProtocol
from taskforce.core.interfaces.memory_store import MemoryStoreProtocol

logger = structlog.get_logger(__name__)


def build_consolidation_components(
    config: dict[str, Any],
    llm_provider: Any = None,
) -> tuple[Any, ConsolidationService | None]:
    """Build experience tracker and consolidation service from profile config.

    Args:
        config: Profile configuration dict (may contain ``consolidation`` section).
        llm_provider: LLM provider for the consolidation engine.

    Returns:
        Tuple of ``(experience_tracker, consolidation_service)`` — both may
        be ``None`` if consolidation is not enabled.
    """
    consol_config = config.get("consolidation", {})
    if not consol_config.get("enabled", False):
        return None, None

    from taskforce.infrastructure.memory.consolidation_engine import ConsolidationEngine
    from taskforce.infrastructure.memory.experience_tracker import ExperienceTracker
    from taskforce.infrastructure.memory.file_experience_store import FileExperienceStore
    from taskforce.infrastructure.memory.file_memory_store import FileMemoryStore

    work_dir = consol_config.get("work_dir", ".taskforce/experiences")
    memory_dir = config.get("persistence", {}).get("work_dir", ".taskforce")

    experience_store = FileExperienceStore(work_dir)
    memory_store = FileMemoryStore(memory_dir)
    tracker = ExperienceTracker(experience_store)

    engine: Any = None
    service: ConsolidationService | None = None

    if llm_provider is not None:
        engine = ConsolidationEngine(
            llm_provider=llm_provider,
            memory_store=memory_store,
            model_alias=consol_config.get("model_alias", "main"),
        )
        service = ConsolidationService(
            experience_store=experience_store,
            consolidation_engine=engine,
            memory_store=memory_store,
            auto_consolidate=consol_config.get("auto_consolidate", False),
            strategy=consol_config.get("strategy", "immediate"),
        )

    return tracker, service


class ConsolidationService:
    """Orchestrates the memory consolidation lifecycle.

    Args:
        experience_store: Persistence for raw session experiences.
        consolidation_engine: LLM-powered consolidation pipeline.
        memory_store: Target store for consolidated memories.
        auto_consolidate: Trigger consolidation after each session.
        strategy: Default consolidation strategy.
    """

    def __init__(
        self,
        experience_store: ExperienceStoreProtocol,
        consolidation_engine: ConsolidationEngineProtocol,
        memory_store: MemoryStoreProtocol,
        auto_consolidate: bool = False,
        strategy: str = "immediate",
    ) -> None:
        self._experience_store = experience_store
        self._engine = consolidation_engine
        self._memory_store = memory_store
        self._auto_consolidate = auto_consolidate
        self._default_strategy = strategy

    async def trigger_consolidation(
        self,
        session_ids: list[str] | None = None,
        strategy: str | None = None,
        max_sessions: int = 20,
    ) -> ConsolidationResult:
        """Run a consolidation pass over session experiences.

        Args:
            session_ids: Specific sessions to consolidate. If ``None``,
                uses unprocessed experiences.
            strategy: Override the default strategy.
            max_sessions: Maximum number of sessions to process.

        Returns:
            Result with consolidation metrics.
        """
        effective_strategy = strategy or self._default_strategy

        # Gather experiences
        if session_ids:
            experiences: list[SessionExperience] = []
            for sid in session_ids[:max_sessions]:
                exp = await self._experience_store.load_experience(sid)
                if exp:
                    experiences.append(exp)
        else:
            experiences = await self._experience_store.list_experiences(
                limit=max_sessions, unprocessed_only=True
            )

        if not experiences:
            logger.info("consolidation.no_experiences")
            return ConsolidationResult(strategy=effective_strategy)

        # Fetch existing consolidated memories for dedup/contradiction check
        existing = await self._memory_store.list(
            scope=MemoryScope.USER, kind=MemoryKind.CONSOLIDATED
        )

        logger.info(
            "consolidation.starting",
            strategy=effective_strategy,
            sessions=len(experiences),
            existing_memories=len(existing),
        )

        result = await self._engine.consolidate(
            experiences=experiences,
            existing_memories=existing,
            strategy=effective_strategy,
        )

        # Mark processed
        processed_ids = [e.session_id for e in experiences]
        await self._experience_store.mark_processed(processed_ids, result.consolidation_id)

        # Persist consolidation result if store supports it
        store = self._experience_store
        if hasattr(store, "save_consolidation"):
            await store.save_consolidation(result)

        return result

    async def post_execution_hook(
        self,
        session_id: str,
        experience: SessionExperience,
    ) -> None:
        """Called after each agent execution when auto_consolidate is enabled.

        Triggers an immediate single-session consolidation.

        Args:
            session_id: The completed session ID.
            experience: The session experience to consolidate.
        """
        if not self._auto_consolidate:
            return

        try:
            await self.trigger_consolidation(
                session_ids=[session_id],
                strategy=ConsolidationStrategy.IMMEDIATE.value,
                max_sessions=1,
            )
        except Exception:
            logger.exception(
                "consolidation.post_execution_failed",
                session_id=session_id,
            )

    async def get_consolidation_history(self, limit: int = 10) -> list[ConsolidationResult]:
        """Retrieve past consolidation run results.

        Args:
            limit: Maximum number of results to return.

        Returns:
            List of consolidation results, most recent first.
        """
        store = self._experience_store
        if hasattr(store, "list_consolidations"):
            return await store.list_consolidations(limit)
        return []
