"""Protocol for SLM-based context enrichment.

A context enricher generates associative, generative context from existing
memories before the ReAct loop starts.  Unlike keyword/semantic retrieval,
the enricher *produces* novel associations — factual, behavioral, and
dreamed optimizations — via a small language model (SLM).
"""

from __future__ import annotations

from typing import Any, Protocol

from taskforce.core.domain.memory import MemoryRecord


class ContextEnricherProtocol(Protocol):
    """Protocol for generative pre-ReAct context enrichment.

    Implementations call a (typically small/local) language model to
    synthesise a concise intuition block from relevant memories and the
    current mission, which is then injected into the agent's system prompt.
    """

    async def enrich(
        self,
        mission: str,
        memories: list[MemoryRecord],
        session_context: dict[str, Any] | None = None,
    ) -> str | None:
        """Generate associative context for the current mission.

        Args:
            mission: The current mission / user query.
            memories: Relevant long-term memories already retrieved.
            session_context: Optional session metadata (profile, user_id, …).

        Returns:
            A formatted prompt section to inject into the system prompt,
            or ``None`` when enrichment is not applicable.
        """
        ...
