"""GoalEvaluatorService — cron filter + LLM dispatch + submit."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pytest

from taskforce.application.goal_evaluator_service import (
    GoalDecision,
    GoalEvaluatorService,
)
from taskforce.core.domain.standing_goal import StandingGoal


class _InMemoryStore:
    def __init__(self, goals: list[StandingGoal]) -> None:
        self._goals = {g.goal_id: g for g in goals}
        self.evaluated: list[tuple[str, datetime, str]] = []

    async def list(self) -> list[StandingGoal]:
        return list(self._goals.values())

    async def get(self, goal_id: str) -> StandingGoal | None:
        return self._goals.get(goal_id)

    async def add(self, goal: StandingGoal) -> StandingGoal:
        self._goals[goal.goal_id] = goal
        return goal

    async def update(self, goal: StandingGoal) -> StandingGoal:
        self._goals[goal.goal_id] = goal
        return goal

    async def delete(self, goal_id: str) -> bool:
        return self._goals.pop(goal_id, None) is not None

    async def mark_evaluated(
        self,
        goal_id: str,
        evaluated_at: datetime,
        action_taken: str,
    ) -> None:
        self.evaluated.append((goal_id, evaluated_at, action_taken))
        goal = self._goals.get(goal_id)
        if goal:
            goal.last_evaluated_at = evaluated_at
            goal.last_action_taken = action_taken


@pytest.mark.spec("standing-goals.disabled_goal_is_skipped")
@pytest.mark.asyncio
async def test_disabled_goals_are_skipped() -> None:
    goal = StandingGoal(
        description="d", evaluation_prompt="p", frequency="* * * * *", enabled=False
    )
    store = _InMemoryStore([goal])
    submitted: list[Any] = []

    async def submit(req: Any) -> None:
        submitted.append(req)

    async def decide(_g: Any, _now: Any) -> GoalDecision:
        return GoalDecision(act=True, mission="m")

    service = GoalEvaluatorService(store=store, submit=submit, decide=decide)
    await service.evaluate_due_goals()

    assert submitted == []
    assert store.evaluated == []


@pytest.mark.spec("standing-goals.submitted_mission_carries_goal_id_metadata")
@pytest.mark.asyncio
async def test_act_decision_submits_request_and_marks_evaluated() -> None:
    goal = StandingGoal(
        description="weekly",
        evaluation_prompt="prompt",
        frequency="* * * * *",
        priority=2,
    )
    store = _InMemoryStore([goal])
    submitted: list[Any] = []

    async def submit(req: Any) -> None:
        submitted.append(req)

    async def decide(_g: Any, _now: Any) -> GoalDecision:
        return GoalDecision(act=True, mission="do the thing", rationale="weekly tick")

    fixed_now = datetime(2026, 5, 6, 9, 0, tzinfo=UTC)
    service = GoalEvaluatorService(
        store=store, submit=submit, decide=decide, clock=lambda: fixed_now
    )

    results = await service.evaluate_due_goals()

    assert len(submitted) == 1
    assert submitted[0].channel == "standing_goal"
    assert submitted[0].priority == 2
    assert submitted[0].metadata["standing_goal_id"] == goal.goal_id
    assert store.evaluated == [(goal.goal_id, fixed_now, "weekly tick")]
    assert results == [
        {"goal_id": goal.goal_id, "acted": True, "rationale": "weekly tick"}
    ]


@pytest.mark.asyncio
async def test_no_action_decision_marks_evaluated_without_submit() -> None:
    goal = StandingGoal(
        description="d", evaluation_prompt="p", frequency="* * * * *"
    )
    store = _InMemoryStore([goal])
    submitted: list[Any] = []

    async def submit(req: Any) -> None:
        submitted.append(req)

    async def decide(_g: Any, _now: Any) -> GoalDecision:
        return GoalDecision(act=False, rationale="nothing to do")

    service = GoalEvaluatorService(store=store, submit=submit, decide=decide)
    await service.evaluate_due_goals()

    assert submitted == []
    assert store.evaluated[0][2] == "nothing to do"


@pytest.mark.asyncio
async def test_decide_failure_does_not_break_loop() -> None:
    goal_a = StandingGoal(
        description="a", evaluation_prompt="pa", frequency="* * * * *"
    )
    goal_b = StandingGoal(
        description="b", evaluation_prompt="pb", frequency="* * * * *"
    )
    store = _InMemoryStore([goal_a, goal_b])
    submitted: list[Any] = []

    async def submit(req: Any) -> None:
        submitted.append(req)

    async def decide(goal: StandingGoal, _now: Any) -> GoalDecision:
        if goal.goal_id == goal_a.goal_id:
            raise RuntimeError("boom")
        return GoalDecision(act=True, mission="m")

    service = GoalEvaluatorService(store=store, submit=submit, decide=decide)
    results = await service.evaluate_due_goals()

    # Only goal_b made it through.
    assert len(submitted) == 1
    assert results == [{"goal_id": goal_b.goal_id, "acted": True, "rationale": "acted"}]


@pytest.mark.asyncio
async def test_evaluate_goal_unknown_returns_none() -> None:
    store = _InMemoryStore([])

    async def submit(req: Any) -> None:
        raise AssertionError("must not submit for unknown goal")

    async def decide(_g: Any, _now: Any) -> GoalDecision:
        return GoalDecision(act=False)

    service = GoalEvaluatorService(store=store, submit=submit, decide=decide)
    assert await service.evaluate_goal("does-not-exist") is None


@pytest.mark.spec("standing-goals.cron_prefilter_skips_when_not_due")
@pytest.mark.asyncio
async def test_cron_filter_skips_not_due_goals() -> None:
    """A goal whose cron last fired before its last_evaluated_at is not due yet."""
    last_eval = datetime(2026, 5, 6, 9, 0, tzinfo=UTC)
    goal = StandingGoal(
        description="weekly",
        evaluation_prompt="p",
        frequency="0 9 * * 1",  # Mondays 9 (next firing well in the future)
        last_evaluated_at=last_eval,
    )
    store = _InMemoryStore([goal])
    submitted: list[Any] = []

    async def submit(req: Any) -> None:
        submitted.append(req)

    decisions: list[Any] = []

    async def decide(g: Any, now: Any) -> GoalDecision:
        decisions.append((g, now))
        return GoalDecision(act=True, mission="m")

    just_after = datetime(2026, 5, 6, 9, 5, tzinfo=UTC)  # same Wednesday morning
    service = GoalEvaluatorService(
        store=store, submit=submit, decide=decide, clock=lambda: just_after
    )

    await service.evaluate_due_goals()

    # Cron filter said "not due" → no LLM call, no submit.
    assert decisions == []
    assert submitted == []


@pytest.mark.spec("standing-goals.first_run_evaluates_even_without_history")
@pytest.mark.asyncio
async def test_first_run_evaluates_goal_with_no_history() -> None:
    """A goal with last_evaluated_at=None is due on the first tick — even with
    a weekly cron and a clock nowhere near the cron boundary."""
    goal = StandingGoal(
        description="weekly",
        evaluation_prompt="p",
        frequency="0 9 * * 1",  # Mondays 9am
        # last_evaluated_at defaults to None → first run
    )
    store = _InMemoryStore([goal])
    submitted: list[Any] = []

    async def submit(req: Any) -> None:
        submitted.append(req)

    async def decide(_g: Any, _now: Any) -> GoalDecision:
        return GoalDecision(act=True, mission="m")

    # A Wednesday afternoon — nowhere near the Monday-9am cron firing.
    not_monday = datetime(2026, 5, 6, 14, 0, tzinfo=UTC)
    service = GoalEvaluatorService(
        store=store, submit=submit, decide=decide, clock=lambda: not_monday
    )

    results = await service.evaluate_due_goals()

    assert len(submitted) == 1
    assert len(results) == 1
    assert results[0]["goal_id"] == goal.goal_id


@pytest.mark.spec("standing-goals.bad_cron_falls_back_to_always_due")
@pytest.mark.asyncio
async def test_bad_cron_expression_is_treated_as_always_due() -> None:
    """A malformed cron expression falls back to 'always due' so the
    misconfiguration surfaces via mark_evaluated instead of silently
    disabling the goal."""
    goal = StandingGoal(
        description="misconfigured",
        evaluation_prompt="p",
        frequency="not a cron",
        last_evaluated_at=datetime(2026, 5, 6, 9, 0, tzinfo=UTC),
    )
    store = _InMemoryStore([goal])
    submitted: list[Any] = []

    async def submit(req: Any) -> None:
        submitted.append(req)

    async def decide(_g: Any, _now: Any) -> GoalDecision:
        return GoalDecision(act=True, mission="m")

    # Only five minutes after last_evaluated_at — a valid cron would NOT be
    # due, but a bad cron forces "always due".
    later = datetime(2026, 5, 6, 9, 5, tzinfo=UTC)
    service = GoalEvaluatorService(
        store=store, submit=submit, decide=decide, clock=lambda: later
    )

    await service.evaluate_due_goals()

    assert len(submitted) == 1
    assert store.evaluated[0][0] == goal.goal_id


@pytest.mark.spec("standing-goals.decision_failure_does_not_mark_evaluated")
@pytest.mark.asyncio
async def test_decision_failure_leaves_goal_unevaluated() -> None:
    """When the LLM decision raises, the goal is NOT marked evaluated, so the
    next tick retries it."""
    goal = StandingGoal(
        description="d", evaluation_prompt="p", frequency="* * * * *"
    )
    store = _InMemoryStore([goal])

    async def submit(_req: Any) -> None:
        raise AssertionError("must not submit when the decision failed")

    async def decide(_g: Any, _now: Any) -> GoalDecision:
        raise RuntimeError("LLM unavailable")

    service = GoalEvaluatorService(store=store, submit=submit, decide=decide)
    results = await service.evaluate_due_goals()

    assert store.evaluated == []
    assert results == []


@pytest.mark.spec("standing-goals.submit_failure_does_not_mark_evaluated")
@pytest.mark.asyncio
async def test_submit_failure_leaves_goal_unevaluated() -> None:
    """When mission submission raises, the goal is NOT marked evaluated, so the
    next tick retries it."""
    goal = StandingGoal(
        description="d", evaluation_prompt="p", frequency="* * * * *"
    )
    store = _InMemoryStore([goal])

    async def submit(_req: Any) -> None:
        raise RuntimeError("request queue is down")

    async def decide(_g: Any, _now: Any) -> GoalDecision:
        return GoalDecision(act=True, mission="m")

    service = GoalEvaluatorService(store=store, submit=submit, decide=decide)
    results = await service.evaluate_due_goals()

    assert store.evaluated == []
    assert results == []
