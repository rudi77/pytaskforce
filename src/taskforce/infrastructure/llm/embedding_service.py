"""LiteLLM-backed embedding service for semantic memory search.

Provider-agnostic: works with any embedding model available through
LiteLLM (OpenAI, Azure, Cohere, etc.).  Includes an in-memory cache
with SHA-256 key hashing to avoid redundant API calls.
"""

from __future__ import annotations

import hashlib
import math
from typing import Any

import structlog

logger = structlog.get_logger(__name__)

try:
    import litellm
except ImportError:  # pragma: no cover
    litellm = None  # type: ignore[assignment]


def cosine_similarity(vec_a: list[float], vec_b: list[float]) -> float:
    """Calculate cosine similarity between two embedding vectors.

    Args:
        vec_a: First embedding vector.
        vec_b: Second embedding vector.

    Returns:
        Cosine similarity score (−1.0 to 1.0).

    Raises:
        ValueError: If embedding dimensions don't match.
    """
    if len(vec_a) != len(vec_b):
        raise ValueError(
            f"Embedding dimensions must match: {len(vec_a)} vs {len(vec_b)}"
        )
    dot = sum(a * b for a, b in zip(vec_a, vec_b, strict=True))
    norm_a = math.sqrt(sum(a * a for a in vec_a))
    norm_b = math.sqrt(sum(b * b for b in vec_b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


class _EmbeddingCache:
    """In-memory LRU embedding cache keyed by SHA-256 text hash."""

    def __init__(self, max_size: int = 2000) -> None:
        self._store: dict[str, list[float]] = {}
        self._max_size = max_size

    @staticmethod
    def _key(text: str) -> str:
        return hashlib.sha256(text.encode()).hexdigest()[:16]

    def get(self, text: str) -> list[float] | None:
        return self._store.get(self._key(text))

    def put(self, text: str, embedding: list[float]) -> None:
        if len(self._store) >= self._max_size:
            oldest = next(iter(self._store))
            del self._store[oldest]
        self._store[self._key(text)] = embedding

    def clear(self) -> None:
        self._store.clear()


def _extract_embedding(emb_data: Any) -> list[float]:
    """Extract embedding vector from a LiteLLM response data element."""
    if isinstance(emb_data, dict):
        return emb_data["embedding"]
    return emb_data.embedding


class LiteLLMEmbeddingService:
    """Provider-agnostic embedding service via LiteLLM.

    Uses ``litellm.aembedding()`` to generate embeddings from any
    supported provider.  Satisfies ``EmbeddingProviderProtocol``.

    Example models::

        "text-embedding-3-small"      (OpenAI)
        "text-embedding-ada-002"      (OpenAI)
        "azure/text-embedding-ada-002" (Azure OpenAI)
        "cohere/embed-english-v3.0"   (Cohere)

    Args:
        model: LiteLLM model identifier for embeddings.
        cache_enabled: Whether to cache embeddings in memory.
        cache_max_size: Maximum number of cached embeddings.
    """

    def __init__(
        self,
        model: str = "text-embedding-3-small",
        cache_enabled: bool = True,
        cache_max_size: int = 2000,
    ) -> None:
        self._model = model
        self._cache = _EmbeddingCache(cache_max_size) if cache_enabled else None

    async def embed_text(self, text: str) -> list[float]:
        """Generate embedding vector for a single text."""
        if self._cache:
            cached = self._cache.get(text)
            if cached is not None:
                return cached

        if litellm is None:
            raise ImportError(
                "litellm package is required for embeddings. "
                "Install with: uv sync"
            )

        response = await litellm.aembedding(model=self._model, input=[text])
        embedding = _extract_embedding(response.data[0])

        if self._cache:
            self._cache.put(text, embedding)

        logger.debug(
            "embedding.generated",
            text_len=len(text),
            dim=len(embedding),
            model=self._model,
        )
        return embedding

    async def embed_batch(self, texts: list[str]) -> list[list[float]]:
        """Generate embedding vectors for multiple texts."""
        if not texts:
            return []

        results: list[list[float] | None] = [None] * len(texts)
        to_embed: list[tuple[int, str]] = []

        if self._cache:
            for i, text in enumerate(texts):
                cached = self._cache.get(text)
                if cached is not None:
                    results[i] = cached
                else:
                    to_embed.append((i, text))
        else:
            to_embed = list(enumerate(texts))

        if not to_embed:
            return [r for r in results if r is not None]

        if litellm is None:
            raise ImportError(
                "litellm package is required for embeddings. "
                "Install with: uv sync"
            )

        batch_texts = [text for _, text in to_embed]
        response = await litellm.aembedding(model=self._model, input=batch_texts)

        for i, emb_data in enumerate(response.data):
            idx = to_embed[i][0]
            embedding = _extract_embedding(emb_data)
            results[idx] = embedding
            if self._cache:
                self._cache.put(batch_texts[i], embedding)

        logger.debug(
            "embedding.batch_complete",
            total=len(texts),
            cached=len(texts) - len(to_embed),
            from_api=len(to_embed),
        )

        final: list[list[float]] = []
        for i, r in enumerate(results):
            if r is None:
                raise RuntimeError(
                    f"Embedding for text at index {i} was not returned by API"
                )
            final.append(r)
        return final

    def clear_cache(self) -> None:
        """Clear the embedding cache."""
        if self._cache:
            self._cache.clear()
