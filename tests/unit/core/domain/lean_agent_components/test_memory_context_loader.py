"""Tests for MemoryContextLoader.

The loader now selects and sorts memories by effective_strength (a
composite of recency, access frequency, emotional valence, and
importance) rather than simple recency.  It also reinforces injected
memories to model the fact that they are being "recalled".
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, Mock

from taskforce.core.domain.lean_agent_components.memory_context_loader import (
    MemoryContextConfig,
    MemoryContextLoader,
)
from taskforce.core.domain.memory import (
    EmotionalValence,
    MemoryKind,
    MemoryRecord,
    MemoryScope,
)


def _make_record(
    content: str = "Test memory",
    kind: MemoryKind = MemoryKind.PREFERENCE,
    scope: MemoryScope = MemoryScope.USER,
    updated_at: datetime | None = None,
    strength: float = 0.8,
    importance: float = 0.5,
    emotional_valence: EmotionalValence = EmotionalValence.NEUTRAL,
    tags: list[str] | None = None,
) -> MemoryRecord:
    """Create a MemoryRecord for testing."""
    return MemoryRecord(
        scope=scope,
        kind=kind,
        content=content,
        updated_at=updated_at or datetime.now(UTC),
        strength=strength,
        importance=importance,
        emotional_valence=emotional_valence,
        tags=tags or [],
    )


def _make_loader(
    records: list[MemoryRecord] | None = None,
    config: MemoryContextConfig | None = None,
) -> MemoryContextLoader:
    """Create a MemoryContextLoader with a mock store."""
    store = AsyncMock()
    store.list = AsyncMock(return_value=records or [])
    store.update = AsyncMock(side_effect=lambda r: r)
    logger = Mock()
    return MemoryContextLoader(
        memory_store=store,
        config=config or MemoryContextConfig(),
        logger=logger,
    )


async def test_load_returns_none_when_no_records():
    loader = _make_loader(records=[])
    result = await loader.load_memory_context()
    assert result is None


async def test_load_formats_records_with_header():
    records = [_make_record(content="Always use dark mode")]
    loader = _make_loader(records=records)
    result = await loader.load_memory_context()
    assert result is not None
    assert "## LONG-TERM MEMORY" in result
    assert "Always use dark mode" in result
    assert "**[PREFERENCE]**" in result


async def test_respects_max_total_chars():
    """Records that would exceed max_total_chars are dropped."""
    config = MemoryContextConfig(max_total_chars=150)
    records = [
        _make_record(content="A" * 60, strength=0.9),
        _make_record(content="B" * 60, strength=0.7),
    ]
    loader = _make_loader(records=records, config=config)
    result = await loader.load_memory_context()
    assert result is not None
    assert "A" * 60 in result
    assert "B" * 60 not in result


async def test_respects_max_chars_per_memory():
    """Long content is truncated per-record."""
    config = MemoryContextConfig(max_chars_per_memory=20)
    records = [_make_record(content="A" * 100)]
    loader = _make_loader(records=records, config=config)
    result = await loader.load_memory_context()
    assert result is not None
    assert "A" * 17 + "..." in result
    assert "A" * 100 not in result


async def test_config_from_dict():
    data = {
        "max_memories": 5,
        "max_chars_per_memory": 200,
        "max_total_chars": 1000,
        "kinds": ["preference", "learned_fact"],
        "scope": "user",
    }
    config = MemoryContextConfig.from_dict(data)
    assert config.max_memories == 5
    assert config.max_chars_per_memory == 200
    assert config.max_total_chars == 1000
    assert config.kinds == [MemoryKind.PREFERENCE, MemoryKind.LEARNED_FACT]
    assert config.scope == MemoryScope.USER


async def test_config_from_dict_defaults():
    """from_dict with empty dict returns defaults."""
    config = MemoryContextConfig.from_dict({})
    assert config.max_memories == 20
    assert config.max_total_chars == 3000
    assert MemoryKind.PREFERENCE in config.kinds


async def test_sorts_by_effective_strength_descending():
    """Strongest (most salient) memories appear first."""
    now = datetime.now(UTC)
    weak = _make_record(content="weak memory", strength=0.3, updated_at=now)
    strong = _make_record(content="strong memory", strength=0.95, updated_at=now)
    medium = _make_record(content="medium memory", strength=0.6, updated_at=now)

    store = AsyncMock()
    store.list = AsyncMock(return_value=[weak, medium, strong])
    store.update = AsyncMock(side_effect=lambda r: r)
    logger = Mock()
    loader = MemoryContextLoader(
        memory_store=store,
        config=MemoryContextConfig(),
        logger=logger,
    )
    result = await loader.load_memory_context()
    assert result is not None
    strong_pos = result.index("strong memory")
    medium_pos = result.index("medium memory")
    weak_pos = result.index("weak memory")
    assert strong_pos < medium_pos < weak_pos


async def test_respects_max_memories():
    """Only max_memories records are included."""
    config = MemoryContextConfig(max_memories=2, max_total_chars=10000)
    records = [_make_record(content=f"Memory {i}", strength=0.8) for i in range(5)]
    loader = _make_loader(records=records, config=config)
    result = await loader.load_memory_context()
    assert result is not None
    assert result.count("- **[") == 2


async def test_fetches_all_configured_kinds():
    """The loader queries the store for each configured kind."""
    config = MemoryContextConfig(
        kinds=[MemoryKind.PREFERENCE, MemoryKind.LEARNED_FACT]
    )
    store = AsyncMock()
    store.list = AsyncMock(return_value=[])
    store.update = AsyncMock(side_effect=lambda r: r)
    logger = Mock()
    loader = MemoryContextLoader(
        memory_store=store, config=config, logger=logger
    )
    await loader.load_memory_context()
    assert store.list.call_count == 2
    calls = store.list.call_args_list
    assert calls[0].kwargs == {"scope": MemoryScope.USER, "kind": MemoryKind.PREFERENCE}
    assert calls[1].kwargs == {"scope": MemoryScope.USER, "kind": MemoryKind.LEARNED_FACT}


async def test_kind_label_formatting():
    """Different kinds produce the correct label."""
    records = [
        _make_record(content="fact A", kind=MemoryKind.LEARNED_FACT),
    ]
    store = AsyncMock()
    store.list = AsyncMock(return_value=records)
    store.update = AsyncMock(side_effect=lambda r: r)
    logger = Mock()
    loader = MemoryContextLoader(
        memory_store=store,
        config=MemoryContextConfig(kinds=[MemoryKind.LEARNED_FACT]),
        logger=logger,
    )
    result = await loader.load_memory_context()
    assert result is not None
    assert "**[LEARNED FACT]**" in result


async def test_strength_indicators_in_output():
    """Records show strength indicators (vivid, clear, fading, dim)."""
    records = [_make_record(content="vivid mem", strength=0.95)]
    loader = _make_loader(records=records)
    result = await loader.load_memory_context()
    assert result is not None
    assert "[vivid]" in result


async def test_emotional_icon_in_output():
    """Emotional memories show an emotion indicator."""
    records = [
        _make_record(
            content="surprising discovery",
            emotional_valence=EmotionalValence.SURPRISE,
            strength=0.8,
        )
    ]
    loader = _make_loader(records=records)
    result = await loader.load_memory_context()
    assert result is not None
    assert "(!)" in result


async def test_archived_memories_excluded():
    """Memories tagged 'archived' are not injected."""
    records = [
        _make_record(content="active", strength=0.8, tags=[]),
        _make_record(content="old", strength=0.8, tags=["archived"]),
    ]
    loader = _make_loader(records=records)
    result = await loader.load_memory_context()
    assert result is not None
    assert "active" in result
    assert "old" not in result


async def test_very_weak_memories_excluded():
    """Memories with effective strength below threshold are excluded."""
    very_old = datetime.now(UTC) - timedelta(days=365)
    records = [
        _make_record(
            content="forgotten",
            strength=0.01,
            importance=0.0,
            updated_at=very_old,
        ),
    ]
    loader = _make_loader(records=records)
    result = await loader.load_memory_context()
    assert result is None


async def test_reinforce_on_injection():
    """Injected memories are reinforced (access_count increases)."""
    rec = _make_record(content="recalled")
    store = AsyncMock()
    store.list = AsyncMock(return_value=[rec])
    store.update = AsyncMock(side_effect=lambda r: r)
    logger = Mock()
    loader = MemoryContextLoader(
        memory_store=store,
        config=MemoryContextConfig(),
        logger=logger,
    )
    await loader.load_memory_context()
    assert rec.access_count >= 1
    assert store.update.called


# ------------------------------------------------------------------
# Contextual retrieval (mission-based boosting)
# ------------------------------------------------------------------


async def test_contextual_retrieval_boosts_relevant_memories():
    """When a mission is provided, matching memories rank higher."""
    now = datetime.now(UTC)
    # Both have similar strength, but "python" memory matches the mission.
    python_rec = _make_record(
        content="Python best practices for testing",
        strength=0.6,
        updated_at=now,
        tags=["python", "testing"],
    )
    cooking_rec = _make_record(
        content="Best Italian cooking recipes",
        strength=0.65,
        updated_at=now,
        tags=["cooking", "recipes"],
    )
    store = AsyncMock()
    store.list = AsyncMock(return_value=[cooking_rec, python_rec])
    store.update = AsyncMock(side_effect=lambda r: r)
    logger = Mock()
    loader = MemoryContextLoader(
        memory_store=store,
        config=MemoryContextConfig(),
        logger=logger,
    )

    # Without mission, cooking_rec has higher raw strength → first.
    result_no_mission = await loader.load_memory_context()
    assert result_no_mission is not None
    cooking_pos = result_no_mission.index("cooking")
    python_pos = result_no_mission.index("Python")
    assert cooking_pos < python_pos

    # Reset access counts for clean comparison.
    python_rec.access_count = 0
    cooking_rec.access_count = 0

    # With mission about Python testing, python_rec should be boosted.
    result_with_mission = await loader.load_memory_context(
        mission="Write Python unit tests for the API"
    )
    assert result_with_mission is not None
    python_pos2 = result_with_mission.index("Python")
    cooking_pos2 = result_with_mission.index("cooking")
    assert python_pos2 < cooking_pos2


async def test_contextual_retrieval_without_mission_is_neutral():
    """Without mission, load_memory_context behaves as before."""
    rec = _make_record(content="some fact", strength=0.8)
    store = AsyncMock()
    store.list = AsyncMock(return_value=[rec])
    store.update = AsyncMock(side_effect=lambda r: r)
    logger = Mock()
    loader = MemoryContextLoader(
        memory_store=store,
        config=MemoryContextConfig(),
        logger=logger,
    )
    result = await loader.load_memory_context(mission=None)
    assert result is not None
    assert "some fact" in result
