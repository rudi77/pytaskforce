"""Standing goal domain model — proactive long-running objectives.

A standing goal is a self-managed, recurring intention the agent should
evaluate on its own schedule (e.g. *"every Monday 9am, prepare a
weekly summary of last week's coding work"*).

Periodic evaluation is performed by
:class:`taskforce.application.goal_evaluator_service.GoalEvaluatorService`,
which runs on a heartbeat tick scheduled through the ordinary
``SchedulerService``. The evaluator asks the LLM whether to act now,
and if so submits a mission to the ``PersistentAgentService`` queue
just like an external trigger would.

This file is pure domain — no I/O, no LLM, no storage. The
``StandingGoalStoreProtocol`` lives in
``core/interfaces/standing_goals.py``; the file-backed implementation
in ``infrastructure/persistence/file_standing_goal_store.py``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any
from uuid import uuid4


@dataclass
class StandingGoal:
    """A proactive, recurring intention the agent should pursue.

    Attributes:
        goal_id: Stable identifier; auto-generated UUID hex when omitted.
        description: Short human-readable description (shown by
            ``taskforce goals list`` and used in the LLM prompt).
        evaluation_prompt: The instruction sent to the LLM on every
            evaluation tick. Should describe what to look at and what
            to ask. ``$NOW``/``$LAST_EVALUATED_AT`` substitution is
            performed by the evaluator before sending.
        frequency: Cron expression in the same 5-field format the
            ``SchedulerService`` accepts (``"0 9 * * 1"`` = Mondays at 9).
            The evaluator filters due goals using this expression
            before any LLM call so cost stays bounded.
        priority: Mission priority forwarded to the ``RequestQueue`` —
            lower values run first.
        enabled: When ``False`` the evaluator skips this goal entirely
            (toggle without losing the configuration).
        last_evaluated_at: Updated by the evaluator on every tick that
            considered this goal. ``None`` means "never evaluated".
        last_action_taken: Free-text summary of the last action the
            evaluator submitted on this goal's behalf, or empty string
            when the LLM decided no action was warranted.
        metadata: Arbitrary user-defined context (tags, links).
    """

    description: str
    evaluation_prompt: str
    frequency: str
    goal_id: str = field(default_factory=lambda: uuid4().hex)
    priority: int = 5
    enabled: bool = True
    last_evaluated_at: datetime | None = None
    last_action_taken: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a JSON-friendly dict for the file store."""
        return {
            "goal_id": self.goal_id,
            "description": self.description,
            "evaluation_prompt": self.evaluation_prompt,
            "frequency": self.frequency,
            "priority": self.priority,
            "enabled": self.enabled,
            "last_evaluated_at": (
                self.last_evaluated_at.isoformat() if self.last_evaluated_at else None
            ),
            "last_action_taken": self.last_action_taken,
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> StandingGoal:
        """Inverse of :meth:`to_dict`. Tolerates missing optional fields."""
        last = data.get("last_evaluated_at")
        last_dt = datetime.fromisoformat(last) if last else None
        return cls(
            description=data["description"],
            evaluation_prompt=data["evaluation_prompt"],
            frequency=data["frequency"],
            goal_id=data.get("goal_id") or uuid4().hex,
            priority=int(data.get("priority", 5)),
            enabled=bool(data.get("enabled", True)),
            last_evaluated_at=last_dt,
            last_action_taken=data.get("last_action_taken", ""),
            metadata=dict(data.get("metadata", {})),
        )
