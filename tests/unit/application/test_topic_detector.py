"""Tests for the TopicDetector service."""

import json
from unittest.mock import AsyncMock

import pytest

from taskforce.application.topic_detector import TopicChange, TopicDetector


def _make_llm(response_content: str) -> AsyncMock:
    """Create a mock LLM provider returning the given content."""
    llm = AsyncMock()
    llm.complete = AsyncMock(return_value={"content": response_content})
    return llm


class TestTopicDetector:
    """Tests for TopicDetector."""

    async def test_no_current_label_always_creates_topic(self) -> None:
        llm = _make_llm("Test conversation")
        detector = TopicDetector(llm)
        result = await detector.detect(
            message="Hello, how are you?",
            current_label=None,
        )
        assert result is not None
        assert result.confidence == 1.0
        assert result.label == "Test conversation"

    async def test_topic_change_detected(self) -> None:
        response = json.dumps({
            "changed": True,
            "label": "Budget discussion",
            "confidence": 0.9,
        })
        llm = _make_llm(response)
        detector = TopicDetector(llm)
        result = await detector.detect(
            message="Let's talk about the budget now",
            current_label="Project timeline",
            recent_messages=[
                {"role": "user", "content": "When is the deadline?"},
                {"role": "assistant", "content": "The deadline is next Friday."},
            ],
        )
        assert result is not None
        assert result.label == "Budget discussion"
        assert result.confidence == 0.9

    async def test_no_topic_change(self) -> None:
        response = json.dumps({
            "changed": False,
            "label": "",
            "confidence": 0.1,
        })
        llm = _make_llm(response)
        detector = TopicDetector(llm)
        result = await detector.detect(
            message="What about the milestones?",
            current_label="Project timeline",
        )
        assert result is None

    async def test_low_confidence_ignored(self) -> None:
        response = json.dumps({
            "changed": True,
            "label": "Maybe new topic",
            "confidence": 0.4,
        })
        llm = _make_llm(response)
        detector = TopicDetector(llm, confidence_threshold=0.7)
        result = await detector.detect(
            message="Hmm, interesting",
            current_label="Current topic",
        )
        assert result is None

    async def test_custom_threshold(self) -> None:
        response = json.dumps({
            "changed": True,
            "label": "New topic",
            "confidence": 0.5,
        })
        llm = _make_llm(response)
        detector = TopicDetector(llm, confidence_threshold=0.3)
        result = await detector.detect(
            message="Something else",
            current_label="Old topic",
        )
        assert result is not None
        assert result.label == "New topic"

    async def test_llm_error_returns_none(self) -> None:
        llm = AsyncMock()
        llm.complete = AsyncMock(side_effect=RuntimeError("LLM down"))
        detector = TopicDetector(llm)
        result = await detector.detect(
            message="Hello",
            current_label="Current topic",
        )
        assert result is None

    async def test_malformed_json_returns_none(self) -> None:
        llm = _make_llm("not valid json at all")
        detector = TopicDetector(llm)
        result = await detector.detect(
            message="Hello",
            current_label="Current topic",
        )
        assert result is None

    async def test_markdown_wrapped_json(self) -> None:
        response = "```json\n" + json.dumps({
            "changed": True,
            "label": "New topic",
            "confidence": 0.85,
        }) + "\n```"
        llm = _make_llm(response)
        detector = TopicDetector(llm)
        result = await detector.detect(
            message="Let's switch",
            current_label="Old topic",
        )
        assert result is not None
        assert result.label == "New topic"

    async def test_generate_summary(self) -> None:
        llm = _make_llm("We discussed the project timeline and key milestones.")
        detector = TopicDetector(llm)
        summary = await detector.generate_summary(
            messages=[
                {"role": "user", "content": "When is the deadline?"},
                {"role": "assistant", "content": "Next Friday."},
            ],
            label="Project timeline",
        )
        assert "timeline" in summary.lower() or "milestones" in summary.lower()

    async def test_generate_summary_error_fallback(self) -> None:
        llm = AsyncMock()
        llm.complete = AsyncMock(side_effect=RuntimeError("LLM error"))
        detector = TopicDetector(llm)
        summary = await detector.generate_summary(
            messages=[{"role": "user", "content": "test"}],
            label="Test topic",
        )
        assert summary == "Discussion about Test topic"


class TestTopicChange:
    """Tests for the TopicChange dataclass."""

    def test_creation(self) -> None:
        tc = TopicChange(label="New topic", confidence=0.85)
        assert tc.label == "New topic"
        assert tc.confidence == 0.85

    def test_frozen(self) -> None:
        tc = TopicChange(label="Test", confidence=0.5)
        with pytest.raises(AttributeError):
            tc.label = "Changed"
