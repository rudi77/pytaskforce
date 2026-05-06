"""REST CRUD for standing goals + manual evaluation trigger.

* ``GET    /api/v1/standing-goals``                 — list all goals
* ``POST   /api/v1/standing-goals``                 — create a goal
* ``GET    /api/v1/standing-goals/{goal_id}``       — fetch one
* ``PATCH  /api/v1/standing-goals/{goal_id}``       — partial update
* ``DELETE /api/v1/standing-goals/{goal_id}``       — remove
* ``POST   /api/v1/standing-goals/{goal_id}/evaluate-now``
                                                    — force an evaluation

The store is always reachable via the lazy ``get_standing_goal_store``
default (file-backed). The evaluator is only available when an
embedding host (butler daemon) has registered one — otherwise
``evaluate-now`` returns 503.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from taskforce.api.dependencies import (
    get_goal_evaluator,
    get_standing_goal_store,
)
from taskforce.core.domain.standing_goal import StandingGoal

router = APIRouter()


class StandingGoalIn(BaseModel):
    description: str
    evaluation_prompt: str
    frequency: str
    priority: int = 5
    enabled: bool = True
    metadata: dict[str, Any] = Field(default_factory=dict)


class StandingGoalPatch(BaseModel):
    description: str | None = None
    evaluation_prompt: str | None = None
    frequency: str | None = None
    priority: int | None = None
    enabled: bool | None = None
    metadata: dict[str, Any] | None = None


class StandingGoalOut(BaseModel):
    goal_id: str
    description: str
    evaluation_prompt: str
    frequency: str
    priority: int
    enabled: bool
    last_evaluated_at: datetime | None
    last_action_taken: str
    metadata: dict[str, Any]


def _to_out(goal: StandingGoal) -> StandingGoalOut:
    return StandingGoalOut(**goal.to_dict() | {"last_evaluated_at": goal.last_evaluated_at})


@router.get("/standing-goals", response_model=list[StandingGoalOut])
async def list_goals(store=Depends(get_standing_goal_store)) -> list[StandingGoalOut]:
    return [_to_out(g) for g in await store.list()]


@router.post(
    "/standing-goals",
    response_model=StandingGoalOut,
    status_code=status.HTTP_201_CREATED,
)
async def create_goal(
    body: StandingGoalIn,
    store=Depends(get_standing_goal_store),
) -> StandingGoalOut:
    goal = StandingGoal(
        description=body.description,
        evaluation_prompt=body.evaluation_prompt,
        frequency=body.frequency,
        priority=body.priority,
        enabled=body.enabled,
        metadata=dict(body.metadata),
    )
    return _to_out(await store.add(goal))


@router.get("/standing-goals/{goal_id}", response_model=StandingGoalOut)
async def get_goal(goal_id: str, store=Depends(get_standing_goal_store)) -> StandingGoalOut:
    goal = await store.get(goal_id)
    if goal is None:
        raise HTTPException(status_code=404, detail=f"No standing goal {goal_id!r}")
    return _to_out(goal)


@router.patch("/standing-goals/{goal_id}", response_model=StandingGoalOut)
async def update_goal(
    goal_id: str,
    body: StandingGoalPatch,
    store=Depends(get_standing_goal_store),
) -> StandingGoalOut:
    goal = await store.get(goal_id)
    if goal is None:
        raise HTTPException(status_code=404, detail=f"No standing goal {goal_id!r}")
    if body.description is not None:
        goal.description = body.description
    if body.evaluation_prompt is not None:
        goal.evaluation_prompt = body.evaluation_prompt
    if body.frequency is not None:
        goal.frequency = body.frequency
    if body.priority is not None:
        goal.priority = body.priority
    if body.enabled is not None:
        goal.enabled = body.enabled
    if body.metadata is not None:
        goal.metadata = dict(body.metadata)
    return _to_out(await store.update(goal))


@router.delete("/standing-goals/{goal_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_goal(goal_id: str, store=Depends(get_standing_goal_store)) -> None:
    deleted = await store.delete(goal_id)
    if not deleted:
        raise HTTPException(status_code=404, detail=f"No standing goal {goal_id!r}")


@router.post(
    "/standing-goals/{goal_id}/evaluate-now",
    status_code=status.HTTP_202_ACCEPTED,
)
async def evaluate_now(goal_id: str) -> dict[str, Any]:
    evaluator = get_goal_evaluator()
    if evaluator is None:
        raise HTTPException(
            status_code=503,
            detail=(
                "No GoalEvaluatorService is registered with this API process. "
                "Start the butler daemon first."
            ),
        )
    result = await evaluator.evaluate_goal(goal_id)
    if result is None:
        raise HTTPException(status_code=404, detail=f"No standing goal {goal_id!r}")
    return result
