"""Protocol for memory consolidation engines."""

from __future__ import annotations

from typing import Protocol

from taskforce.core.domain.experience import ConsolidationResult, SessionExperience
from taskforce.core.domain.memory import MemoryRecord


class ConsolidationEngineProtocol(Protocol):
    """Protocol for LLM-powered experience consolidation.

    Implementations process raw session experiences and produce
    consolidated long-term memory records.
    """

    async def consolidate(
        self,
        experiences: list[SessionExperience],
        existing_memories: list[MemoryRecord],
        strategy: str = "immediate",
    ) -> ConsolidationResult:
        """Run the consolidation pipeline on a batch of experiences.

        Args:
            experiences: Session experiences to consolidate.
            existing_memories: Current consolidated memories for deduplication.
            strategy: Consolidation strategy (``immediate`` or ``batch``).

        Returns:
            Result with counts of created, updated, and retired memories.
        """
        ...
