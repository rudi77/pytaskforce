"""Tests for the FileMemoryStore in-memory cache and hybrid search."""

from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from taskforce.core.domain.memory import (
    MemoryKind,
    MemoryRecord,
    MemoryScope,
)
from taskforce.infrastructure.memory.file_memory_store import FileMemoryStore


def _make_record(
    content: str = "test",
    tags: list[str] | None = None,
    strength: float = 0.8,
    importance: float = 0.5,
) -> MemoryRecord:
    return MemoryRecord(
        scope=MemoryScope.USER,
        kind=MemoryKind.LEARNED_FACT,
        content=content,
        tags=tags or [],
        strength=strength,
        importance=importance,
    )


# ------------------------------------------------------------------
# In-memory cache tests
# ------------------------------------------------------------------


class TestInMemoryCache:
    @pytest.fixture()
    def store(self, tmp_path: Path) -> FileMemoryStore:
        return FileMemoryStore(tmp_path)

    async def test_cache_populated_on_first_load(self, store: FileMemoryStore) -> None:
        await store.add(_make_record("first"))
        records = await store.list()
        assert len(records) == 1
        # Second call should use cache (no disk parse).
        assert store._cache is not None

    async def test_cache_returns_copies(self, store: FileMemoryStore) -> None:
        await store.add(_make_record("original"))
        list1 = await store.list()
        list2 = await store.list()
        # Should be separate list objects (copies).
        assert list1 is not list2

    async def test_cache_invalidated_on_external_write(
        self, store: FileMemoryStore
    ) -> None:
        await store.add(_make_record("A"))
        assert store._cache is not None

        # Simulate external modification by changing mtime.
        file_path = store._file
        mtime = os.path.getmtime(file_path)
        os.utime(file_path, (mtime + 1, mtime + 1))

        assert store._cache_stale() is True

    async def test_add_updates_cache(self, store: FileMemoryStore) -> None:
        await store.add(_make_record("A"))
        await store.add(_make_record("B"))
        assert store._cache is not None
        assert len(store._cache) == 2

    async def test_delete_updates_cache(self, store: FileMemoryStore) -> None:
        rec = _make_record("delete me")
        await store.add(rec)
        await store.delete(rec.id)
        assert store._cache is not None
        assert len(store._cache) == 0

    async def test_update_updates_cache(self, store: FileMemoryStore) -> None:
        rec = _make_record("old")
        await store.add(rec)
        rec.content = "new"
        await store.update(rec)
        cached = [r for r in store._cache if r.id == rec.id]
        assert cached[0].content == "new"


# ------------------------------------------------------------------
# Hybrid search tests (keyword + effective_strength weighting)
# ------------------------------------------------------------------


class TestHybridSearch:
    @pytest.fixture()
    def store(self, tmp_path: Path) -> FileMemoryStore:
        return FileMemoryStore(tmp_path)

    async def test_search_excludes_archived(self, store: FileMemoryStore) -> None:
        rec = _make_record("python tips", tags=["archived", "python"])
        await store.add(rec)
        results = await store.search("python")
        assert len(results) == 0

    async def test_stronger_memory_ranks_higher(self, store: FileMemoryStore) -> None:
        weak = _make_record("python basics", strength=0.3)
        strong = _make_record("python advanced", strength=0.95)
        await store.add(weak)
        await store.add(strong)
        results = await store.search("python")
        assert len(results) == 2
        assert "advanced" in results[0].content

    async def test_search_keyword_score_normalised(
        self, store: FileMemoryStore
    ) -> None:
        """More keyword hits → higher score."""
        one_hit = _make_record("python guide", tags=["general"])
        two_hits = _make_record("python coding patterns", tags=["python"])
        await store.add(one_hit)
        await store.add(two_hits)
        results = await store.search("python coding")
        assert len(results) == 2
        # two_hits matches both words in content, one_hit only matches "python".
        assert "patterns" in results[0].content


# ------------------------------------------------------------------
# Semantic search with mock embedding provider
# ------------------------------------------------------------------


class TestSemanticSearch:
    async def test_semantic_scores_used_when_embedder_present(
        self, tmp_path: Path
    ) -> None:
        embedder = AsyncMock()
        # Return deterministic embeddings.
        embedder.embed_text = AsyncMock(return_value=[1.0, 0.0, 0.0])
        embedder.embed_batch = AsyncMock(
            return_value=[[0.9, 0.1, 0.0], [0.1, 0.9, 0.0]]
        )

        store = FileMemoryStore(tmp_path, embedding_provider=embedder)
        # Record A is semantically similar to query, B is not.
        await store.add(_make_record("very relevant topic", tags=["topic"]))
        await store.add(_make_record("unrelated stuff", tags=["other"]))

        results = await store.search("relevant topic")
        # With embeddings, record A should rank higher.
        assert len(results) >= 1
        assert "relevant" in results[0].content

    async def test_fallback_on_embedding_error(self, tmp_path: Path) -> None:
        embedder = AsyncMock()
        embedder.embed_text = AsyncMock(side_effect=RuntimeError("API down"))

        store = FileMemoryStore(tmp_path, embedding_provider=embedder)
        await store.add(_make_record("keyword match here"))

        # Should still work via keyword fallback.
        results = await store.search("keyword match")
        assert len(results) >= 1

    async def test_embedding_cache_reused(self, tmp_path: Path) -> None:
        embedder = AsyncMock()
        embedder.embed_text = AsyncMock(return_value=[1.0, 0.0])
        embedder.embed_batch = AsyncMock(return_value=[[0.8, 0.2]])

        store = FileMemoryStore(tmp_path, embedding_provider=embedder)
        rec = _make_record("cached embedding", tags=["test"])
        await store.add(rec)

        await store.search("test query")
        call_count_1 = embedder.embed_batch.call_count
        await store.search("another query")
        call_count_2 = embedder.embed_batch.call_count

        # Second search should use cached embeddings, so no new batch call.
        assert call_count_2 == call_count_1
