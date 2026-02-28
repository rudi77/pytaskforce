"""
Unit Tests for LiteLLM Embedding Service

Tests the LiteLLMEmbeddingService including embedding generation,
caching, cosine similarity, and graceful degradation.
"""

import math
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from accounting_agent.infrastructure.embeddings.litellm_embeddings import (
    LiteLLMEmbeddingService,
    cosine_similarity,
)


class TestCosineSimlarity:
    """Tests for the standalone cosine_similarity function."""

    def test_identical_vectors(self):
        """Identical vectors should have similarity 1.0."""
        vec = [1.0, 0.0, 0.0]
        assert abs(cosine_similarity(vec, vec) - 1.0) < 1e-6

    def test_orthogonal_vectors(self):
        """Orthogonal vectors should have similarity 0.0."""
        a = [1.0, 0.0]
        b = [0.0, 1.0]
        assert abs(cosine_similarity(a, b)) < 1e-6

    def test_opposite_vectors(self):
        """Opposite vectors should have similarity -1.0."""
        a = [1.0, 0.0]
        b = [-1.0, 0.0]
        assert abs(cosine_similarity(a, b) - (-1.0)) < 1e-6

    def test_zero_vector(self):
        """Zero vector should return 0.0."""
        a = [0.0, 0.0]
        b = [1.0, 0.0]
        assert cosine_similarity(a, b) == 0.0

    def test_dimension_mismatch_raises(self):
        """Mismatched dimensions should raise ValueError."""
        a = [1.0, 0.0]
        b = [1.0, 0.0, 0.0]
        with pytest.raises(ValueError, match="dimensions must match"):
            cosine_similarity(a, b)

    def test_known_similarity(self):
        """Test with known cosine similarity value."""
        a = [1.0, 2.0, 3.0]
        b = [4.0, 5.0, 6.0]
        # cos(a, b) = (4+10+18) / (sqrt(14) * sqrt(77))
        expected = 32.0 / (math.sqrt(14) * math.sqrt(77))
        assert abs(cosine_similarity(a, b) - expected) < 1e-6


class TestLiteLLMEmbeddingService:
    """Tests for LiteLLMEmbeddingService."""

    def _mock_litellm_response(self, embeddings: list[list[float]]):
        """Create a mock litellm response."""
        mock_response = MagicMock()
        mock_response.data = [{"embedding": emb} for emb in embeddings]
        return mock_response

    @pytest.mark.asyncio
    async def test_embed_text_calls_litellm(self):
        """Should call litellm.aembedding with correct parameters."""
        service = LiteLLMEmbeddingService(
            model="text-embedding-3-small", cache_enabled=False
        )

        mock_emb = [0.1, 0.2, 0.3]
        mock_response = self._mock_litellm_response([mock_emb])

        with patch("accounting_agent.infrastructure.embeddings.litellm_embeddings.litellm") as mock_litellm:
            mock_litellm.aembedding = AsyncMock(return_value=mock_response)

            result = await service.embed_text("test text")

            mock_litellm.aembedding.assert_called_once_with(
                model="text-embedding-3-small", input=["test text"]
            )
            assert result == mock_emb

    @pytest.mark.asyncio
    async def test_embed_batch(self):
        """Should embed multiple texts in a single call."""
        service = LiteLLMEmbeddingService(cache_enabled=False)

        embeddings = [[0.1, 0.2], [0.3, 0.4], [0.5, 0.6]]
        mock_response = self._mock_litellm_response(embeddings)

        with patch("accounting_agent.infrastructure.embeddings.litellm_embeddings.litellm") as mock_litellm:
            mock_litellm.aembedding = AsyncMock(return_value=mock_response)

            result = await service.embed_batch(["text1", "text2", "text3"])

            assert len(result) == 3
            assert result[0] == [0.1, 0.2]
            assert result[2] == [0.5, 0.6]

    @pytest.mark.asyncio
    async def test_caching(self):
        """Second call with same text should use cache, not API."""
        service = LiteLLMEmbeddingService(cache_enabled=True)

        mock_emb = [0.1, 0.2, 0.3]
        mock_response = self._mock_litellm_response([mock_emb])

        with patch("accounting_agent.infrastructure.embeddings.litellm_embeddings.litellm") as mock_litellm:
            mock_litellm.aembedding = AsyncMock(return_value=mock_response)

            # First call - should hit API
            result1 = await service.embed_text("test text")
            assert mock_litellm.aembedding.call_count == 1

            # Second call - should use cache
            result2 = await service.embed_text("test text")
            assert mock_litellm.aembedding.call_count == 1  # No additional call

            assert result1 == result2

    def test_cosine_similarity_method(self):
        """Instance method should delegate to standalone function."""
        service = LiteLLMEmbeddingService()

        a = [1.0, 0.0]
        b = [0.0, 1.0]
        assert abs(service.cosine_similarity(a, b)) < 1e-6

    @pytest.mark.asyncio
    async def test_embed_batch_empty(self):
        """Empty batch should return empty list."""
        service = LiteLLMEmbeddingService()

        result = await service.embed_batch([])
        assert result == []


class TestGracefulDegradation:
    """Test that the tool works without an embedding service."""

    @pytest.mark.asyncio
    async def test_semantic_rule_engine_without_embeddings(self):
        """SemanticRuleEngineTool should work without embedding_service."""
        from accounting_agent.tools.semantic_rule_engine_tool import SemanticRuleEngineTool
        from accounting_agent.domain.models import AccountingRule, RuleType, RuleSource

        tool = SemanticRuleEngineTool(
            rules_path="/nonexistent", embedding_service=None
        )

        # Create a simple vendor-only rule
        tool._rules = [
            AccountingRule(
                rule_id="TEST-1",
                rule_type=RuleType.VENDOR_ONLY,
                vendor_pattern="TestVendor",
                target_account="4930",
                source=RuleSource.MANUAL,
            )
        ]
        tool._rules_loaded = True
        # Prevent reload from detecting changed learned_rules.yaml in working dir
        tool._learned_rules_mtime = float("inf")

        result = await tool.execute(
            invoice_data={
                "supplier_name": "TestVendor GmbH",
                "line_items": [
                    {"description": "Office supplies", "net_amount": 100, "vat_rate": 0.19}
                ],
            }
        )

        assert result["success"] is True
        assert result["rules_applied"] == 1


