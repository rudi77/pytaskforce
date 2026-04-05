"""Protocol for generative dream engines."""

from __future__ import annotations

from typing import Protocol

from taskforce.core.domain.dream import DreamConfig, DreamCycle
from taskforce.core.domain.memory import MemoryRecord


class DreamEngineProtocol(Protocol):
    """Protocol for LLM-powered generative dreaming.

    Implementations process existing memories and produce novel
    insights through replay, recombination, emotional processing,
    and predictive simulation.
    """

    async def dream(
        self,
        memories: list[MemoryRecord],
        config: DreamConfig,
    ) -> DreamCycle:
        """Run a dream cycle on the given memories.

        Args:
            memories: Active memories to dream about.
            config: Dream configuration (phases, budget, etc.).

        Returns:
            Completed dream cycle with generated insights.
        """
        ...
