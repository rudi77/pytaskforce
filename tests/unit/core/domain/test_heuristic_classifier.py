"""Tests for HeuristicComplexityClassifier and TwoStageComplexityClassifier."""
from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from taskforce.core.domain.complexity_classifier import (
    ComplexityVerdict,
    HeuristicComplexityClassifier,
    MissionComplexityClassifier,
    TwoStageComplexityClassifier,
)


# ---------------------------------------------------------------------------
# Heuristic
# ---------------------------------------------------------------------------


class TestHeuristicSimplePatterns:
    """Missions that obviously belong to native_react."""

    @pytest.mark.parametrize("mission", [
        "17 * 23",
        "17 mal 23",
        "100 + 250",
        "5 / 2 =",
        "Wie ist gerade das Wetter in Salzburg?",
        "Was ist 17 mal 23?",
        "Wer war Konrad Adenauer?",
        "What is the capital of France?",
        "Erinnere mich in 2 Stunden ans Frühstück.",
        "Erinnere mich morgen um 7:30 Tabletten zu nehmen",
        "Remind me at 8pm to call Bob",
        "Setze einen Reminder für 14:00",
        "Merke dir: meine Lieblingsmusik ist Jazz.",
        "Notiere das.",
    ])
    def test_classifies_as_simple(self, mission):
        clf = HeuristicComplexityClassifier()
        match = clf.classify_sync(mission)
        assert match.verdict == "simple", (
            f"{mission!r} should be SIMPLE, got {match.verdict} ({match.reason})"
        )


class TestHeuristicComplexPatterns:
    """Missions that obviously belong to plan_and_react."""

    @pytest.mark.parametrize("mission", [
        "Vergleiche die Top 3 Elektroautos unter 40k Euro: Preis, Reichweite, Ladezeit.",
        "Plane eine 3-Tage-Reise nach Berlin: Bahn, Hotel, 2 Sehenswürdigkeiten.",
        "Compare the latest iPhones and Pixels in terms of camera and battery.",
        "Erst: hole die ungelesenen Mails. Dann: schreibe eine Zusammenfassung.",
        "Recherchiere die Top 5 Tech-News und vergleiche mit gestern.",
        "Durchsuche meine Downloads nach Rechnungen 2025 und kategorisiere sie.",
        "Plan my trip step by step including transport and accommodation.",
        "Schrittweise eine Excel-Auswertung der letzten 12 Monate erstellen.",
    ])
    def test_classifies_as_complex(self, mission):
        clf = HeuristicComplexityClassifier()
        match = clf.classify_sync(mission)
        assert match.verdict == "complex", (
            f"{mission!r} should be COMPLEX, got {match.verdict} ({match.reason})"
        )


class TestHeuristicUnknown:
    """Ambiguous missions go to UNKNOWN so the LLM can decide."""

    @pytest.mark.parametrize("mission", [
        # Medium length, no clear keywords
        "Hi, brauche mal kurz deine Hilfe mit irgendwas Wichtigem dazu",
        "Kannst du mir bitte einen Vorschlag machen für die Adresse aus Wien",
    ])
    def test_classifies_as_unknown(self, mission):
        clf = HeuristicComplexityClassifier()
        match = clf.classify_sync(mission)
        assert match.verdict == "unknown", (
            f"{mission!r} should be UNKNOWN, got {match.verdict} ({match.reason})"
        )


class TestHeuristicEdgeCases:
    def test_empty_returns_unknown(self):
        clf = HeuristicComplexityClassifier()
        assert clf.classify_sync("").verdict == "unknown"
        assert clf.classify_sync("   ").verdict == "unknown"

    @pytest.mark.asyncio
    async def test_async_simple(self):
        clf = HeuristicComplexityClassifier()
        v = await clf.classify("Was ist 2 plus 2?")
        assert v.level == "simple"
        assert v.confidence == HeuristicComplexityClassifier.SIMPLE_CONFIDENCE

    @pytest.mark.asyncio
    async def test_async_complex(self):
        clf = HeuristicComplexityClassifier()
        v = await clf.classify("Vergleiche A und B.")
        assert v.level == "complex"
        assert v.confidence == HeuristicComplexityClassifier.COMPLEX_CONFIDENCE

    @pytest.mark.asyncio
    async def test_async_unknown_gives_zero_confidence(self):
        clf = HeuristicComplexityClassifier()
        v = await clf.classify("Hi, brauche mal kurz deine Hilfe mit irgendwas dazu")
        assert v.confidence == 0.0


