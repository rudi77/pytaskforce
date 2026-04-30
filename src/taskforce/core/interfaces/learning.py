"""Protocol for post-mission learning.

A LearningStrategy inspects a finished agent run and decides whether
any reusable knowledge (working sources, recurring entities, workflow
hints) should be added to the long-term wiki. It is intentionally
side-effect-free in its return value — the strategy does its own
wiki writes via the injected store and returns only diagnostics.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol


@dataclass(frozen=True)
class LearningResult:
    """Diagnostic summary of one learning pass."""

    extracted_count: int
    pages_written: list[str]
    skipped_reason: str | None = None


class LearningStrategyProtocol(Protocol):
    """Extracts reusable knowledge from a completed mission."""

    async def learn_from_mission(
        self,
        mission: str,
        messages: list[dict[str, Any]],
        session_id: str,
    ) -> LearningResult:
        """Inspect a finished mission and persist any reusable facts.

        Args:
            mission: The original mission text the user gave.
            messages: Final chat-style message list (system + user +
                assistant + tool messages) at mission completion.
            session_id: Session identifier (for logging / dedup).

        Returns:
            A LearningResult describing what was written. Implementations
            should never raise — they swallow LLM/store errors and report
            them via ``skipped_reason``.
        """
        ...
