"""Tests for the embedding service and cosine similarity."""

from __future__ import annotations

import math

import pytest

from taskforce.infrastructure.llm.embedding_service import (
    LiteLLMEmbeddingService,
    _EmbeddingCache,
    cosine_similarity,
)

# ------------------------------------------------------------------
# Cosine similarity
# ------------------------------------------------------------------


class TestCosineSimilarity:
    def test_identical_vectors(self) -> None:
        assert cosine_similarity([1.0, 0.0], [1.0, 0.0]) == pytest.approx(1.0)

    def test_orthogonal_vectors(self) -> None:
        assert cosine_similarity([1.0, 0.0], [0.0, 1.0]) == pytest.approx(0.0)

    def test_opposite_vectors(self) -> None:
        assert cosine_similarity([1.0, 0.0], [-1.0, 0.0]) == pytest.approx(-1.0)

    def test_dimension_mismatch_raises(self) -> None:
        with pytest.raises(ValueError, match="dimensions must match"):
            cosine_similarity([1.0], [1.0, 0.0])

    def test_zero_vector_returns_zero(self) -> None:
        assert cosine_similarity([0.0, 0.0], [1.0, 0.0]) == 0.0

    def test_arbitrary_vectors(self) -> None:
        a = [1.0, 2.0, 3.0]
        b = [4.0, 5.0, 6.0]
        dot = 1 * 4 + 2 * 5 + 3 * 6  # 32
        norm_a = math.sqrt(14)
        norm_b = math.sqrt(77)
        expected = dot / (norm_a * norm_b)
        assert cosine_similarity(a, b) == pytest.approx(expected)


# ------------------------------------------------------------------
# Embedding cache
# ------------------------------------------------------------------


class TestEmbeddingCache:
    def test_put_and_get(self) -> None:
        cache = _EmbeddingCache(max_size=10)
        cache.put("hello", [0.1, 0.2])
        result = cache.get("hello")
        assert result == [0.1, 0.2]

    def test_miss_returns_none(self) -> None:
        cache = _EmbeddingCache(max_size=10)
        assert cache.get("missing") is None

    def test_eviction_on_max_size(self) -> None:
        cache = _EmbeddingCache(max_size=2)
        cache.put("a", [1.0])
        cache.put("b", [2.0])
        cache.put("c", [3.0])  # Should evict "a".
        assert cache.get("a") is None
        assert cache.get("b") == [2.0]
        assert cache.get("c") == [3.0]

    def test_clear(self) -> None:
        cache = _EmbeddingCache(max_size=10)
        cache.put("x", [0.5])
        cache.clear()
        assert cache.get("x") is None

    def test_same_text_overwrites(self) -> None:
        cache = _EmbeddingCache(max_size=10)
        cache.put("text", [1.0])
        cache.put("text", [2.0])
        assert cache.get("text") == [2.0]


# ------------------------------------------------------------------
# LiteLLMEmbeddingService (unit tests, no actual API calls)
# ------------------------------------------------------------------


class TestLiteLLMEmbeddingService:
    def test_init_with_cache(self) -> None:
        service = LiteLLMEmbeddingService(cache_enabled=True)
        assert service._cache is not None

    def test_init_without_cache(self) -> None:
        service = LiteLLMEmbeddingService(cache_enabled=False)
        assert service._cache is None

    def test_clear_cache(self) -> None:
        service = LiteLLMEmbeddingService()
        service.clear_cache()  # Should not raise.

    def test_clear_cache_when_disabled(self) -> None:
        service = LiteLLMEmbeddingService(cache_enabled=False)
        service.clear_cache()  # Should not raise.
