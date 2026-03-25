"""Tests for the DreamService application layer."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock

import pytest

from taskforce.core.domain.dream import (
    DreamConfig,
    DreamCycle,
    DreamInsight,
    DreamInsightType,
    DreamStatus,
    DreamTrigger,
)
from taskforce.core.domain.memory import (
    EmotionalValence,
    MemoryKind,
    MemoryRecord,
    MemoryScope,
)
from taskforce.application.dream_service import DreamService, build_dream_components


# ------------------------------------------------------------------
# Fixtures
# ------------------------------------------------------------------


@pytest.fixture()
def mock_llm() -> AsyncMock:
    """Mock LLM provider."""
    llm = AsyncMock()
    llm.complete = AsyncMock(
        return_value={
            "content": (
                '{"narrative": "...", "key_learnings": ["learning1"],'
                ' "tool_patterns": ["p1"], "memory_kind": "semantic",'
                ' "emotional_valence": "positive", "importance": 0.7}'
            ),
            "usage": {"total_tokens": 100},
        }
    )
    return llm


@pytest.fixture()
def mock_memory_store() -> AsyncMock:
    """Mock memory store."""
    store = AsyncMock()
    store.list = AsyncMock(return_value=[])
    store.add = AsyncMock(side_effect=lambda r: r)
    store.update = AsyncMock(side_effect=lambda r: r)
    store.get = AsyncMock(return_value=None)
    store.flush = AsyncMock()
    return store


@pytest.fixture()
def mock_dream_engine() -> AsyncMock:
    """Mock dream engine returning a completed cycle with insights."""
    engine = AsyncMock()

    def _dream(memories, config):
        insight = DreamInsight(
            content="Cross-domain insight: caching patterns apply to API design.",
            source_memory_ids=["m1", "m2"],
            insight_type=DreamInsightType.RECOMBINATION,
            confidence=0.8,
            novelty_score=0.7,
            tags=["caching", "api"],
            emotional_valence=EmotionalValence.POSITIVE,
        )
        return DreamCycle(
            status=DreamStatus.COMPLETED,
            ended_at=datetime.now(UTC),
            insights=[insight],
            memories_processed=len(memories),
            total_tokens=150,
        )

    engine.dream = AsyncMock(side_effect=_dream)
    return engine


@pytest.fixture()
def dream_config() -> DreamConfig:
    """Default enabled dream config for testing."""
    return DreamConfig(enabled=True)


@pytest.fixture()
def dream_service(
    mock_dream_engine: AsyncMock,
    mock_memory_store: AsyncMock,
    dream_config: DreamConfig,
    tmp_path,
) -> DreamService:
    """DreamService with mocked dependencies and tmp_path work dir."""
    return DreamService(
        dream_engine=mock_dream_engine,
        memory_store=mock_memory_store,
        config=dream_config,
        work_dir=str(tmp_path),
    )


def _make_active_memory(content: str = "active memory", tags: list[str] | None = None) -> MemoryRecord:
    """Create a MemoryRecord that passes the active filter (no archived tag, high strength)."""
    return MemoryRecord(
        scope=MemoryScope.USER,
        kind=MemoryKind.CONSOLIDATED,
        content=content,
        tags=tags or [],
        strength=0.8,
        importance=0.5,
    )


# ------------------------------------------------------------------
# trigger_dream() with mock engine
# ------------------------------------------------------------------


async def test_trigger_dream_calls_engine(
    dream_service: DreamService,
    mock_dream_engine: AsyncMock,
    mock_memory_store: AsyncMock,
):
    """trigger_dream should call the dream engine with active memories."""
    active = _make_active_memory()
    mock_memory_store.list.return_value = [active]

    cycle = await dream_service.trigger_dream()

    mock_dream_engine.dream.assert_called_once()
    assert cycle.status == DreamStatus.COMPLETED
    assert cycle.memories_processed == 1
    assert len(cycle.insights) == 1


async def test_trigger_dream_uses_override_config(
    dream_service: DreamService,
    mock_dream_engine: AsyncMock,
    mock_memory_store: AsyncMock,
):
    """Override config should be passed to the engine."""
    mock_memory_store.list.return_value = [_make_active_memory()]
    override = DreamConfig(enabled=True, max_llm_calls=2)

    await dream_service.trigger_dream(config=override)

    _, call_kwargs = mock_dream_engine.dream.call_args
    # The config is passed as positional arg
    call_args = mock_dream_engine.dream.call_args[0]
    assert call_args[1].max_llm_calls == 2


async def test_trigger_dream_sets_trigger(
    dream_service: DreamService,
    mock_memory_store: AsyncMock,
):
    """The trigger field should be set on the returned cycle."""
    mock_memory_store.list.return_value = [_make_active_memory()]

    cycle = await dream_service.trigger_dream(trigger=DreamTrigger.SCHEDULED)

    assert cycle.trigger == DreamTrigger.SCHEDULED


# ------------------------------------------------------------------
# Insight persistence: insights saved as MemoryRecord(kind=CONSOLIDATED)
# ------------------------------------------------------------------


async def test_insights_persisted_as_consolidated_memories(
    dream_service: DreamService,
    mock_memory_store: AsyncMock,
):
    """Dream insights should be saved as CONSOLIDATED memory records."""
    mock_memory_store.list.return_value = [_make_active_memory()]

    cycle = await dream_service.trigger_dream()

    assert cycle.memories_created == 1
    mock_memory_store.add.assert_called_once()

    record = mock_memory_store.add.call_args[0][0]
    assert isinstance(record, MemoryRecord)
    assert record.kind == MemoryKind.CONSOLIDATED
    assert record.content == "Cross-domain insight: caching patterns apply to API design."
    assert "dreaming" in record.tags
    assert record.metadata["source"] == "dreaming"
    assert record.metadata["insight_type"] == "recombination"
    assert record.metadata["source_memory_ids"] == ["m1", "m2"]
    assert record.emotional_valence == EmotionalValence.POSITIVE


async def test_insights_importance_equals_confidence(
    dream_service: DreamService,
    mock_memory_store: AsyncMock,
):
    """The importance of persisted insight records should match confidence."""
    mock_memory_store.list.return_value = [_make_active_memory()]

    await dream_service.trigger_dream()

    record = mock_memory_store.add.call_args[0][0]
    assert record.importance == 0.8  # matches insight confidence


# ------------------------------------------------------------------
# Dream history: save and retrieve cycles
# ------------------------------------------------------------------


async def test_save_and_retrieve_dream_cycle(
    dream_service: DreamService,
    mock_memory_store: AsyncMock,
):
    """A completed dream cycle should be retrievable from disk."""
    mock_memory_store.list.return_value = [_make_active_memory()]

    cycle = await dream_service.trigger_dream()
    dream_id = cycle.dream_id

    # Retrieve by ID
    loaded = await dream_service.get_dream(dream_id)

    assert loaded is not None
    assert loaded.dream_id == dream_id
    assert loaded.status == DreamStatus.COMPLETED
    assert len(loaded.insights) == 1


async def test_get_dream_history(
    dream_service: DreamService,
    mock_memory_store: AsyncMock,
):
    """Dream history should return cycles ordered most recent first."""
    mock_memory_store.list.return_value = [_make_active_memory()]

    cycle1 = await dream_service.trigger_dream()
    cycle2 = await dream_service.trigger_dream()

    history = await dream_service.get_dream_history(limit=10)

    assert len(history) == 2
    # Files are sorted reverse alphabetically by filename (uuid hex)
    dream_ids = {c.dream_id for c in history}
    assert cycle1.dream_id in dream_ids
    assert cycle2.dream_id in dream_ids


async def test_get_dream_not_found(dream_service: DreamService):
    """get_dream should return None for nonexistent dream ID."""
    result = await dream_service.get_dream("nonexistent-id")
    assert result is None


async def test_get_dream_history_empty(dream_service: DreamService):
    """Dream history should return empty list when no dreams exist."""
    history = await dream_service.get_dream_history()
    assert history == []


# ------------------------------------------------------------------
# Empty memories => early return
# ------------------------------------------------------------------


async def test_empty_memories_returns_completed_no_insights(
    dream_service: DreamService,
    mock_dream_engine: AsyncMock,
    mock_memory_store: AsyncMock,
):
    """When no active memories exist, return completed cycle with no insights."""
    mock_memory_store.list.return_value = []

    cycle = await dream_service.trigger_dream()

    assert cycle.status == DreamStatus.COMPLETED
    assert cycle.insights == []
    assert cycle.ended_at is not None
    # Engine should not be called
    mock_dream_engine.dream.assert_not_called()


async def test_archived_memories_filtered_out(
    dream_service: DreamService,
    mock_dream_engine: AsyncMock,
    mock_memory_store: AsyncMock,
):
    """Memories with 'archived' tag should be filtered out before dreaming."""
    archived = _make_active_memory()
    archived.tags.append("archived")
    mock_memory_store.list.return_value = [archived]

    cycle = await dream_service.trigger_dream()

    assert cycle.status == DreamStatus.COMPLETED
    assert cycle.insights == []
    mock_dream_engine.dream.assert_not_called()


async def test_weak_memories_filtered_out(
    dream_service: DreamService,
    mock_dream_engine: AsyncMock,
    mock_memory_store: AsyncMock,
):
    """Memories with effective_strength <= 0.15 should be filtered out."""
    weak = MemoryRecord(
        scope=MemoryScope.USER,
        kind=MemoryKind.CONSOLIDATED,
        content="very weak memory",
        strength=0.01,
        importance=0.0,
    )
    mock_memory_store.list.return_value = [weak]

    cycle = await dream_service.trigger_dream()

    assert cycle.status == DreamStatus.COMPLETED
    mock_dream_engine.dream.assert_not_called()


# ------------------------------------------------------------------
# Flush called
# ------------------------------------------------------------------


async def test_trigger_dream_flushes_store(
    dream_service: DreamService,
    mock_memory_store: AsyncMock,
):
    """Memory store flush should be called after persisting insights."""
    mock_memory_store.list.return_value = [_make_active_memory()]

    await dream_service.trigger_dream()

    mock_memory_store.flush.assert_called_once()


# ------------------------------------------------------------------
# Disabled config skips persistence
# ------------------------------------------------------------------


async def test_disabled_config_skips_insight_persistence(
    mock_dream_engine: AsyncMock,
    mock_memory_store: AsyncMock,
    tmp_path,
):
    """When config.enabled is False, insights should not be persisted."""
    disabled_config = DreamConfig(enabled=False)
    service = DreamService(
        dream_engine=mock_dream_engine,
        memory_store=mock_memory_store,
        config=disabled_config,
        work_dir=str(tmp_path),
    )
    mock_memory_store.list.return_value = [_make_active_memory()]

    cycle = await service.trigger_dream()

    # Engine is called but insights are not persisted
    mock_dream_engine.dream.assert_called_once()
    assert cycle.memories_created == 0
    # add should not be called for insights (only triggered when enabled)
    mock_memory_store.add.assert_not_called()


# ------------------------------------------------------------------
# build_dream_components()
# ------------------------------------------------------------------


def test_build_dream_components_returns_none_when_disabled():
    """Should return None when dreaming is not enabled in config."""
    config = {"dreaming": {"enabled": False}}
    result = build_dream_components(config, llm_provider=AsyncMock(), memory_store=AsyncMock())
    assert result is None


def test_build_dream_components_returns_none_when_no_dreaming_section():
    """Should return None when dreaming section is missing."""
    result = build_dream_components({}, llm_provider=AsyncMock(), memory_store=AsyncMock())
    assert result is None


def test_build_dream_components_returns_none_when_no_llm():
    """Should return None when llm_provider is missing."""
    config = {"dreaming": {"enabled": True}}
    result = build_dream_components(config, llm_provider=None, memory_store=AsyncMock())
    assert result is None


def test_build_dream_components_returns_none_when_no_store():
    """Should return None when memory_store is missing."""
    config = {"dreaming": {"enabled": True}}
    result = build_dream_components(config, llm_provider=AsyncMock(), memory_store=None)
    assert result is None


def test_build_dream_components_returns_service_when_enabled():
    """Should return a configured DreamService when enabled with deps."""
    config = {
        "dreaming": {"enabled": True, "max_llm_calls": 8},
        "persistence": {"work_dir": "/tmp/test_dreams"},
    }
    service = build_dream_components(
        config, llm_provider=AsyncMock(), memory_store=AsyncMock()
    )

    assert isinstance(service, DreamService)


def test_build_dream_components_uses_custom_work_dir():
    """Should use persistence.work_dir from config."""
    config = {
        "dreaming": {"enabled": True},
        "persistence": {"work_dir": "/custom/path"},
    }
    service = build_dream_components(
        config, llm_provider=AsyncMock(), memory_store=AsyncMock()
    )

    assert service is not None
    assert str(service._dreams_dir) == "/custom/path/dreams"


def test_build_dream_components_default_work_dir():
    """Should fall back to .taskforce when no persistence.work_dir."""
    config = {"dreaming": {"enabled": True}}
    service = build_dream_components(
        config, llm_provider=AsyncMock(), memory_store=AsyncMock()
    )

    assert service is not None
    assert str(service._dreams_dir).endswith(".taskforce/dreams")
