"""Tests for TaskComplexityClassifier."""

import pytest
from unittest.mock import AsyncMock, MagicMock

from taskforce.application.task_complexity_classifier import (
    ComplexityClassification,
    TaskComplexityClassifier,
    _COMPLEX_FALLBACK,
)


@pytest.fixture
def mock_llm():
    llm = AsyncMock()
    llm.complete_json = AsyncMock()
    return llm


@pytest.fixture
def classifier(mock_llm):
    return TaskComplexityClassifier(mock_llm, classification_model="fast")


@pytest.mark.asyncio
async def test_classify_simple_task(classifier, mock_llm):
    mock_llm.complete_json.return_value = {
        "success": True,
        "data": {"level": "simple", "confidence": 0.95, "reason": "single lookup"},
    }
    result = await classifier.classify("was ist 2+2")
    assert result.level == "simple"
    assert result.is_simple is True
    assert result.confidence == 0.95


@pytest.mark.asyncio
async def test_classify_complex_task(classifier, mock_llm):
    mock_llm.complete_json.return_value = {
        "success": True,
        "data": {
            "level": "complex",
            "confidence": 0.88,
            "reason": "multi-step research",
        },
    }
    result = await classifier.classify("recherchiere 3 Cloud-Anbieter und vergleiche")
    assert result.level == "complex"
    assert result.is_simple is False


@pytest.mark.asyncio
async def test_fallback_on_llm_error(classifier, mock_llm):
    mock_llm.complete_json.side_effect = Exception("API timeout")
    result = await classifier.classify("some task")
    assert result.level == "complex"
    assert result.confidence == 0.0
    assert "fallback" in result.reason


@pytest.mark.asyncio
async def test_fallback_on_invalid_json(classifier, mock_llm):
    mock_llm.complete_json.return_value = {
        "success": False,
        "error": "parse error",
    }
    result = await classifier.classify("some task")
    assert result.level == "complex"


@pytest.mark.asyncio
async def test_fallback_on_empty_mission(classifier):
    result = await classifier.classify("")
    assert result.level == "complex"

    result = await classifier.classify("   ")
    assert result.level == "complex"


@pytest.mark.asyncio
async def test_invalid_level_defaults_to_complex(classifier, mock_llm):
    mock_llm.complete_json.return_value = {
        "success": True,
        "data": {"level": "medium", "confidence": 0.5, "reason": "unclear"},
    }
    result = await classifier.classify("do something")
    assert result.level == "complex"


@pytest.mark.asyncio
async def test_confidence_clamped(classifier, mock_llm):
    mock_llm.complete_json.return_value = {
        "success": True,
        "data": {"level": "simple", "confidence": 1.5, "reason": "very sure"},
    }
    result = await classifier.classify("hello")
    assert result.confidence == 1.0


@pytest.mark.asyncio
async def test_mission_truncated(mock_llm):
    classifier = TaskComplexityClassifier(
        mock_llm, max_mission_chars=10
    )
    mock_llm.complete_json.return_value = {
        "success": True,
        "data": {"level": "simple", "confidence": 0.9, "reason": "short"},
    }
    await classifier.classify("a" * 1000)
    # Verify the message sent to LLM was truncated
    call_args = mock_llm.complete_json.call_args
    messages = call_args.kwargs.get("messages", call_args.args[0] if call_args.args else [])
    user_msg = [m for m in messages if m["role"] == "user"][0]
    assert len(user_msg["content"]) == 10


@pytest.mark.asyncio
async def test_fallback_to_complete_when_no_complete_json(mock_llm):
    """When LLM has no complete_json, falls back to complete()."""
    del mock_llm.complete_json  # Remove complete_json
    mock_llm.complete = AsyncMock(return_value={
        "content": '{"level": "simple", "confidence": 0.8, "reason": "basic"}',
    })
    classifier = TaskComplexityClassifier(mock_llm)
    result = await classifier.classify("what time is it")
    assert result.level == "simple"
