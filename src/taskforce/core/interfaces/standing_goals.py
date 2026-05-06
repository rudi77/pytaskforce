"""Protocol for standing-goal storage."""

from __future__ import annotations

from datetime import datetime
from typing import Protocol

from taskforce.core.domain.standing_goal import StandingGoal


class StandingGoalStoreProtocol(Protocol):
    """Persistent storage for :class:`StandingGoal` records.

    All methods are async to match the existing persistence protocols
    (``StateManagerProtocol``, ``ConversationStoreProtocol``); a
    sync file-based implementation just wraps the I/O in
    ``asyncio.to_thread`` if it ever becomes contention-prone.
    """

    async def list(self) -> list[StandingGoal]:
        """Return every stored standing goal (enabled and disabled)."""
        ...

    async def get(self, goal_id: str) -> StandingGoal | None:
        """Return the goal for ``goal_id`` or ``None``."""
        ...

    async def add(self, goal: StandingGoal) -> StandingGoal:
        """Persist a new goal and return it (with ``goal_id`` populated)."""
        ...

    async def update(self, goal: StandingGoal) -> StandingGoal:
        """Replace the stored goal that shares ``goal_id``."""
        ...

    async def delete(self, goal_id: str) -> bool:
        """Remove the goal; return ``True`` if it existed, ``False`` otherwise."""
        ...

    async def mark_evaluated(
        self,
        goal_id: str,
        evaluated_at: datetime,
        action_taken: str,
    ) -> None:
        """Record an evaluation outcome on the stored goal.

        Implementations must be safe to call concurrently for different
        ``goal_id``s — the file store serializes writes through a lock.
        """
        ...
