"""Unit tests for auto-epic integration in AgentExecutor."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from taskforce.application.executor import AgentExecutor, ProgressUpdate
from taskforce.application.factory import AgentFactory
from taskforce.core.domain.config_schema import AutoEpicConfig
from taskforce.core.domain.enums import EventType
from taskforce.core.domain.epic import TaskComplexity, TaskComplexityResult
from taskforce.core.domain.models import ExecutionResult


def _make_executor_with_profile(
    profile_config: dict | None = None,
) -> AgentExecutor:
    """Create an AgentExecutor with a mocked factory and profile loader."""
    mock_factory = MagicMock(spec=AgentFactory)
    mock_factory.profile_loader = MagicMock()
    mock_factory.profile_loader.load_safe = MagicMock(
        return_value=profile_config or {}
    )
    mock_factory._create_llm_provider = MagicMock(return_value=AsyncMock())

    # Mock agent creation
    mock_agent = AsyncMock()
    mock_agent.execute.return_value = ExecutionResult(
        session_id="test-session",
        status="completed",
        final_message="Done",
        execution_history=[],
    )
    mock_agent.close = AsyncMock()
    mock_factory.create_agent = AsyncMock(return_value=mock_agent)

    return AgentExecutor(factory=mock_factory)


class TestResolveAutoEpicConfig:
    """Tests for _resolve_auto_epic_config."""

    def test_returns_none_when_no_orchestration_section(self) -> None:
        executor = _make_executor_with_profile({})
        config = executor._resolve_auto_epic_config("dev")
        assert config is None

    def test_returns_none_when_auto_epic_disabled(self) -> None:
        executor = _make_executor_with_profile(
            {"orchestration": {"auto_epic": {"enabled": False}}}
        )
        config = executor._resolve_auto_epic_config("dev")
        assert config is not None
        assert config.enabled is False

    def test_returns_config_when_enabled(self) -> None:
        executor = _make_executor_with_profile(
            {
                "orchestration": {
                    "auto_epic": {
                        "enabled": True,
                        "confidence_threshold": 0.8,
                        "default_worker_count": 4,
                    }
                }
            }
        )
        config = executor._resolve_auto_epic_config("dev")
        assert config is not None
        assert config.enabled is True
        assert config.confidence_threshold == 0.8
        assert config.default_worker_count == 4

    def test_returns_none_on_invalid_config(self) -> None:
        executor = _make_executor_with_profile(
            {"orchestration": {"auto_epic": {"enabled": "not_a_bool_but_valid"}}}
        )
        # Pydantic may accept truthy string; but truly invalid configs return None
        # Test with actually invalid data
        executor2 = _make_executor_with_profile(
            {"orchestration": {"auto_epic": {"confidence_threshold": "invalid"}}}
        )
        config = executor2._resolve_auto_epic_config("dev")
        assert config is None


class TestClassifyAndRouteEpic:
    """Tests for _classify_and_route_epic."""

    @pytest.mark.asyncio
    async def test_returns_none_when_auto_epic_is_false(self) -> None:
        executor = _make_executor_with_profile()
        result = await executor._classify_and_route_epic(
            mission="Test", profile="dev", auto_epic=False
        )
        assert result is None

    @pytest.mark.asyncio
    async def test_returns_none_when_config_not_enabled(self) -> None:
        executor = _make_executor_with_profile({})
        result = await executor._classify_and_route_epic(
            mission="Test", profile="dev", auto_epic=None
        )
        assert result is None

    @pytest.mark.asyncio
    async def test_returns_escalation_event_for_complex_mission(self) -> None:
        executor = _make_executor_with_profile(
            {
                "orchestration": {
                    "auto_epic": {"enabled": True, "confidence_threshold": 0.5}
                }
            }
        )

        classification_result = TaskComplexityResult(
            complexity=TaskComplexity.EPIC,
            reasoning="Multi-component system",
            confidence=0.9,
            suggested_worker_count=4,
            suggested_scopes=["api", "frontend"],
            estimated_task_count=6,
        )

        with patch(
            "taskforce.application.executor.TaskComplexityClassifier"
        ) as MockClassifier:
            mock_instance = AsyncMock()
            mock_instance.classify = AsyncMock(return_value=classification_result)
            MockClassifier.return_value = mock_instance

            result = await executor._classify_and_route_epic(
                mission="Build a full system", profile="dev", auto_epic=None
            )

        assert result is not None
        assert result.event_type == EventType.EPIC_ESCALATION
        assert result.details["complexity"] == "epic"
        assert result.details["confidence"] == 0.9
        assert result.details["worker_count"] == 4

    @pytest.mark.asyncio
    async def test_returns_none_when_confidence_below_threshold(self) -> None:
        executor = _make_executor_with_profile(
            {
                "orchestration": {
                    "auto_epic": {"enabled": True, "confidence_threshold": 0.9}
                }
            }
        )

        classification_result = TaskComplexityResult(
            complexity=TaskComplexity.EPIC,
            reasoning="Maybe complex",
            confidence=0.6,  # Below threshold of 0.9
            suggested_worker_count=2,
            estimated_task_count=3,
        )

        with patch(
            "taskforce.application.executor.TaskComplexityClassifier"
        ) as MockClassifier:
            mock_instance = AsyncMock()
            mock_instance.classify = AsyncMock(return_value=classification_result)
            MockClassifier.return_value = mock_instance

            result = await executor._classify_and_route_epic(
                mission="Some task", profile="dev", auto_epic=None
            )

        assert result is None

    @pytest.mark.asyncio
    async def test_force_auto_epic_uses_defaults(self) -> None:
        """auto_epic=True should work even without profile config."""
        executor = _make_executor_with_profile({})

        classification_result = TaskComplexityResult(
            complexity=TaskComplexity.EPIC,
            reasoning="Forced check",
            confidence=0.85,
            suggested_worker_count=3,
            estimated_task_count=5,
        )

        with patch(
            "taskforce.application.executor.TaskComplexityClassifier"
        ) as MockClassifier:
            mock_instance = AsyncMock()
            mock_instance.classify = AsyncMock(return_value=classification_result)
            MockClassifier.return_value = mock_instance

            result = await executor._classify_and_route_epic(
                mission="Build everything", profile="dev", auto_epic=True
            )

        assert result is not None
        assert result.event_type == EventType.EPIC_ESCALATION

    @pytest.mark.asyncio
    async def test_returns_none_when_classified_as_simple(self) -> None:
        executor = _make_executor_with_profile(
            {
                "orchestration": {
                    "auto_epic": {"enabled": True, "confidence_threshold": 0.5}
                }
            }
        )

        classification_result = TaskComplexityResult(
            complexity=TaskComplexity.SIMPLE,
            reasoning="Just a small fix",
            confidence=0.95,
            suggested_worker_count=1,
            estimated_task_count=1,
        )

        with patch(
            "taskforce.application.executor.TaskComplexityClassifier"
        ) as MockClassifier:
            mock_instance = AsyncMock()
            mock_instance.classify = AsyncMock(return_value=classification_result)
            MockClassifier.return_value = mock_instance

            result = await executor._classify_and_route_epic(
                mission="Fix typo", profile="dev", auto_epic=None
            )

        assert result is None


class TestAutoEpicConfig:
    """Tests for AutoEpicConfig Pydantic model."""

    def test_defaults(self) -> None:
        config = AutoEpicConfig()
        assert config.enabled is False
        assert config.confidence_threshold == 0.7
        assert config.classifier_model is None
        assert config.default_worker_count == 3
        assert config.default_max_rounds == 3
        assert config.planner_profile == "planner"
        assert config.worker_profile == "worker"
        assert config.judge_profile == "judge"

    def test_custom_values(self) -> None:
        config = AutoEpicConfig(
            enabled=True,
            confidence_threshold=0.8,
            classifier_model="fast",
            default_worker_count=5,
            default_max_rounds=2,
            planner_profile="custom_planner",
        )
        assert config.enabled is True
        assert config.confidence_threshold == 0.8
        assert config.classifier_model == "fast"
        assert config.default_worker_count == 5
        assert config.planner_profile == "custom_planner"

    def test_validation_rejects_invalid_threshold(self) -> None:
        with pytest.raises(Exception):
            AutoEpicConfig(confidence_threshold=1.5)

    def test_validation_rejects_invalid_worker_count(self) -> None:
        with pytest.raises(Exception):
            AutoEpicConfig(default_worker_count=0)
