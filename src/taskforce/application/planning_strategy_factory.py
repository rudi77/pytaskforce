"""Planning Strategy Factory - Extracted from AgentFactory.

Provides :func:`select_planning_strategy` which instantiates the correct
planning strategy class from a strategy name and optional parameters.
"""

from __future__ import annotations

from typing import Any

import structlog

from taskforce.core.domain.planning_strategy import (
    NativeReActStrategy,
    PlanAndExecuteStrategy,
    PlanAndReactStrategy,
    PlanningStrategy,
    SparStrategy,
)


def _coerce_bool(value: Any, default: bool) -> bool:
    """Coerce config values into booleans with sane defaults."""
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "y"}
    return bool(value)


def select_planning_strategy(
    strategy_name: str | None = None,
    params: dict[str, Any] | None = None,
) -> PlanningStrategy:
    """Select and instantiate a planning strategy.

    Args:
        strategy_name: Strategy name. One of ``native_react``,
            ``plan_and_execute``, ``plan_and_react``, ``spar``.
            Defaults to ``native_react``.
        params: Optional strategy-specific parameters.

    Returns:
        PlanningStrategy instance.

    Raises:
        ValueError: If strategy name is invalid or params are malformed.
    """
    normalized = (
        (strategy_name or "native_react").strip().lower().replace("-", "_")
    )
    params = params or {}
    if not isinstance(params, dict):
        raise ValueError("planning_strategy_params must be a dictionary")

    logger = structlog.get_logger().bind(
        component=f"{normalized}_strategy"
    )

    if normalized == "native_react":
        return NativeReActStrategy()  # type: ignore[return-value]

    if normalized == "plan_and_execute":
        max_step = params.get("max_step_iterations")
        max_plan = params.get("max_plan_steps")
        return PlanAndExecuteStrategy(  # type: ignore[return-value]
            max_step_iterations=int(max_step) if max_step is not None else 4,
            max_plan_steps=int(max_plan) if max_plan is not None else 12,
            logger=logger,
        )

    if normalized == "plan_and_react":
        max_plan = params.get("max_plan_steps")
        return PlanAndReactStrategy(  # type: ignore[return-value]
            max_plan_steps=int(max_plan) if max_plan is not None else 12,
            logger=logger,
        )

    if normalized == "spar":
        max_step = params.get("max_step_iterations")
        max_plan = params.get("max_plan_steps")
        reflect_val = params.get("reflect_every_step")
        max_reflect = params.get("max_reflection_iterations")
        return SparStrategy(  # type: ignore[return-value]
            max_step_iterations=(
                int(max_step) if max_step is not None else 3
            ),
            max_plan_steps=int(max_plan) if max_plan is not None else 12,
            reflect_every_step=_coerce_bool(reflect_val, True),
            max_reflection_iterations=(
                int(max_reflect) if max_reflect is not None else 2
            ),
            logger=logger,
        )

    raise ValueError(
        "Invalid planning_strategy. Supported values: "
        "native_react, plan_and_execute, plan_and_react, spar"
    )
