"""Tests for planning_strategy_factory module."""

from __future__ import annotations

import pytest

from taskforce.application.planning_strategy_factory import (
    _coerce_bool,
    select_planning_strategy,
)
from taskforce.core.domain.planning_strategy import (
    NativeReActStrategy,
    PlanAndExecuteStrategy,
    PlanAndReactStrategy,
    SparStrategy,
)


class TestCoerceBool:
    """Tests for _coerce_bool helper."""

    def test_none_returns_default_true(self) -> None:
        assert _coerce_bool(None, True) is True

    def test_none_returns_default_false(self) -> None:
        assert _coerce_bool(None, False) is False

    def test_bool_true(self) -> None:
        assert _coerce_bool(True, False) is True

    def test_bool_false(self) -> None:
        assert _coerce_bool(False, True) is False

    def test_string_true_variants(self) -> None:
        for val in ("true", "True", "TRUE", "yes", "Yes", "y", "Y", "1"):
            assert _coerce_bool(val, False) is True, f"Failed for {val!r}"

    def test_string_false_variants(self) -> None:
        for val in ("false", "False", "no", "0", "n", ""):
            assert _coerce_bool(val, True) is False, f"Failed for {val!r}"

    def test_integer_truthy(self) -> None:
        assert _coerce_bool(1, False) is True

    def test_integer_falsy(self) -> None:
        assert _coerce_bool(0, True) is False


class TestSelectPlanningStrategy:
    """Tests for select_planning_strategy."""

    def test_default_returns_native_react(self) -> None:
        strategy = select_planning_strategy()
        assert isinstance(strategy, NativeReActStrategy)

    def test_none_returns_native_react(self) -> None:
        strategy = select_planning_strategy(strategy_name=None)
        assert isinstance(strategy, NativeReActStrategy)

    def test_native_react_explicit(self) -> None:
        strategy = select_planning_strategy(strategy_name="native_react")
        assert isinstance(strategy, NativeReActStrategy)

    def test_plan_and_execute_defaults(self) -> None:
        strategy = select_planning_strategy(strategy_name="plan_and_execute")
        assert isinstance(strategy, PlanAndExecuteStrategy)
        assert strategy.max_step_iterations == 4
        assert strategy.max_plan_steps == 12

    def test_plan_and_execute_custom_params(self) -> None:
        strategy = select_planning_strategy(
            strategy_name="plan_and_execute",
            params={"max_step_iterations": 2, "max_plan_steps": 6},
        )
        assert isinstance(strategy, PlanAndExecuteStrategy)
        assert strategy.max_step_iterations == 2
        assert strategy.max_plan_steps == 6

    def test_plan_and_react(self) -> None:
        strategy = select_planning_strategy(strategy_name="plan_and_react")
        assert isinstance(strategy, PlanAndReactStrategy)
        # PlanAndReactStrategy delegates to NativeReActStrategy internally
        assert strategy._delegate.max_plan_steps == 12

    def test_plan_and_react_custom_params(self) -> None:
        strategy = select_planning_strategy(
            strategy_name="plan_and_react",
            params={"max_plan_steps": 8},
        )
        assert isinstance(strategy, PlanAndReactStrategy)
        assert strategy._delegate.max_plan_steps == 8

    def test_spar_defaults(self) -> None:
        strategy = select_planning_strategy(strategy_name="spar")
        assert isinstance(strategy, SparStrategy)
        assert strategy.max_step_iterations == 3
        assert strategy.max_plan_steps == 12
        assert strategy.reflect_every_step is True
        assert strategy.max_reflection_iterations == 2

    def test_spar_custom_params(self) -> None:
        strategy = select_planning_strategy(
            strategy_name="spar",
            params={
                "max_step_iterations": 5,
                "max_plan_steps": 20,
                "reflect_every_step": "false",
                "max_reflection_iterations": 3,
            },
        )
        assert isinstance(strategy, SparStrategy)
        assert strategy.max_step_iterations == 5
        assert strategy.max_plan_steps == 20
        assert strategy.reflect_every_step is False
        assert strategy.max_reflection_iterations == 3

    def test_name_normalization_dashes(self) -> None:
        strategy = select_planning_strategy(strategy_name="plan-and-execute")
        assert isinstance(strategy, PlanAndExecuteStrategy)

    def test_name_normalization_uppercase(self) -> None:
        strategy = select_planning_strategy(strategy_name="SPAR")
        assert isinstance(strategy, SparStrategy)

    def test_name_normalization_whitespace(self) -> None:
        strategy = select_planning_strategy(strategy_name="  native_react  ")
        assert isinstance(strategy, NativeReActStrategy)

    def test_invalid_strategy_raises(self) -> None:
        with pytest.raises(ValueError, match="Invalid planning_strategy"):
            select_planning_strategy(strategy_name="unknown_strategy")

    def test_non_dict_params_raises(self) -> None:
        with pytest.raises(ValueError, match="must be a dictionary"):
            select_planning_strategy(
                strategy_name="spar",
                params="not a dict",  # type: ignore[arg-type]
            )