class TestPersistentEmbeddingCache:
    """Tests for PersistentEmbeddingCache (disk-backed)."""

    def test_put_and_get_returns_same_embedding(self, tmp_path):
        """Stored embedding should be retrievable immediately."""
        from accounting_agent.infrastructure.embeddings.azure_embeddings import PersistentEmbeddingCache
        cache = PersistentEmbeddingCache(cache_dir=str(tmp_path), model="test-model")
        emb = [0.1, 0.2, 0.3]
        cache.put("hello world", emb)
        result = cache.get("hello world")
        assert result == emb

    def test_miss_returns_none(self, tmp_path):
        """Unknown text should return None."""
        from accounting_agent.infrastructure.embeddings.azure_embeddings import PersistentEmbeddingCache
        cache = PersistentEmbeddingCache(cache_dir=str(tmp_path), model="test-model")
        assert cache.get("not stored") is None

    def test_survives_process_restart(self, tmp_path):
        """Embedding written in one instance must be readable from a fresh instance."""
        from accounting_agent.infrastructure.embeddings.azure_embeddings import PersistentEmbeddingCache
        cache1 = PersistentEmbeddingCache(cache_dir=str(tmp_path), model="text-embedding-3-small")
        emb = [0.9, 0.8, 0.7]
        cache1.put("persistent text", emb)

        cache2 = PersistentEmbeddingCache(cache_dir=str(tmp_path), model="text-embedding-3-small")
        result = cache2.get("persistent text")
        assert result == emb

    def test_different_models_do_not_collide(self, tmp_path):
        """Embeddings from different models must be keyed independently."""
        from accounting_agent.infrastructure.embeddings.azure_embeddings import PersistentEmbeddingCache
        cache_a = PersistentEmbeddingCache(cache_dir=str(tmp_path), model="model-a")
        cache_b = PersistentEmbeddingCache(cache_dir=str(tmp_path), model="model-b")

        cache_a.put("same text", [1.0, 0.0])
        cache_b.put("same text", [0.0, 1.0])

        assert cache_a.get("same text") == [1.0, 0.0]
        assert cache_b.get("same text") == [0.0, 1.0]

    def test_clear_removes_all_entries(self, tmp_path):
        """After clear(), previously stored entries must be gone."""
        from accounting_agent.infrastructure.embeddings.azure_embeddings import PersistentEmbeddingCache
        cache = PersistentEmbeddingCache(cache_dir=str(tmp_path), model="test-model")
        cache.put("text1", [0.1])
        cache.put("text2", [0.2])
        cache.clear()

        assert cache.get("text1") is None
        assert cache.get("text2") is None

    def test_hot_cache_avoids_disk_read_on_repeated_access(self, tmp_path):
        """After put(), subsequent get() should hit the in-memory hot cache."""
        from accounting_agent.infrastructure.embeddings.azure_embeddings import PersistentEmbeddingCache
        cache = PersistentEmbeddingCache(cache_dir=str(tmp_path), model="test-model")
        emb = [0.5, 0.5]
        cache.put("cached text", emb)

        result1 = cache.get("cached text")
        result2 = cache.get("cached text")
        assert result1 == emb
        assert result2 == emb


class TestLiteLLMServiceWithPersistentCache:
    """Tests for LiteLLMEmbeddingService with disk-backed persistent cache."""

    @pytest.mark.asyncio
    async def test_persistent_cache_used_when_cache_dir_provided(self, tmp_path):
        """When cache_dir is given, service must use PersistentEmbeddingCache."""
        from accounting_agent.infrastructure.embeddings.azure_embeddings import PersistentEmbeddingCache
        service = LiteLLMEmbeddingService(
            model="text-embedding-3-small",
            cache_enabled=True,
            cache_dir=str(tmp_path),
        )
        assert isinstance(service._cache, PersistentEmbeddingCache)

    def test_in_memory_cache_used_when_no_cache_dir(self):
        """Without cache_dir, must fall back to in-memory EmbeddingCache."""
        from accounting_agent.infrastructure.embeddings.azure_embeddings import (
            EmbeddingCache,
            PersistentEmbeddingCache,
        )
        service = LiteLLMEmbeddingService(cache_enabled=True)
        assert isinstance(service._cache, EmbeddingCache)
        assert not isinstance(service._cache, PersistentEmbeddingCache)

    @pytest.mark.asyncio
    async def test_persistent_cache_hit_skips_api(self, tmp_path):
        """Second embed_text call with same text must not call the API."""
        service = LiteLLMEmbeddingService(
            model="text-embedding-3-small",
            cache_enabled=True,
            cache_dir=str(tmp_path),
        )
        mock_emb = [0.1, 0.2, 0.3]
        mock_response = MagicMock()
        mock_response.data = [{"embedding": mock_emb}]

        with patch("accounting_agent.infrastructure.embeddings.litellm_embeddings.litellm") as mock_litellm:
            mock_litellm.aembedding = AsyncMock(return_value=mock_response)

            result1 = await service.embed_text("unique text abc")
            result2 = await service.embed_text("unique text abc")

            assert mock_litellm.aembedding.call_count == 1
            assert result1 == result2 == mock_emb
