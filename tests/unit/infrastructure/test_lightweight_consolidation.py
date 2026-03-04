"""Tests for lightweight (no-LLM) memory consolidation."""

from __future__ import annotations

from unittest.mock import AsyncMock

from taskforce.core.domain.memory import (
    MemoryKind,
    MemoryRecord,
    MemoryScope,
)
from taskforce.infrastructure.memory.lightweight_consolidation import (
    run_lightweight_consolidation,
)


def _make_record(
    content: str = "fact",
    record_id: str | None = None,
    tags: list[str] | None = None,
    strength: float = 0.8,
    importance: float = 0.5,
    associations: list[str] | None = None,
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


def _mock_store(records: list[MemoryRecord]) -> AsyncMock:
    store = AsyncMock()
    store.list = AsyncMock(return_value=list(records))
    store.update = AsyncMock(side_effect=lambda r: r)
    return store


# ------------------------------------------------------------------
# Phase 1: Decay sweep
# ------------------------------------------------------------------


class TestDecayPhase:
    async def test_weak_memory_archived(self) -> None:
        weak = _make_record(
            content="forgotten",
            record_id="w",
            strength=0.01,
            importance=0.0,
        )
        store = _mock_store([weak])
        result = await run_lightweight_consolidation(store)
        assert result.archived >= 1
        assert "archived" in weak.tags

    async def test_strong_memory_survives(self) -> None:
        strong = _make_record(content="vivid", record_id="s", strength=0.95)
        store = _mock_store([strong])
        result = await run_lightweight_consolidation(store)
        assert result.archived == 0
        assert "archived" not in strong.tags

    async def test_already_archived_skipped(self) -> None:
        archived = _make_record(
            content="old",
            record_id="a",
            strength=0.01,
            importance=0.0,
            tags=["archived"],
        )
        store = _mock_store([archived])
        result = await run_lightweight_consolidation(store)
        assert result.archived == 0


# ------------------------------------------------------------------
# Phase 2: Reinforce session-related memories
# ------------------------------------------------------------------


class TestReinforcePhase:
    async def test_session_keywords_reinforce_matching(self) -> None:
        rec = _make_record(content="Python testing is great", tags=["python"])
        store = _mock_store([rec])
        original_count = rec.access_count
        result = await run_lightweight_consolidation(
            store, session_keywords={"python", "testing"}
        )
        assert result.strengthened >= 1
        assert rec.access_count > original_count

    async def test_no_reinforce_without_keywords(self) -> None:
        rec = _make_record(content="Python tips", tags=["python"])
        store = _mock_store([rec])
        result = await run_lightweight_consolidation(store, session_keywords=None)
        assert result.strengthened == 0

    async def test_short_keywords_filtered(self) -> None:
        """Keywords with length <= 2 are ignored."""
        rec = _make_record(content="is a test", tags=["test"])
        store = _mock_store([rec])
        result = await run_lightweight_consolidation(
            store, session_keywords={"is", "a"}
        )
        assert result.strengthened == 0

    async def test_needs_two_keyword_overlap(self) -> None:
        """A single keyword match is not enough for reinforcement."""
        rec = _make_record(content="only python here")
        store = _mock_store([rec])
        result = await run_lightweight_consolidation(
            store, session_keywords={"python", "javascript", "rust"}
        )
        assert result.strengthened == 0


# ------------------------------------------------------------------
# Phase 3: Build associations
# ------------------------------------------------------------------


class TestAssociationPhase:
    async def test_shared_tags_create_association(self) -> None:
        r1 = _make_record(content="A", record_id="a", tags=["python"])
        r2 = _make_record(content="B", record_id="b", tags=["python"])
        store = _mock_store([r1, r2])
        result = await run_lightweight_consolidation(store)
        assert result.associations_created >= 1
        assert "b" in r1.associations
        assert "a" in r2.associations

    async def test_no_association_without_shared_tags(self) -> None:
        r1 = _make_record(content="A", record_id="a", tags=["python"])
        r2 = _make_record(content="B", record_id="b", tags=["rust"])
        store = _mock_store([r1, r2])
        result = await run_lightweight_consolidation(store)
        assert result.associations_created == 0

    async def test_existing_association_not_duplicated(self) -> None:
        r1 = _make_record(
            content="A", record_id="a", tags=["python"], associations=["b"]
        )
        r2 = _make_record(
            content="B", record_id="b", tags=["python"], associations=["a"]
        )
        store = _mock_store([r1, r2])
        result = await run_lightweight_consolidation(store)
        assert result.associations_created == 0


# ------------------------------------------------------------------
# Result summary
# ------------------------------------------------------------------


class TestEmbeddingAssociations:
    """Test embedding-based association building."""

    async def test_embeddings_create_associations(self) -> None:
        """Records with similar embeddings get associated."""
        r1 = _make_record(content="Python testing", record_id="a")
        r2 = _make_record(content="Python unit tests", record_id="b")
        store = _mock_store([r1, r2])

        embedder = AsyncMock()
        # High cosine similarity between the two.
        embedder.embed_batch = AsyncMock(
            return_value=[[0.9, 0.1, 0.0], [0.85, 0.15, 0.0]]
        )

        result = await run_lightweight_consolidation(
            store, embedding_provider=embedder
        )
        assert result.associations_created >= 1
        assert "b" in r1.associations
        assert "a" in r2.associations

    async def test_dissimilar_embeddings_no_association(self) -> None:
        """Records with low cosine similarity are not associated."""
        r1 = _make_record(content="Python testing", record_id="a")
        r2 = _make_record(content="Italian cooking", record_id="b")
        store = _mock_store([r1, r2])

        embedder = AsyncMock()
        # Low similarity.
        embedder.embed_batch = AsyncMock(
            return_value=[[1.0, 0.0, 0.0], [0.0, 1.0, 0.0]]
        )

        result = await run_lightweight_consolidation(
            store, embedding_provider=embedder
        )
        assert result.associations_created == 0

    async def test_embedding_failure_falls_back_to_tags(self) -> None:
        """If embeddings fail, fall back to tag-based associations."""
        r1 = _make_record(content="A", record_id="a", tags=["python"])
        r2 = _make_record(content="B", record_id="b", tags=["python"])
        store = _mock_store([r1, r2])

        embedder = AsyncMock()
        embedder.embed_batch = AsyncMock(side_effect=RuntimeError("API error"))

        result = await run_lightweight_consolidation(
            store, embedding_provider=embedder
        )
        # Should still create tag-based association.
        assert result.associations_created >= 1

    async def test_embedding_with_single_record_falls_back(self) -> None:
        """With only one active record, skip embedding path."""
        r1 = _make_record(content="A", record_id="a", tags=["python"])
        store = _mock_store([r1])

        embedder = AsyncMock()

        await run_lightweight_consolidation(
            store, embedding_provider=embedder
        )
        # embed_batch should not be called with < 2 records.
        embedder.embed_batch.assert_not_called()


# ------------------------------------------------------------------
# Result summary
# ------------------------------------------------------------------


class TestResultSummary:
    async def test_duration_measured(self) -> None:
        store = _mock_store([])
        result = await run_lightweight_consolidation(store)
        assert result.duration_ms >= 0

    async def test_empty_store_produces_zero_counts(self) -> None:
        store = _mock_store([])
        result = await run_lightweight_consolidation(store)
        assert result.decayed == 0
        assert result.archived == 0
        assert result.strengthened == 0
        assert result.associations_created == 0
