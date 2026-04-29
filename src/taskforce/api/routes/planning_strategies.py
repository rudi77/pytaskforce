"""
Planning Strategies API Route
=============================

Surfaces the supported planning-strategy identifiers for the agent
editor's strategy dropdown. The list is static and matches the values
accepted by :class:`AgentConfigSchema`.
"""

from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter()


class PlanningStrategy(BaseModel):
    id: str
    label: str
    description: str


class PlanningStrategiesResponse(BaseModel):
    strategies: list[PlanningStrategy]


_STRATEGIES: list[PlanningStrategy] = [
    PlanningStrategy(
        id="native_react",
        label="Native ReAct",
        description=(
            "Default. Pure ReAct loop — Thought → Action → Observation cycle "
            "without an upfront plan."
        ),
    ),
    PlanningStrategy(
        id="plan_and_execute",
        label="Plan & Execute",
        description="Generates a plan first, then executes each step in sequence.",
    ),
    PlanningStrategy(
        id="plan_and_react",
        label="Plan & React (hybrid)",
        description=(
            "Generates a plan, then runs a focused ReAct cycle inside each step "
            "for tool-driven sub-tasks."
        ),
    ),
    PlanningStrategy(
        id="spar",
        label="SPAR",
        description=(
            "Structured Sense → Plan → Act → Reflect cycle with iterative "
            "refinement after each step."
        ),
    ),
]


@router.get(
    "/planning-strategies",
    response_model=PlanningStrategiesResponse,
    summary="List supported planning strategies",
)
def list_planning_strategies() -> PlanningStrategiesResponse:
    return PlanningStrategiesResponse(strategies=_STRATEGIES)
