"""Dream service — application-layer orchestration for generative dreaming.

Coordinates the dream lifecycle: loading memories, running the dream
engine, persisting insights as new memories, and saving dream history.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import structlog

from taskforce.core.domain.dream import (
    DreamConfig,
    DreamCycle,
    DreamInsight,
    DreamStatus,
    DreamTrigger,
)
from taskforce.core.domain.memory import MemoryKind, MemoryRecord, MemoryScope
from taskforce.core.interfaces.dreaming import DreamEngineProtocol
from taskforce.core.interfaces.memory_store import MemoryStoreProtocol

logger = structlog.get_logger(__name__)


class DreamService:
    """Orchestrates dream cycles and persists results.

    Args:
        dream_engine: The dream engine implementation.
        memory_store: Memory store for reading/writing memories.
        config: Default dream configuration.
        work_dir: Base directory for dream history persistence.
    """

    def __init__(
        self,
        dream_engine: DreamEngineProtocol,
        memory_store: MemoryStoreProtocol,
        config: DreamConfig | None = None,
        work_dir: str = ".taskforce",
    ) -> None:
        self._engine = dream_engine
        self._memory_store = memory_store
        self._config = config or DreamConfig()
        self._dreams_dir = Path(work_dir) / "dreams"

    async def trigger_dream(
        self,
        config: DreamConfig | None = None,
        trigger: DreamTrigger = DreamTrigger.MANUAL,
    ) -> DreamCycle:
        """Run a dream cycle.

        Args:
            config: Override config for this cycle (uses default if None).
            trigger: What triggered this dream cycle.

        Returns:
            Completed dream cycle with insights.
        """
        cfg = config or self._config
        logger.info("dream.cycle_starting", trigger=trigger.value)

        # Load active memories
        all_memories = await self._memory_store.list()
        decay_enabled = bool(getattr(self._memory_store, "decay_enabled", False))
        active = [
            m
            for m in all_memories
            if "archived" not in m.tags and m.effective_strength(decay_enabled=decay_enabled) > 0.15
        ]

        if not active:
            logger.info("dream.no_active_memories")
            return DreamCycle(
                status=DreamStatus.COMPLETED,
                ended_at=datetime.now(UTC),
                trigger=trigger,
            )

        # Run dream engine
        cycle = await self._engine.dream(active, cfg)
        cycle.trigger = trigger

        # Persist high-quality insights as new memories
        if cfg.enabled:
            cycle.memories_created = await self._persist_insights(cycle.insights)

        # Flush memory store
        if hasattr(self._memory_store, "flush"):
            await self._memory_store.flush()

        # Save dream cycle to disk
        await self._save_cycle(cycle)

        logger.info(
            "dream.cycle_completed",
            dream_id=cycle.dream_id,
            insights=len(cycle.insights),
            memories_created=cycle.memories_created,
            tokens=cycle.total_tokens,
        )
        return cycle

    async def get_dream_history(self, limit: int = 10) -> list[DreamCycle]:
        """Retrieve past dream cycles, most recent first.

        Args:
            limit: Maximum number of cycles to return.

        Returns:
            List of dream cycles sorted by start time descending.
        """
        if not self._dreams_dir.exists():
            return []

        cycles: list[DreamCycle] = []
        files = sorted(self._dreams_dir.glob("*.json"), reverse=True)
        for path in files[:limit]:
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                cycles.append(DreamCycle.from_dict(data))
            except (json.JSONDecodeError, KeyError, ValueError) as exc:
                logger.warning("dream.load_failed", path=str(path), error=str(exc))
        return cycles

    async def get_dream(self, dream_id: str) -> DreamCycle | None:
        """Retrieve a specific dream cycle by ID.

        Args:
            dream_id: The dream cycle identifier.

        Returns:
            The dream cycle, or None if not found.
        """
        path = self._dreams_dir / f"{dream_id}.json"
        if not path.exists():
            return None
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            return DreamCycle.from_dict(data)
        except (json.JSONDecodeError, KeyError, ValueError):
            return None

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _persist_insights(self, insights: list[DreamInsight]) -> int:
        """Convert dream insights into consolidated memory records.

        Returns:
            Number of memories created.
        """
        created = 0
        for insight in insights:
            record = MemoryRecord(
                scope=MemoryScope.USER,
                kind=MemoryKind.CONSOLIDATED,
                content=insight.content,
                tags=insight.tags + ["dreaming"],
                metadata={
                    "source": "dreaming",
                    "insight_type": insight.insight_type.value,
                    "source_memory_ids": insight.source_memory_ids,
                    "confidence": insight.confidence,
                    "novelty_score": insight.novelty_score,
                },
                emotional_valence=insight.emotional_valence,
                importance=insight.confidence,
            )
            await self._memory_store.add(record)
            created += 1
        return created

    async def _save_cycle(self, cycle: DreamCycle) -> None:
        """Persist dream cycle to disk as JSON."""
        self._dreams_dir.mkdir(parents=True, exist_ok=True)
        path = self._dreams_dir / f"{cycle.dream_id}.json"
        path.write_text(
            json.dumps(cycle.to_dict(), indent=2, ensure_ascii=False),
            encoding="utf-8",
        )


def build_dream_components(
    config: dict[str, Any],
    llm_provider: Any = None,
    memory_store: Any = None,
) -> DreamService | None:
    """Build dream service from profile configuration.

    Args:
        config: Full profile configuration dict.
        llm_provider: LLM provider (``LLMProviderProtocol``).
        memory_store: Memory store (``MemoryStoreProtocol``).

    Returns:
        Configured ``DreamService``, or ``None`` if dreaming is disabled
        or dependencies are missing.
    """
    dream_config_raw = config.get("dreaming", {})
    if not dream_config_raw.get("enabled", False):
        return None

    if not llm_provider or not memory_store:
        logger.warning("dream.missing_dependencies")
        return None

    from taskforce.infrastructure.memory.dream_engine import DreamEngine

    dream_config = DreamConfig.from_dict(dream_config_raw)
    engine = DreamEngine(llm_provider=llm_provider, memory_store=memory_store)
    work_dir = config.get("persistence", {}).get("work_dir", ".taskforce")

    return DreamService(
        dream_engine=engine,
        memory_store=memory_store,
        config=dream_config,
        work_dir=work_dir,
    )
