"""Learning Strategy Protocol for automatic knowledge extraction.

Defines the contract for components that extract facts, preferences,
and decisions from conversations and manage long-term memory compaction.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from taskforce.core.domain.memory import MemoryRecord, MemoryScope


class LearningStrategyProtocol(Protocol):
    """Protocol for automatic knowledge extraction and memory management.

    The learning strategy runs after agent executions to extract
    facts, preferences, and decisions, storing them as long-term memories.
    """

    async def extract_learnings(
        self,
        conversation: list[dict],
        session_context: dict,
    ) -> list[MemoryRecord]:
        """Extract facts, preferences, and decisions from a conversation.

        Called after each agent execution to mine the conversation for
        valuable knowledge to store in long-term memory.

        Args:
            conversation: The message history of the completed execution.
            session_context: Context about the session (profile, user_id, etc.).

        Returns:
            List of new MemoryRecords extracted from the conversation.
        """
        ...

    async def enrich_context(
        self,
        mission: str,
        user_id: str,
    ) -> list[MemoryRecord]:
        """Retrieve relevant memories for the current mission context.

        Called before agent execution to find memories that might be
        relevant to the current task.

        Args:
            mission: The mission description.
            user_id: The user making the request.

        Returns:
            List of relevant MemoryRecords to inject as context.
        """
        ...

    async def compact_memories(
        self,
        scope: MemoryScope,
        max_age_days: int,
    ) -> int:
        """Summarize and archive old memories.

        Compacts old, infrequently accessed memories by summarizing
        groups of related records into single consolidated records.

        Args:
            scope: Memory scope to compact.
            max_age_days: Records older than this are candidates for compaction.

        Returns:
            Number of records processed (compacted or archived).
        """
        ...
