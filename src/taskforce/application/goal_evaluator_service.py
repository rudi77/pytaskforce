"""Standing-goal evaluator — proactive layer.

Runs once per heartbeat tick. For every enabled, due standing goal it
asks the LLM whether to act now and, if yes, submits a mission to the
``PersistentAgentService`` queue. If a goal already had a previous
evaluation it is "due" when its cron expression has fired since the
last evaluation; otherwise it is due on its first matching tick.

Cost control: due goals are filtered with a cheap cron pre-filter
(reusing ``_next_cron_occurrence`` from the SchedulerService) before
any LLM call happens. A heartbeat at 15-minute granularity with five
weekly goals therefore burns at most one LLM call per week per goal —
not one per heartbeat.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta
from typing import Any

import structlog

from taskforce.core.domain.request import AgentRequest
from taskforce.core.domain.standing_goal import StandingGoal
from taskforce.core.interfaces.standing_goals import StandingGoalStoreProtocol

logger = structlog.get_logger(__name__)


# Submit signature: (mission, priority) -> Awaitable result. Decoupled
# from PersistentAgentService.submit so the evaluator stays testable
# without a full queue setup.
SubmitFn = Callable[[AgentRequest], Awaitable[Any]]
LLMDecisionFn = Callable[[StandingGoal, datetime], Awaitable["GoalDecision"]]


class GoalDecision:
    """Outcome of a single LLM evaluation.

    Attributes:
        act: ``True`` if the LLM judged action is warranted now.
        mission: The mission text to submit when ``act`` is true.
        rationale: Short summary stored on the goal as
            ``last_action_taken`` (or "no action" when ``act`` is false).
    """

    __slots__ = ("act", "mission", "rationale")

    def __init__(self, *, act: bool, mission: str = "", rationale: str = "") -> None:
        self.act = act
        self.mission = mission
        self.rationale = rationale or ("acted" if act else "no action")


class GoalEvaluatorService:
    """Evaluates standing goals on heartbeat ticks and submits missions."""

    def __init__(
        self,
        *,
        store: StandingGoalStoreProtocol,
        submit: SubmitFn,
        decide: LLMDecisionFn,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._store = store
        self._submit = submit
        self._decide = decide
        self._clock = clock or (lambda: datetime.now(UTC))

    async def evaluate_due_goals(self) -> list[dict[str, Any]]:
        """Evaluate every enabled, due goal once.

        Returns one summary record per goal that was evaluated (action
        or no-action). Goals that are not due are silently skipped so
        the daemon can call this from every heartbeat tick without
        rate-limiting itself.
        """
        now = self._clock()
        results: list[dict[str, Any]] = []
        for goal in await self._store.list():
            if not goal.enabled:
                continue
            if not _is_due(goal, now):
                continue
            try:
                decision = await self._decide(goal, now)
            except Exception as exc:
                logger.warning(
                    "goal_evaluator.decision_failed",
                    goal_id=goal.goal_id,
                    error=str(exc),
                )
                continue

            action_summary = decision.rationale
            if decision.act:
                request = AgentRequest(
                    channel="standing_goal",
                    message=decision.mission or goal.evaluation_prompt,
                    priority=goal.priority,
                    metadata={
                        "standing_goal_id": goal.goal_id,
                        "goal_description": goal.description,
                    },
                )
                try:
                    await self._submit(request)
                except Exception as exc:
                    logger.warning(
                        "goal_evaluator.submit_failed",
                        goal_id=goal.goal_id,
                        error=str(exc),
                    )
                    continue

            await self._store.mark_evaluated(goal.goal_id, now, action_summary)
            results.append(
                {
                    "goal_id": goal.goal_id,
                    "acted": decision.act,
                    "rationale": action_summary,
                }
            )
            logger.info(
                "goal_evaluator.evaluated",
                goal_id=goal.goal_id,
                acted=decision.act,
            )
        return results

    async def evaluate_goal(self, goal_id: str) -> dict[str, Any] | None:
        """Force evaluation of a single goal (used by the ``/evaluate-now`` route)."""
        goal = await self._store.get(goal_id)
        if goal is None:
            return None
        now = self._clock()
        decision = await self._decide(goal, now)
        action_summary = decision.rationale
        acted = decision.act
        if acted:
            await self._submit(
                AgentRequest(
                    channel="standing_goal",
                    message=decision.mission or goal.evaluation_prompt,
                    priority=goal.priority,
                    metadata={
                        "standing_goal_id": goal.goal_id,
                        "goal_description": goal.description,
                        "forced": True,
                    },
                )
            )
        await self._store.mark_evaluated(goal_id, now, action_summary)
        return {
            "goal_id": goal_id,
            "acted": acted,
            "rationale": action_summary,
            "forced": True,
        }


def _is_due(goal: StandingGoal, now: datetime) -> bool:
    """Return True if the goal's cron has fired since its last evaluation.

    On first run (``last_evaluated_at is None``) every enabled goal is
    considered due so the user does not have to wait for a fresh cron
    boundary to see proactive behavior.
    """
    if goal.last_evaluated_at is None:
        return True
    try:
        from taskforce.infrastructure.scheduler.scheduler_service import (
            _next_cron_occurrence,
        )
    except ImportError:  # pragma: no cover — scheduler optional in tests
        return True
    last = goal.last_evaluated_at
    # Re-use the scheduler's cron parser; goal is due if the next
    # firing computed *after the last evaluation* is in the past.
    try:
        next_after_last = _next_cron_occurrence(goal.frequency, last)
    except ValueError:
        # Bad cron expression — fall back to "always due" so the
        # evaluator can surface the misconfiguration via mark_evaluated.
        return True
    return next_after_last <= now + timedelta(seconds=1)
