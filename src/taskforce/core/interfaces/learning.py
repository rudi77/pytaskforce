"""Protocol for automatic knowledge extraction and memory management."""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from taskforce.core.domain.memory import MemoryRecord, MemoryScope


class LearningStrategyProtocol(Protocol):
    """Protocol for automatic knowledge extraction and memory management.

    Implementations analyze agent conversations to extract facts, preferences,
    and decisions, and manage the long-term memory lifecycle.
    """

    async def extract_learnings(
        self,
        conversation: list[dict],
        session_context: dict,
    ) -> list[MemoryRecord]:
        """Extract facts, preferences, and decisions from a conversation."""
        ...

    async def enrich_context(
        self,
        mission: str,
        user_id: str,
    ) -> list[MemoryRecord]:
        """Retrieve relevant memories for the current mission context."""
        ...

    async def compact_memories(
        self,
        scope: MemoryScope,
        max_age_days: int,
    ) -> int:
        """Summarize and archive old memories. Returns records processed."""
        ...