# ---------------------------------------------------------------------------
# Two-stage chained classifier
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestTwoStageRouting:
    """The two-stage classifier short-circuits on heuristic hits and only
    calls the LLM on UNKNOWN."""

    async def test_simple_via_heuristic_no_llm_call(self):
        heuristic = HeuristicComplexityClassifier()
        llm_clf = MissionComplexityClassifier.__new__(MissionComplexityClassifier)
        llm_clf.classify = AsyncMock(return_value=ComplexityVerdict("complex", 0.99, "x"))

        two_stage = TwoStageComplexityClassifier(heuristic, llm_clf)
        v = await two_stage.classify("Was ist 17 mal 23?")

        assert v.level == "simple"
        llm_clf.classify.assert_not_called(), \
            "LLM must NOT be called when heuristic is decisive"

    async def test_complex_via_heuristic_no_llm_call(self):
        heuristic = HeuristicComplexityClassifier()
        llm_clf = MissionComplexityClassifier.__new__(MissionComplexityClassifier)
        llm_clf.classify = AsyncMock(return_value=ComplexityVerdict("simple", 0.99, "x"))

        two_stage = TwoStageComplexityClassifier(heuristic, llm_clf)
        v = await two_stage.classify(
            "Vergleiche die Top 3 Elektroautos unter 40k Euro."
        )

        assert v.level == "complex"
        llm_clf.classify.assert_not_called()

    async def test_unknown_escalates_to_llm(self):
        heuristic = HeuristicComplexityClassifier()
        llm_clf = MissionComplexityClassifier.__new__(MissionComplexityClassifier)
        llm_clf.classify = AsyncMock(
            return_value=ComplexityVerdict("simple", 0.7, "lookup"),
        )

        two_stage = TwoStageComplexityClassifier(heuristic, llm_clf)
        v = await two_stage.classify(
            "Hi, brauche mal kurz deine Hilfe mit irgendwas Wichtigem dazu"
        )

        llm_clf.classify.assert_called_once()
        assert v.level == "simple"
        assert "llm_fallback" in v.reason


# ---------------------------------------------------------------------------
# Factory integration
# ---------------------------------------------------------------------------


class TestFactoryClassifierModes:
    def test_two_stage_is_default(self):
        from taskforce.application.planning_strategy_factory import select_planning_strategy

        llm = AsyncMock()
        llm.complete_json = AsyncMock()
        strat = select_planning_strategy("adaptive", llm_provider=llm)
        assert isinstance(strat.classifier, TwoStageComplexityClassifier)

    def test_llm_mode_picks_llm_only(self):
        from taskforce.application.planning_strategy_factory import select_planning_strategy

        llm = AsyncMock()
        llm.complete_json = AsyncMock()
        strat = select_planning_strategy(
            "adaptive",
            params={"classifier_mode": "llm"},
            llm_provider=llm,
        )
        assert isinstance(strat.classifier, MissionComplexityClassifier)

    def test_heuristic_mode_picks_heuristic_only(self):
        from taskforce.application.planning_strategy_factory import select_planning_strategy

        llm = AsyncMock()
        llm.complete_json = AsyncMock()
        strat = select_planning_strategy(
            "adaptive",
            params={"classifier_mode": "heuristic"},
            llm_provider=llm,
        )
        assert isinstance(strat.classifier, HeuristicComplexityClassifier)

    def test_invalid_classifier_mode_raises(self):
        from taskforce.application.planning_strategy_factory import select_planning_strategy

        llm = AsyncMock()
        llm.complete_json = AsyncMock()
        with pytest.raises(ValueError, match="Invalid classifier_mode"):
            select_planning_strategy(
                "adaptive",
                params={"classifier_mode": "nonsense"},
                llm_provider=llm,
            )
