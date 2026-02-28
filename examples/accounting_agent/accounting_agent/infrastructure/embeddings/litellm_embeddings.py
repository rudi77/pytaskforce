"""
LiteLLM Embedding Service

Provider-agnostic embedding service using litellm.aembedding().
Supports any embedding model available through LiteLLM (OpenAI, Azure, Cohere, etc.).
Implements the same interface as AzureEmbeddingService for drop-in replacement.
"""

import math
from typing import Any, Optional

import structlog

try:
    import litellm
except ImportError:
    litellm = None  # type: ignore[assignment]

from accounting_agent.infrastructure.embeddings.azure_embeddings import (
    EmbeddingCache,
    PersistentEmbeddingCache,
)

logger = structlog.get_logger(__name__)


def _extract_embedding(emb_data: Any) -> list[float]:
    """Extract embedding vector from a response data element.

    Handles both dict-style (older LiteLLM) and attribute-style (newer) access.
    """
    if isinstance(emb_data, dict):
        return emb_data["embedding"]
    return emb_data.embedding


def cosine_similarity(embedding1: list[float], embedding2: list[float]) -> float:
    """Calculate cosine similarity between two embedding vectors.

    Args:
        embedding1: First embedding vector
        embedding2: Second embedding vector

    Returns:
        Cosine similarity score (-1.0 to 1.0)

    Raises:
        ValueError: If embedding dimensions don't match
    """
    if len(embedding1) != len(embedding2):
        raise ValueError(
            f"Embedding dimensions must match: {len(embedding1)} vs {len(embedding2)}"
        )

    dot_product = sum(a * b for a, b in zip(embedding1, embedding2))
    norm1 = math.sqrt(sum(a * a for a in embedding1))
    norm2 = math.sqrt(sum(b * b for b in embedding2))

    if norm1 == 0 or norm2 == 0:
        return 0.0

    return dot_product / (norm1 * norm2)


