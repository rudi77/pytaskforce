"""Unit tests for TaskComplexityClassifier."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock

import pytest

from taskforce.application.task_complexity_classifier import (
    TaskComplexityClassifier,
)
from taskforce.core.domain.epic import TaskComplexity


def _mock_llm(response_data: dict) -> AsyncMock:
    """Create a mock LLM provider returning a given JSON response."""
    llm = AsyncMock()
    llm.complete = AsyncMock(
        return_value={
            "success": True,
            "content": json.dumps(response_data),
        }
    )
    return llm


class TestTaskComplexityClassifier:
    """Tests for the complexity classifier."""

    @pytest.mark.asyncio
    async def test_simple_task_classified_correctly(self) -> None:
        llm = _mock_llm(
            {
                "complexity": "simple",
                "reasoning": "Single file bug fix",
                "confidence": 0.92,
                "suggested_worker_count": 1,
                "suggested_scopes": [],
                "estimated_task_count": 1,
            }
        )
        classifier = TaskComplexityClassifier(llm)
        result = await classifier.classify("Fix the typo in README.md")

        assert result.complexity == TaskComplexity.SIMPLE
        assert result.confidence == pytest.approx(0.92)
        assert result.suggested_worker_count == 1

    @pytest.mark.asyncio
    async def test_complex_task_classified_as_epic(self) -> None:
        llm = _mock_llm(
            {
                "complexity": "epic",
                "reasoning": "Multi-component system with API, DB, and frontend",
                "confidence": 0.95,
                "suggested_worker_count": 4,
                "suggested_scopes": ["api", "database", "frontend", "tests"],
                "estimated_task_count": 8,
            }
        )
        classifier = TaskComplexityClassifier(llm)
        result = await classifier.classify(
            "Build a complete user management system with REST API, "
            "database migrations, frontend forms, and integration tests"
        )

        assert result.complexity == TaskComplexity.EPIC
        assert result.confidence >= 0.7
        assert result.suggested_worker_count == 4
        assert result.estimated_task_count == 8
        assert "api" in result.suggested_scopes

    @pytest.mark.asyncio
    async def test_llm_error_falls_back_to_simple(self) -> None:
        llm = AsyncMock()
        llm.complete = AsyncMock(side_effect=RuntimeError("Connection failed"))

        classifier = TaskComplexityClassifier(llm)
        result = await classifier.classify("Some mission")

        assert result.complexity == TaskComplexity.SIMPLE
        assert result.confidence == 0.0

    @pytest.mark.asyncio
    async def test_llm_unsuccessful_falls_back_to_simple(self) -> None:
        llm = AsyncMock()
        llm.complete = AsyncMock(
            return_value={"success": False, "error": "Rate limit exceeded"}
        )

        classifier = TaskComplexityClassifier(llm)
        result = await classifier.classify("Some mission")

        assert result.complexity == TaskComplexity.SIMPLE

    @pytest.mark.asyncio
    async def test_invalid_json_falls_back_to_simple(self) -> None:
        llm = AsyncMock()
        llm.complete = AsyncMock(
            return_value={"success": True, "content": "Not valid JSON at all"}
        )

        classifier = TaskComplexityClassifier(llm)
        result = await classifier.classify("Some mission")

        assert result.complexity == TaskComplexity.SIMPLE
        assert result.confidence == 0.0

    @pytest.mark.asyncio
    async def test_markdown_fenced_json_parsed(self) -> None:
        """LLM sometimes wraps JSON in markdown code fences."""
        data = {
            "complexity": "epic",
            "reasoning": "Multiple components",
            "confidence": 0.88,
            "suggested_worker_count": 3,
            "suggested_scopes": [],
            "estimated_task_count": 5,
        }
        llm = AsyncMock()
        llm.complete = AsyncMock(
            return_value={
                "success": True,
                "content": f"```json\n{json.dumps(data)}\n```",
            }
        )

        classifier = TaskComplexityClassifier(llm)
        result = await classifier.classify("Build a whole system")

        assert result.complexity == TaskComplexity.EPIC
        assert result.confidence == pytest.approx(0.88)

    @pytest.mark.asyncio
    async def test_classifier_uses_specified_model(self) -> None:
        llm = _mock_llm(
            {
                "complexity": "simple",
                "reasoning": "Trivial task",
                "confidence": 0.99,
                "suggested_worker_count": 1,
                "suggested_scopes": [],
                "estimated_task_count": 1,
            }
        )
        classifier = TaskComplexityClassifier(llm, model="fast")
        await classifier.classify("Hello world")

        call_kwargs = llm.complete.call_args.kwargs
        assert call_kwargs["model"] == "fast"

    @pytest.mark.asyncio
    async def test_confidence_clamped_to_valid_range(self) -> None:
        llm = _mock_llm(
            {
                "complexity": "epic",
                "reasoning": "Very complex",
                "confidence": 1.5,  # Above valid range
                "suggested_worker_count": 3,
                "suggested_scopes": [],
                "estimated_task_count": 4,
            }
        )
        classifier = TaskComplexityClassifier(llm)
        result = await classifier.classify("Some complex task")

        assert result.confidence == 1.0

    @pytest.mark.asyncio
    async def test_worker_count_clamped_to_valid_range(self) -> None:
        llm = _mock_llm(
            {
                "complexity": "epic",
                "reasoning": "Huge project",
                "confidence": 0.9,
                "suggested_worker_count": 50,  # Above max
                "suggested_scopes": [],
                "estimated_task_count": 20,
            }
        )
        classifier = TaskComplexityClassifier(llm)
        result = await classifier.classify("Giant project")

        assert result.suggested_worker_count == 10  # Clamped to max

    @pytest.mark.asyncio
    async def test_unknown_complexity_value_falls_back(self) -> None:
        llm = _mock_llm(
            {
                "complexity": "unknown_value",
                "reasoning": "Not sure",
                "confidence": 0.5,
                "suggested_worker_count": 1,
                "suggested_scopes": [],
                "estimated_task_count": 1,
            }
        )
        classifier = TaskComplexityClassifier(llm)
        result = await classifier.classify("Something")

        assert result.complexity == TaskComplexity.SIMPLE
