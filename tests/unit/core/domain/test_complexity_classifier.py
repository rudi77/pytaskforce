"""Tests for MissionComplexityClassifier."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from taskforce.core.domain.complexity_classifier import (
    MissionComplexityClassifier,
    ComplexityVerdict,
)


@pytest.fixture
def llm_with_complete_json():
    """LLM that has complete_json (the preferred path)."""
    llm = MagicMock()
    llm.complete_json = AsyncMock()
    return llm


@pytest.fixture
def llm_without_complete_json():
    """LLM that only has complete() (the fallback path)."""
    llm = MagicMock(spec=["complete"])  # explicitly no complete_json
    llm.complete = AsyncMock()
    return llm


@pytest.mark.asyncio
class TestClassifierHappyPath:
    """Classifier returns a SIMPLE or COMPLEX verdict based on LLM output."""

    async def test_simple_verdict(self, llm_with_complete_json):
        llm_with_complete_json.complete_json.return_value = {
            "success": True,
            "data": {"level": "simple", "confidence": 0.9, "reason": "one step"},
        }
        clf = MissionComplexityClassifier(llm_with_complete_json)
        verdict = await clf.classify("set a reminder for 8pm")
        assert verdict.level == "simple"
        assert verdict.is_simple is True
        assert verdict.confidence == 0.9
        assert "one step" in verdict.reason

    async def test_complex_verdict(self, llm_with_complete_json):
        llm_with_complete_json.complete_json.return_value = {
            "success": True,
            "data": {"level": "complex", "confidence": 0.85, "reason": "multi step"},
        }
        clf = MissionComplexityClassifier(llm_with_complete_json)
        verdict = await clf.classify("plan my trip to Berlin")
        assert verdict.level == "complex"
        assert verdict.is_simple is False

    async def test_confidence_clamped_to_unit_interval(self, llm_with_complete_json):
        llm_with_complete_json.complete_json.return_value = {
            "success": True,
            "data": {"level": "simple", "confidence": 1.7, "reason": "high"},
        }
        clf = MissionComplexityClassifier(llm_with_complete_json)
        verdict = await clf.classify("x")
        assert 0.0 <= verdict.confidence <= 1.0


@pytest.mark.asyncio
class TestClassifierFallback:
    """All failure modes fall back to COMPLEX with confidence 0.0."""

    async def test_empty_mission(self, llm_with_complete_json):
        clf = MissionComplexityClassifier(llm_with_complete_json)
        verdict = await clf.classify("")
        assert verdict.level == "complex"
        assert verdict.confidence == 0.0
        llm_with_complete_json.complete_json.assert_not_called()

    async def test_llm_exception(self, llm_with_complete_json):
        llm_with_complete_json.complete_json.side_effect = RuntimeError("api down")
        clf = MissionComplexityClassifier(llm_with_complete_json)
        verdict = await clf.classify("anything")
        assert verdict.level == "complex"
        assert verdict.confidence == 0.0

    async def test_unsuccessful_llm_response(self, llm_with_complete_json):
        llm_with_complete_json.complete_json.return_value = {
            "success": False, "error": "rate limited",
        }
        clf = MissionComplexityClassifier(llm_with_complete_json)
        verdict = await clf.classify("x")
        assert verdict.level == "complex"
        assert verdict.confidence == 0.0

    async def test_invalid_level_falls_back_to_complex(self, llm_with_complete_json):
        llm_with_complete_json.complete_json.return_value = {
            "success": True,
            "data": {"level": "totally-invalid", "confidence": 0.9, "reason": "x"},
        }
        clf = MissionComplexityClassifier(llm_with_complete_json)
        verdict = await clf.classify("x")
        assert verdict.level == "complex"

    async def test_complete_path_when_complete_json_missing(self, llm_without_complete_json):
        """Provider without complete_json uses complete() and parses JSON."""
        llm_without_complete_json.complete.return_value = {
            "content": '{"level": "simple", "confidence": 0.7, "reason": "lookup"}',
        }
        clf = MissionComplexityClassifier(llm_without_complete_json)
        verdict = await clf.classify("how late is it")
        assert verdict.level == "simple"
        assert verdict.confidence == 0.7

    async def test_complete_path_malformed_json(self, llm_without_complete_json):
        llm_without_complete_json.complete.return_value = {"content": "definitely not json"}
        clf = MissionComplexityClassifier(llm_without_complete_json)
        verdict = await clf.classify("x")
        assert verdict.level == "complex"  # fallback


@pytest.mark.asyncio
class TestTruncation:
    """Long missions are truncated before being sent to the LLM."""

    async def test_truncates_long_mission(self, llm_with_complete_json):
        llm_with_complete_json.complete_json.return_value = {
            "success": True,
            "data": {"level": "simple", "confidence": 0.5, "reason": "ok"},
        }
        clf = MissionComplexityClassifier(
            llm_with_complete_json, max_mission_chars=50,
        )
        await clf.classify("X" * 1000)
        sent_messages = llm_with_complete_json.complete_json.call_args.kwargs["messages"]
        user_content = sent_messages[1]["content"]
        assert len(user_content) == 50