class LiteLLMEmbeddingService:
    """Provider-agnostic embedding service via LiteLLM.

    Uses litellm.aembedding() to generate embeddings from any supported provider.
    Supports persistent disk caching (default) to avoid redundant API calls across
    process restarts, or in-memory-only caching as fallback.

    Example models:
    - "text-embedding-3-small" (OpenAI)
    - "text-embedding-ada-002" (OpenAI)
    - "azure/text-embedding-ada-002" (Azure OpenAI)
    - "cohere/embed-english-v3.0" (Cohere)
    """

    def __init__(
        self,
        model: str = "text-embedding-3-small",
        cache_enabled: bool = True,
        cache_max_size: int = 1000,
        cache_dir: Optional[str] = None,
    ):
        """Initialize LiteLLM embedding service.

        Args:
            model: LiteLLM model identifier for embeddings
            cache_enabled: Whether to cache embeddings (default: True)
            cache_max_size: Maximum number of embeddings to cache
            cache_dir: Directory for persistent disk cache. When provided,
                embeddings survive process restarts. When None, falls back
                to in-memory-only caching.
        """
        self._model = model
        self._cache_enabled = cache_enabled
        if cache_enabled:
            if cache_dir is not None:
                self._cache: Optional[EmbeddingCache] = PersistentEmbeddingCache(
                    cache_dir=cache_dir,
                    model=model,
                    max_size=cache_max_size,
                )
                logger.info(
                    "litellm_embedding.persistent_cache_enabled",
                    cache_dir=cache_dir,
                    model=model,
                )
            else:
                self._cache = EmbeddingCache(max_size=cache_max_size)
        else:
            self._cache = None

    async def embed_text(self, text: str) -> list[float]:
        """Generate embedding vector for a single text.

        Args:
            text: Text to embed

        Returns:
            List of floats representing the embedding vector
        """
        if self._cache_enabled and self._cache:
            cached = self._cache.get(text)
            if cached:
                logger.debug("litellm_embedding.cache_hit", text_length=len(text))
                return cached

        if litellm is None:
            raise ImportError("litellm package required. Install with: uv add litellm")

        try:
            response = await litellm.aembedding(model=self._model, input=[text])
            embedding = _extract_embedding(response.data[0])

            if self._cache_enabled and self._cache:
                self._cache.put(text, embedding)

            logger.debug(
                "litellm_embedding.generated",
                text_length=len(text),
                embedding_dim=len(embedding),
                model=self._model,
            )
            return embedding

        except Exception as e:
            logger.error(
                "litellm_embedding.error",
                error=str(e),
                text_length=len(text),
                model=self._model,
            )
            raise

    async def embed_batch(self, texts: list[str]) -> list[list[float]]:
        """Generate embedding vectors for multiple texts.

        Args:
            texts: List of texts to embed

        Returns:
            List of embedding vectors (one per input text)
        """
        if not texts:
            return []

        # Check cache for each text
        results: list[Optional[list[float]]] = [None] * len(texts)
        texts_to_embed: list[tuple[int, str]] = []

        if self._cache_enabled and self._cache:
            for i, text in enumerate(texts):
                cached = self._cache.get(text)
                if cached:
                    results[i] = cached
                else:
                    texts_to_embed.append((i, text))
        else:
            texts_to_embed = list(enumerate(texts))

        if not texts_to_embed:
            logger.debug("litellm_embedding.batch_all_cached", count=len(texts))
            return [r for r in results if r is not None]

        if litellm is None:
            raise ImportError("litellm package required. Install with: uv add litellm")

        try:
            batch_texts = [text for _, text in texts_to_embed]
            response = await litellm.aembedding(model=self._model, input=batch_texts)

            for i, emb_data in enumerate(response.data):
                original_idx = texts_to_embed[i][0]
                embedding = _extract_embedding(emb_data)
                results[original_idx] = embedding

                if self._cache_enabled and self._cache:
                    self._cache.put(batch_texts[i], embedding)

        except Exception as e:
            logger.error(
                "litellm_embedding.batch_error",
                error=str(e),
                batch_size=len(texts_to_embed),
                model=self._model,
            )
            raise

        logger.debug(
            "litellm_embedding.batch_complete",
            total=len(texts),
            from_cache=len(texts) - len(texts_to_embed),
            from_api=len(texts_to_embed),
        )

        # Validate all slots were filled to preserve 1:1 correspondence
        final: list[list[float]] = []
        for i, r in enumerate(results):
            if r is None:
                raise RuntimeError(
                    f"Embedding for text at index {i} was not returned by API"
                )
            final.append(r)
        return final

    def cosine_similarity(
        self, embedding1: list[float], embedding2: list[float]
    ) -> float:
        """Calculate cosine similarity between two embeddings.

        Args:
            embedding1: First embedding vector
            embedding2: Second embedding vector

        Returns:
            Cosine similarity score (0.0 to 1.0)
        """
        return cosine_similarity(embedding1, embedding2)

    async def find_most_similar(
        self,
        query_embedding: list[float],
        candidate_embeddings: list[list[float]],
        threshold: float = 0.0,
    ) -> list[tuple[int, float]]:
        """Find most similar embeddings to a query embedding.

        Args:
            query_embedding: Query embedding vector
            candidate_embeddings: List of candidate embedding vectors
            threshold: Minimum similarity threshold

        Returns:
            List of (index, similarity) tuples, sorted by similarity descending
        """
        similarities = []
        for i, candidate in enumerate(candidate_embeddings):
            sim = cosine_similarity(query_embedding, candidate)
            if sim >= threshold:
                similarities.append((i, sim))

        similarities.sort(key=lambda x: x[1], reverse=True)
        return similarities

    def clear_cache(self) -> None:
        """Clear the embedding cache."""
        if self._cache:
            self._cache.clear()
            logger.info("litellm_embedding.cache_cleared")
