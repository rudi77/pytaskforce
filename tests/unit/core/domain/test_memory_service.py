"""Tests for the enhanced MemoryService with human-like operations.

Covers recall with reinforcement, associative linking, spreading
activation, and the decay sweep.
"""

from __future__ import annotations

from unittest.mock import AsyncMock

from taskforce.core.domain.memory import (
    MemoryKind,
    MemoryRecord,
    MemoryScope,
)
from taskforce.core.domain.memory_service import MemoryService


def _make_record(
    content: str = "fact",
    record_id: str | None = None,
    tags: list[str] | None = None,
    strength: float = 0.8,
    associations: list[str] | None = None,
    importance: float = 0.5,
) -> MemoryRecord:
    kwargs: dict = {
        "scope": MemoryScope.USER,
        "kind": MemoryKind.LEARNED_FACT,
        "content": content,
        "tags": tags or [],
        "strength": strength,
        "importance": importance,
        "associations": associations or [],
    }
    if record_id:
        kwargs["id"] = record_id
    return MemoryRecord(**kwargs)


def _mock_store(records: list[MemoryRecord] | None = None) -> AsyncMock:
    store = AsyncMock()
    all_records = list(records or [])
    store.add = AsyncMock(side_effect=lambda r: r)
    store.get = AsyncMock(
        side_effect=lambda rid: next((r for r in all_records if r.id == rid), None)
    )
    store.list = AsyncMock(return_value=all_records)
    store.search = AsyncMock(return_value=all_records[:2])
    store.update = AsyncMock(side_effect=lambda r: r)
    store.delete = AsyncMock(return_value=True)
    return store


# ------------------------------------------------------------------
# Recall with reinforcement
# ------------------------------------------------------------------


class TestRecallReinforcement:
    """recall() should reinforce retrieved memories by default."""

    async def test_recall_reinforces_results(self) -> None:
        rec = _make_record(content="fact A", record_id="a1")
        store = _mock_store([rec])
        service = MemoryService(store)
        await service.recall("fact")
        assert store.update.called
        # The record should have been reinforced
        updated = store.update.call_args_list[0][0][0]
        assert updated.access_count >= 1

    async def test_recall_without_reinforce(self) -> None:
        rec = _make_record(content="fact A", record_id="a1")
        store = _mock_store([rec])
        service = MemoryService(store)
        await service.recall("fact", reinforce=False, spread_activation=False)
        # update should not have been called for reinforcement
        assert not store.update.called


# ------------------------------------------------------------------
# Explicit reinforce
# ------------------------------------------------------------------


class TestReinforceById:
    async def test_reinforce_existing(self) -> None:
        rec = _make_record(content="fact", record_id="r1")
        store = _mock_store([rec])
        service = MemoryService(store)
        result = await service.reinforce_by_id("r1")
        assert result is not None
        assert result.access_count >= 1

    async def test_reinforce_missing_returns_none(self) -> None:
        store = _mock_store([])
        service = MemoryService(store)
        result = await service.reinforce_by_id("nonexistent")
        assert result is None


# ------------------------------------------------------------------
# Association management
# ------------------------------------------------------------------


class TestAssociation:
    async def test_associate_creates_bidirectional_link(self) -> None:
        r1 = _make_record(content="A", record_id="a")
        r2 = _make_record(content="B", record_id="b")
        store = _mock_store([r1, r2])
        service = MemoryService(store)
        ok = await service.associate("a", "b")
        assert ok is True
        assert "b" in r1.associations
        assert "a" in r2.associations

    async def test_associate_returns_false_for_missing(self) -> None:
        store = _mock_store([])
        service = MemoryService(store)
        ok = await service.associate("x", "y")
        assert ok is False

    async def test_get_associated_returns_neighbours(self) -> None:
        r1 = _make_record(content="A", record_id="a", associations=["b"])
        r2 = _make_record(content="B", record_id="b", associations=["a"])
        store = _mock_store([r1, r2])
        service = MemoryService(store)
        neighbours = await service.get_associated("a")
        assert len(neighbours) == 1
        assert neighbours[0].id == "b"


# ------------------------------------------------------------------
# Decay sweep
# ------------------------------------------------------------------


class TestDecaySweep:
    async def test_weak_memory_gets_archived(self) -> None:
        weak = _make_record(
            content="forgotten",
            record_id="w",
            strength=0.01,
            importance=0.0,
        )
        store = _mock_store([weak])
        service = MemoryService(store)
        decayed, forgotten = await service.decay_sweep(threshold=0.10)
        assert forgotten >= 1
        assert "archived" in weak.tags

    async def test_strong_memory_survives(self) -> None:
        strong = _make_record(
            content="vivid",
            record_id="s",
            strength=0.95,
        )
        store = _mock_store([strong])
        service = MemoryService(store)
        _, forgotten = await service.decay_sweep(threshold=0.10)
        assert forgotten == 0
        assert "archived" not in strong.tags

    async def test_decay_sweep_delete_mode(self) -> None:
        weak = _make_record(
            content="gone",
            record_id="w",
            strength=0.01,
            importance=0.0,
        )
        store = _mock_store([weak])
        service = MemoryService(store)
        _, forgotten = await service.decay_sweep(threshold=0.10, archive=False)
        assert forgotten >= 1
        assert store.delete.called


# ------------------------------------------------------------------
# Auto-association on remember
# ------------------------------------------------------------------


class TestAutoAssociation:
    async def test_remember_discovers_associations(self) -> None:
        existing = _make_record(
            content="Python is great",
            record_id="e1",
            tags=["python"],
        )
        new_rec = _make_record(
            content="Python tips",
            tags=["python", "tips"],
        )
        store = _mock_store([existing])
        # search returns the existing record as a match
        store.search = AsyncMock(return_value=[existing])
        service = MemoryService(store)
        saved = await service.remember(new_rec, auto_associate=True)
        # The new record should have been associated with the existing one
        assert existing.id in saved.associations
