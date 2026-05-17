"""Tests for AdaptivePlanningStrategy."""
from __future__ import annotations

from collections.abc import AsyncIterator
from unittest.mock import AsyncMock, MagicMock

import pytest

from taskforce.core.domain.complexity_classifier import ComplexityVerdict
from taskforce.core.domain.planning_strategy import AdaptivePlanningStrategy


class _StubStrategy:
    """Minimal PlanningStrategy stub with traceable invocation."""

    def __init__(self, name: str):
        self.name = name
        self.execute_calls: list[tuple] = []
        self.stream_calls: list[tuple] = []

    async def execute(self, agent, mission, session_id):
        self.execute_calls.append((agent, mission, session_id))
        return f"<result from {self.name}>"

    async def execute_stream(self, agent, mission, session_id) -> AsyncIterator[object]:
        self.stream_calls.append((agent, mission, session_id))
        if False:  # pragma: no cover - generator skeleton
            yield None


class _StubClassifier:
    """Classifier stub that returns a pre-set verdict."""

    def __init__(self, verdict: ComplexityVerdict):
        self.verdict = verdict
        self.calls: list[str] = []

    async def classify(self, mission: str) -> ComplexityVerdict:
        self.calls.append(mission)
        return self.verdict


@pytest.fixture
def simple_strategy():
    return _StubStrategy("native_react")


@pytest.fixture
def complex_strategy():
    return _StubStrategy("plan_and_react")


@pytest.fixture
def fake_agent():
    return MagicMock(logger=MagicMock())


@pytest.mark.asyncio
class TestRouting:
    """The classifier verdict determines which substrategy runs."""

    async def test_simple_verdict_routes_to_simple(
        self, simple_strategy, complex_strategy, fake_agent
    ):
        classifier = _StubClassifier(ComplexityVerdict(
            level="simple", confidence=0.9, reason="trivial"
        ))
        strat = AdaptivePlanningStrategy(
            simple=simple_strategy,
            complex_strategy=complex_strategy,
            classifier=classifier,
        )
        await strat.execute(fake_agent, "what is 17 times 23", "s1")
        assert len(simple_strategy.execute_calls) == 1
        assert len(complex_strategy.execute_calls) == 0
        assert classifier.calls == ["what is 17 times 23"]

    async def test_complex_verdict_routes_to_complex(
        self, simple_strategy, complex_strategy, fake_agent
    ):
        classifier = _StubClassifier(ComplexityVerdict(
            level="complex", confidence=0.8, reason="multi-step"
        ))
        strat = AdaptivePlanningStrategy(
            simple=simple_strategy,
            complex_strategy=complex_strategy,
            classifier=classifier,
        )
        await strat.execute(fake_agent, "plan my Berlin trip", "s1")
        assert len(simple_strategy.execute_calls) == 0
        assert len(complex_strategy.execute_calls) == 1


@pytest.mark.asyncio
class TestFallback:
    """confidence == 0.0 means classifier failed - use fallback_level."""

    async def test_zero_confidence_uses_default_fallback_complex(
        self, simple_strategy, complex_strategy, fake_agent
    ):
        classifier = _StubClassifier(ComplexityVerdict(
            level="simple", confidence=0.0, reason="fallback"
        ))
        # default fallback is "complex"
        strat = AdaptivePlanningStrategy(
            simple=simple_strategy,
            complex_strategy=complex_strategy,
            classifier=classifier,
        )
        await strat.execute(fake_agent, "x", "s1")
        # Even though verdict.level == "simple", confidence 0 = fallback to complex
        assert len(complex_strategy.execute_calls) == 1
        assert len(simple_strategy.execute_calls) == 0

    async def test_zero_confidence_with_simple_fallback(
        self, simple_strategy, complex_strategy, fake_agent
    ):
        classifier = _StubClassifier(ComplexityVerdict(
            level="complex", confidence=0.0, reason="fallback"
        ))
        strat = AdaptivePlanningStrategy(
            simple=simple_strategy,
            complex_strategy=complex_strategy,
            classifier=classifier,
            fallback_level="simple",
        )
        await strat.execute(fake_agent, "x", "s1")
        assert len(simple_strategy.execute_calls) == 1
        assert len(complex_strategy.execute_calls) == 0

    async def test_invalid_fallback_level_normalises_to_complex(
        self, simple_strategy, complex_strategy, fake_agent
    ):
        classifier = _StubClassifier(ComplexityVerdict(
            level="simple", confidence=0.0, reason="fallback"
        ))
        strat = AdaptivePlanningStrategy(
            simple=simple_strategy,
            complex_strategy=complex_strategy,
            classifier=classifier,
            fallback_level="nonsense",
        )
        await strat.execute(fake_agent, "x", "s1")
        # invalid fallback -> defaults to complex
        assert len(complex_strategy.execute_calls) == 1


@pytest.mark.asyncio
class TestExecuteStream:
    """execute_stream must also route via the classifier."""

    async def test_stream_routes_through_classifier(
        self, simple_strategy, complex_strategy, fake_agent
    ):
        classifier = _StubClassifier(ComplexityVerdict(
            level="simple", confidence=0.9, reason="ok"
        ))
        strat = AdaptivePlanningStrategy(
            simple=simple_strategy,
            complex_strategy=complex_strategy,
            classifier=classifier,
        )
        # Consume the stream (empty generator)
        async for _ in strat.execute_stream(fake_agent, "x", "s1"):
            pass
        assert len(simple_strategy.stream_calls) == 1
        assert classifier.calls == ["x"]


class TestName:
    def test_name_is_adaptive(self, simple_strategy, complex_strategy):
        """Consistent with other strategies: name is a stable class-level string."""
        classifier = _StubClassifier(ComplexityVerdict("simple", 1.0, "x"))
        strat = AdaptivePlanningStrategy(
            simple=simple_strategy,
            complex_strategy=complex_strategy,
            classifier=classifier,
        )
        assert strat.name == "adaptive"


# ---------------------------------------------------------------------------
# Factory integration
# ---------------------------------------------------------------------------

class TestFactoryIntegration:
    """select_planning_strategy('adaptive', ..., llm_provider=...) end-to-end."""

    def test_factory_builds_adaptive_with_default_params(self):
        from taskforce.application.planning_strategy_factory import select_planning_strategy

        llm = MagicMock()
        llm.complete_json = AsyncMock()
        strat = select_planning_strategy("adaptive", llm_provider=llm)
        assert isinstance(strat, AdaptivePlanningStrategy)
        assert strat.simple.name == "native_react"
        assert strat.complex.name == "plan_and_react"

    def test_factory_respects_custom_sub_strategies(self):
        from taskforce.application.planning_strategy_factory import select_planning_strategy

        llm = MagicMock()
        llm.complete_json = AsyncMock()
        strat = select_planning_strategy(
            "adaptive",
            params={"simple": "native_react", "complex": "spar"},
            llm_provider=llm,
        )
        assert isinstance(strat, AdaptivePlanningStrategy)
        assert strat.complex.name == "spar"

    def test_factory_raises_without_llm_provider(self):
        from taskforce.application.planning_strategy_factory import select_planning_strategy

        with pytest.raises(ValueError, match="requires llm_provider"):
            select_planning_strategy("adaptive")
