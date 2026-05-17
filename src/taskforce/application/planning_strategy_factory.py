"""Planning Strategy Factory - Extracted from AgentFactory.

Provides :func:`select_planning_strategy` which instantiates the correct
planning strategy class from a strategy name and optional parameters.
"""

from __future__ import annotations

from typing import Any

import structlog

from taskforce.core.domain.complexity_classifier import (
    HeuristicComplexityClassifier,
    MissionComplexityClassifier,
    TwoStageComplexityClassifier,
)
from taskforce.core.domain.planning_strategy import (
    AdaptivePlanningStrategy,
    NativeReActStrategy,
    PlanAndExecuteStrategy,
    PlanAndReactStrategy,
    PlanningStrategy,
    SparStrategy,
)
from taskforce.core.interfaces.llm import LLMProviderProtocol


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
    *,
    llm_provider: LLMProviderProtocol | None = None,
) -> PlanningStrategy:
    """Select and instantiate a planning strategy.

    Args:
        strategy_name: Strategy name. One of ``native_react``,
            ``plan_and_execute``, ``plan_and_react``, ``spar``, ``adaptive``.
            Defaults to ``native_react``.
        params: Optional strategy-specific parameters.
        llm_provider: Required when ``strategy_name == "adaptive"`` so the
            built-in MissionComplexityClassifier has an LLM for routing.
            Ignored for all other strategies.

    Returns:
        PlanningStrategy instance.

    Raises:
        ValueError: If strategy name is invalid, params are malformed, or
            ``adaptive`` is requested without an llm_provider.
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
        return NativeReActStrategy()

    if normalized == "plan_and_execute":
        max_step = params.get("max_step_iterations")
        max_plan = params.get("max_plan_steps")
        return PlanAndExecuteStrategy(
            max_step_iterations=int(max_step) if max_step is not None else 4,
            max_plan_steps=int(max_plan) if max_plan is not None else 12,
            logger=logger,
        )

    if normalized == "plan_and_react":
        max_plan = params.get("max_plan_steps")
        return PlanAndReactStrategy(
            max_plan_steps=int(max_plan) if max_plan is not None else 12,
            logger=logger,
        )

    if normalized == "spar":
        max_step = params.get("max_step_iterations")
        max_plan = params.get("max_plan_steps")
        reflect_val = params.get("reflect_every_step")
        max_reflect = params.get("max_reflection_iterations")
        return SparStrategy(
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

    if normalized == "adaptive":
        if llm_provider is None:
            raise ValueError(
                "planning_strategy='adaptive' requires llm_provider — pass it "
                "via select_planning_strategy(..., llm_provider=...). The "
                "AgentFactory does this automatically."
            )
        simple_name = params.get("simple", "native_react")
        complex_name = params.get("complex", "plan_and_react")
        fallback_level = params.get("fallback", "complex")
        classification_model = params.get("classifier_model", "fast")
        max_mission_chars = int(params.get("max_mission_chars", 500))
        # classifier_mode:
        #   "two_stage" (default) — heuristic pre-filter + LLM on UNKNOWN
        #   "llm"                 — LLM only, every mission
        #   "heuristic"           — heuristic only, no LLM (fallback on UNKNOWN)
        classifier_mode = params.get("classifier_mode", "two_stage")

        # Sub-strategies recursively use the same factory so they pick up
        # their own param defaults. They themselves are non-adaptive, so
        # llm_provider isn't propagated further (would only matter if a
        # user nested adaptive inside adaptive, which we don't support).
        simple_params = params.get("simple_params") or {}
        complex_params = params.get("complex_params") or {}
        simple = select_planning_strategy(simple_name, simple_params)
        complex_strategy = select_planning_strategy(complex_name, complex_params)

        if classifier_mode == "llm":
            classifier: Any = MissionComplexityClassifier(
                llm_provider,
                classification_model=classification_model,
                max_mission_chars=max_mission_chars,
            )
        elif classifier_mode == "heuristic":
            classifier = HeuristicComplexityClassifier()
        elif classifier_mode == "two_stage":
            llm = MissionComplexityClassifier(
                llm_provider,
                classification_model=classification_model,
                max_mission_chars=max_mission_chars,
            )
            classifier = TwoStageComplexityClassifier(
                heuristic=HeuristicComplexityClassifier(),
                llm_fallback=llm,
            )
        else:
            raise ValueError(
                f"Invalid classifier_mode={classifier_mode!r}. "
                "Supported: two_stage (default), llm, heuristic"
            )

        return AdaptivePlanningStrategy(
            simple=simple,
            complex_strategy=complex_strategy,
            classifier=classifier,
            fallback_level=fallback_level,
            logger=logger,
        )

    raise ValueError(
        "Invalid planning_strategy. Supported values: "
        "native_react, plan_and_execute, plan_and_react, spar, adaptive"
    )
