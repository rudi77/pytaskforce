"""Tests for MemoryContextLoader."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, Mock

import pytest

from taskforce.core.domain.lean_agent_components.memory_context_loader import (
    MemoryContextConfig,
    MemoryContextLoader,
)
from taskforce.core.domain.memory import MemoryKind, MemoryRecord, MemoryScope


def _make_record(
    content: str = "Test memory",
    kind: MemoryKind = MemoryKind.PREFERENCE,
    scope: MemoryScope = MemoryScope.USER,
    updated_at: datetime | None = None,
) -> MemoryRecord:
    """Create a MemoryRecord for testing."""
    return MemoryRecord(
        scope=scope,
        kind=kind,
        content=content,
        updated_at=updated_at or datetime.now(UTC),
    )


def _make_loader(
    records: list[MemoryRecord] | None = None,
    config: MemoryContextConfig | None = None,
) -> MemoryContextLoader:
    """Create a MemoryContextLoader with a mock store."""
    store = AsyncMock()
    store.list = AsyncMock(return_value=records or [])
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
    config = MemoryContextConfig(max_total_chars=100)
    records = [
        _make_record(content="A" * 60, updated_at=datetime.now(UTC)),
        _make_record(content="B" * 60, updated_at=datetime.now(UTC) - timedelta(hours=1)),
    ]
    loader = _make_loader(records=records, config=config)
    result = await loader.load_memory_context()
    assert result is not None
    # First record fits, second would exceed budget
    assert "A" * 60 in result
    assert "B" * 60 not in result


async def test_respects_max_chars_per_memory():
    """Long content is truncated per-record."""
    config = MemoryContextConfig(max_chars_per_memory=20)
    records = [_make_record(content="A" * 100)]
    loader = _make_loader(records=records, config=config)
    result = await loader.load_memory_context()
    assert result is not None
    # Content should be truncated to 17 chars + "..."
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


async def test_sorts_by_updated_at_descending():
    """Most recently updated memories appear first."""
    now = datetime.now(UTC)
    old = _make_record(content="old memory", updated_at=now - timedelta(days=10))
    new = _make_record(content="new memory", updated_at=now)
    mid = _make_record(content="mid memory", updated_at=now - timedelta(days=5))

    # Store returns them in arbitrary order
    store = AsyncMock()
    store.list = AsyncMock(return_value=[old, mid, new])
    logger = Mock()
    loader = MemoryContextLoader(
        memory_store=store,
        config=MemoryContextConfig(),
        logger=logger,
    )
    result = await loader.load_memory_context()
    assert result is not None
    # new memory should appear before mid, which should appear before old
    new_pos = result.index("new memory")
    mid_pos = result.index("mid memory")
    old_pos = result.index("old memory")
    assert new_pos < mid_pos < old_pos


async def test_respects_max_memories():
    """Only max_memories records are included."""
    config = MemoryContextConfig(max_memories=2, max_total_chars=10000)
    records = [_make_record(content=f"Memory {i}") for i in range(5)]
    loader = _make_loader(records=records, config=config)
    result = await loader.load_memory_context()
    assert result is not None
    # Should contain at most 2 bullet entries
    assert result.count("- **[") == 2


async def test_fetches_all_configured_kinds():
    """The loader queries the store for each configured kind."""
    config = MemoryContextConfig(
        kinds=[MemoryKind.PREFERENCE, MemoryKind.LEARNED_FACT]
    )
    store = AsyncMock()
    store.list = AsyncMock(return_value=[])
    logger = Mock()
    loader = MemoryContextLoader(
        memory_store=store, config=config, logger=logger
    )
    await loader.load_memory_context()
    # Should have called list() once per kind
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
    logger = Mock()
    loader = MemoryContextLoader(
        memory_store=store,
        config=MemoryContextConfig(kinds=[MemoryKind.LEARNED_FACT]),
        logger=logger,
    )
    result = await loader.load_memory_context()
    assert result is not None
    assert "**[LEARNED FACT]**" in result
