"""Tests for ConsolidationService."""

from datetime import UTC, datetime
from unittest.mock import AsyncMock

import pytest

from taskforce.application.consolidation_service import (
    ConsolidationService,
    build_consolidation_components,
)
from taskforce.core.domain.experience import ConsolidationResult, SessionExperience


@pytest.fixture
def mock_experience_store():
    store = AsyncMock()
    store.load_experience = AsyncMock(return_value=None)
    store.list_experiences = AsyncMock(return_value=[])
    store.mark_processed = AsyncMock()
    store.save_consolidation = AsyncMock()
    store.list_consolidations = AsyncMock(return_value=[])
    return store


@pytest.fixture
def mock_engine():
    engine = AsyncMock()
    engine.consolidate = AsyncMock(
        return_value=ConsolidationResult(
            consolidation_id="test-consol",
            sessions_processed=1,
            memories_created=2,
        )
    )
    return engine


@pytest.fixture
def mock_memory_store():
    store = AsyncMock()
    store.list = AsyncMock(return_value=[])
    return store


@pytest.fixture
def service(mock_experience_store, mock_engine, mock_memory_store):
    return ConsolidationService(
        experience_store=mock_experience_store,
        consolidation_engine=mock_engine,
        memory_store=mock_memory_store,
    )


def _make_experience(session_id: str = "sess-1") -> SessionExperience:
    return SessionExperience(
        session_id=session_id,
        profile="dev",
        mission="Test",
        started_at=datetime.now(UTC),
    )


class TestConsolidationService:
    async def test_trigger_consolidation_no_experiences(self, service, mock_experience_store):
        result = await service.trigger_consolidation()
        assert result.sessions_processed == 0
        mock_experience_store.list_experiences.assert_awaited_once()

    async def test_trigger_consolidation_with_experiences(
        self, service, mock_experience_store, mock_engine
    ):
        exp = _make_experience()
        mock_experience_store.list_experiences = AsyncMock(return_value=[exp])

        result = await service.trigger_consolidation()

        assert result.consolidation_id == "test-consol"
        mock_engine.consolidate.assert_awaited_once()
        mock_experience_store.mark_processed.assert_awaited_once()

    async def test_trigger_consolidation_specific_sessions(self, service, mock_experience_store):
        exp = _make_experience("sess-42")
        mock_experience_store.load_experience = AsyncMock(return_value=exp)

        await service.trigger_consolidation(session_ids=["sess-42"])

        mock_experience_store.load_experience.assert_awaited_with("sess-42")

    async def test_post_execution_hook_disabled(
        self, mock_experience_store, mock_engine, mock_memory_store
    ):
        """When auto_consolidate is False, hook is a no-op."""
        service = ConsolidationService(
            experience_store=mock_experience_store,
            consolidation_engine=mock_engine,
            memory_store=mock_memory_store,
            auto_consolidate=False,
        )
        exp = _make_experience()
        await service.post_execution_hook("sess-1", exp)
        mock_engine.consolidate.assert_not_awaited()

    async def test_post_execution_hook_enabled(
        self, mock_experience_store, mock_engine, mock_memory_store
    ):
        """When auto_consolidate is True, hook triggers consolidation."""
        service = ConsolidationService(
            experience_store=mock_experience_store,
            consolidation_engine=mock_engine,
            memory_store=mock_memory_store,
            auto_consolidate=True,
        )
        exp = _make_experience()
        mock_experience_store.load_experience = AsyncMock(return_value=exp)

        await service.post_execution_hook("sess-1", exp)
        mock_engine.consolidate.assert_awaited_once()

    async def test_get_consolidation_history(self, service, mock_experience_store):
        mock_experience_store.list_consolidations = AsyncMock(
            return_value=[
                ConsolidationResult(consolidation_id="c1"),
                ConsolidationResult(consolidation_id="c2"),
            ]
        )
        results = await service.get_consolidation_history(limit=5)
        assert len(results) == 2


class TestBuildConsolidationComponents:
    def test_explicitly_disabled_returns_none(self):
        config = {"consolidation": {"enabled": False, "auto_capture": False}}
        tracker, service = build_consolidation_components(config)
        assert tracker is None
        assert service is None

    def test_missing_config_creates_tracker_via_default_auto_capture(self):
        config = {}
        tracker, service = build_consolidation_components(config)
        assert tracker is not None
        assert service is None  # No LLM provider

    def test_enabled_without_llm_creates_tracker_only(self):
        config = {
            "consolidation": {"enabled": True, "work_dir": "/tmp/test_exp"},
            "persistence": {"work_dir": "/tmp/test_mem"},
        }
        tracker, service = build_consolidation_components(config)
        assert tracker is not None
        assert service is None  # No LLM provider

    def test_enabled_with_llm_creates_both(self):
        config = {
            "consolidation": {"enabled": True, "work_dir": "/tmp/test_exp2"},
            "persistence": {"work_dir": "/tmp/test_mem2"},
        }
        mock_llm = AsyncMock()
        tracker, service = build_consolidation_components(config, mock_llm)
        assert tracker is not None
        assert service is not None
